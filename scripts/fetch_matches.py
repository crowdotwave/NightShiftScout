#!/usr/bin/env python3
"""Fetch Deadlock match metadata and cache the raw JSON to disk.

One file per match ID, under data/matches/<id>.json.gz. The compressed file
decompresses to exactly the bytes the API returned, with no reformatting,
key filtering, or pretty printing, so the cache stays a faithful record of
what the API said at the time it was asked. Gzip is a transport detail: it
cuts the repository to about a fifth of its raw size and is bit for bit
recoverable. See data/README.md for the one line decompress command.

The cache is authoritative. If a match is already cached, this script does
not make a network request for it under any circumstances, unless you
explicitly pass --force. Input IDs are also de-duplicated before fetching,
so a repeated ID in the input list costs one request at most.

A fetch that fails writes nothing, so re-running retries it. The rule is
"never re-fetch data we already have", not "give up permanently on a match
that timed out once".

Standard library only, so there is nothing to install.

Usage:
    python scripts/fetch_matches.py data/match-ids/night-shift.txt
    python scripts/fetch_matches.py 95172627 95180553
    python scripts/fetch_matches.py --dry-run ids.txt
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = "https://api.deadlock-api.com/v1"
DEFAULT_OUT = Path("data/matches")
USER_AGENT = "night-shift-scout-cache/1.0 (+local research tool)"


def parse_ids(text: str) -> list[str]:
    """Pull match IDs out of a text blob.

    Mirrors the parsing the console app already does, so the same pasted
    list works in both places: skip blank lines and '#' comments, strip any
    non-digit characters, then de-duplicate while preserving order.
    """
    seen: dict[str, None] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digits = "".join(ch for ch in line if ch.isdigit())
        if digits:
            seen.setdefault(digits, None)
    return list(seen)


def collect_ids(sources: list[str]) -> list[str]:
    """Read IDs from files where the argument names one, else treat it as literal text."""
    blob: list[str] = []
    for src in sources:
        path = Path(src)
        if path.is_file():
            blob.append(path.read_text(encoding="utf-8"))
        else:
            blob.append(src)
    if not sources and not sys.stdin.isatty():
        blob.append(sys.stdin.read())
    return parse_ids("\n".join(blob))


def fetch_one(match_id: str, retries: int, timeout: int) -> bytes:
    """Return the raw response body, or raise the final error after retries.

    Retries only on conditions that can plausibly succeed later: rate limits,
    server errors, and transport failures. A 404 is a fact about the match,
    not a transient problem, so it fails immediately.
    """
    url = f"{API_BASE}/matches/{match_id}/metadata"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None

    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 429:
                wait = float(exc.headers.get("Retry-After") or 0) or (2 ** attempt)
                print(f"    rate limited, waiting {wait:.0f}s", flush=True)
                time.sleep(wait)
                continue
            if 500 <= exc.code < 600:
                time.sleep(2 ** attempt)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            time.sleep(2 ** attempt)

    assert last_error is not None
    raise last_error


def looks_like_match(body: bytes) -> tuple[bool, str]:
    """Cheap sanity check so an error page never lands in the cache as if it were data.

    This validates a copy in memory. It never alters the bytes that get written.
    """
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        return False, f"response was not valid JSON ({exc})"
    if not isinstance(parsed, dict) or "match_info" not in parsed:
        keys = list(parsed)[:5] if isinstance(parsed, dict) else type(parsed).__name__
        return False, f"response has no match_info (top level: {keys})"
    return True, ""


def compress(body: bytes) -> bytes:
    """Gzip with a fixed timestamp.

    Gzip normally stamps the current time into the header, which would make
    two compressions of identical bytes produce different files and create
    pointless repository churn. Pinning mtime to 0 keeps it deterministic.
    """
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", compresslevel=9, mtime=0) as handle:
        handle.write(body)
    return buffer.getvalue()


def cache_path(out: Path, match_id: str) -> Path:
    return out / f"{match_id}.json.gz"


def is_cached(out: Path, match_id: str) -> bool:
    """True if we already hold this match, in either the current or the legacy layout."""
    return cache_path(out, match_id).exists() or (out / f"{match_id}.json").exists()


def read_cached(path: Path) -> bytes:
    """Return the original API bytes for a cached match, compressed or not."""
    if path.suffix == ".gz":
        return gzip.decompress(path.read_bytes())
    return path.read_bytes()


def write_atomic(destination: Path, body: bytes) -> None:
    """Write via a temp file and rename.

    A half written file would otherwise look cached on the next run and would
    then be trusted forever, which is exactly the failure this cache design
    is supposed to make impossible.
    """
    temp = destination.with_name(destination.name + ".part")
    temp.write_bytes(body)
    os.replace(temp, destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sources", nargs="*", help="Files containing match IDs, or literal IDs. Reads stdin if neither is given.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"Cache directory (default: {DEFAULT_OUT})")
    parser.add_argument("--force", action="store_true", help="Refetch and overwrite matches that are already cached")
    parser.add_argument("--dry-run", action="store_true", help="Report what would be fetched without making any request")
    parser.add_argument("--delay", type=float, default=0.25, help="Seconds to pause between network requests (default: 0.25)")
    parser.add_argument("--retries", type=int, default=3, help="Retry attempts per match on rate limits and server errors")
    parser.add_argument("--timeout", type=int, default=60, help="Per request timeout in seconds")
    args = parser.parse_args()

    ids = collect_ids(args.sources)
    if not ids:
        parser.error("no match IDs found in the given sources")

    args.out.mkdir(parents=True, exist_ok=True)

    cached, to_fetch = [], []
    for match_id in ids:
        if is_cached(args.out, match_id) and not args.force:
            cached.append(match_id)
        else:
            to_fetch.append(match_id)

    print(f"{len(ids)} unique match ID(s): {len(cached)} already cached, {len(to_fetch)} to fetch")
    if args.dry_run:
        for match_id in to_fetch:
            print(f"  would fetch {match_id}")
        return 0

    fetched, failed = [], []
    for index, match_id in enumerate(to_fetch, start=1):
        destination = cache_path(args.out, match_id)
        print(f"  [{index}/{len(to_fetch)}] {match_id} ... ", end="", flush=True)
        try:
            body = fetch_one(match_id, args.retries, args.timeout)
        except Exception as exc:  # noqa: BLE001 - report and continue to the next match
            print(f"FAILED ({exc})")
            failed.append((match_id, str(exc)))
            continue

        ok, reason = looks_like_match(body)
        if not ok:
            print(f"REJECTED ({reason})")
            failed.append((match_id, reason))
            continue

        packed = compress(body)
        write_atomic(destination, packed)
        # Read it back and confirm it restores to the exact bytes the API sent,
        # so a corrupt write is caught now rather than discovered months later.
        if read_cached(destination) != body:
            destination.unlink()
            print("REJECTED (compressed file did not round trip, nothing written)")
            failed.append((match_id, "gzip round trip mismatch"))
            continue
        print(f"cached {len(body):,} bytes as {len(packed):,} ({len(packed) / len(body):.0%})")
        fetched.append(match_id)
        if index < len(to_fetch):
            time.sleep(args.delay)

    print()
    print(f"Done. {len(fetched)} fetched, {len(cached)} skipped as already cached, {len(failed)} failed.")
    if failed:
        print("Failures (nothing was written for these, so rerunning will retry them):")
        for match_id, reason in failed:
            print(f"  {match_id}: {reason}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
