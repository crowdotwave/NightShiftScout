#!/usr/bin/env python3
"""Slowly backfill matches the API has to pull from Valve, across many hours.

Run this detached and walk away. It is designed to be left alone, killed at
any moment, and started again with no cleanup.

Why this exists separately from `fetch_matches.py`: a match the API already
holds is cheap, and `fetch_matches.py` handles those fine in one pass. A
match the API does *not* hold has to be fetched from Valve and is capped at
**3 requests per hour per IP**. That is not a spacing problem, it is a budget
problem, and no polite delay solves it. Backfilling a handful of cold matches
is therefore a multi hour job that consists almost entirely of waiting.

`fetch_matches.py` deliberately refuses to sit through that wait, because a
script that sleeps for an hour with no output is indistinguishable from one
that has hung. This script is the place where waiting is the *expected*
behaviour, so it waits loudly: every window, every attempt and every sleep is
timestamped and flushed.

How it works:

1. Ask `fetch_matches` for the ids we do not already hold.
2. Fetch until the hourly budget runs out, which it detects from the API's
   own Retry-After rather than by counting requests, so a budget partly spent
   by something else is handled correctly.
3. Sleep until the budget resets, plus a small margin, then go again.
4. Stop when nothing is left, or when `--max-hours` is reached.

Resumability is inherited, not implemented. A failed fetch writes nothing and
cached matches are never re-requested, so being killed costs at most the one
match in flight. There is no state file, no lock and no partial output to
clean up. See the rate limit section in API-NOTES.md.

Standard library only.

Usage, detached:

    # PowerShell
    Start-Process -WindowStyle Hidden python `
      -ArgumentList "scripts/backfill_cold.py","data/match-ids/liquipedia-backfill.txt" `
      -RedirectStandardOutput backfill.log

    # bash
    nohup python scripts/backfill_cold.py data/match-ids/liquipedia-backfill.txt \
      > backfill.log 2>&1 &

Then check on it whenever you like:

    Get-Content backfill.log -Tail 20     # PowerShell
    tail -f backfill.log                  # bash
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fetch_matches import (  # noqa: E402
    RateLimited,
    cache_path,
    collect_ids,
    compress,
    fetch_one,
    is_cached,
    looks_like_match,
    read_cached,
    write_atomic,
)

# The API's hourly cold budget. Only used as a fallback when a 429 arrives
# with no Retry-After, which should not happen but is cheap to guard.
FALLBACK_WAIT_S = 3600.0


def log(message: str) -> None:
    """Timestamped and flushed. This script's whole job is to be watchable."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def fetch_and_store(match_id: str, out: Path, timeout: int) -> tuple[bool, str]:
    """Fetch one match and write it. Returns (stored, detail).

    Raises RateLimited so the caller can decide to wait. Every other failure
    is returned rather than raised, because one bad match should not end a
    run that still has hours of budget ahead of it.

    `max_wait=0` means this never sleeps inside a request. Waiting is the
    outer loop's decision, made once per window, not per attempt.
    """
    try:
        body = fetch_one(match_id, retries=0, timeout=timeout, max_wait=0.0)
    except RateLimited:
        raise
    except Exception as exc:  # noqa: BLE001 - report and let the caller continue
        return False, f"failed ({exc})"

    ok, reason = looks_like_match(body)
    if not ok:
        return False, f"rejected ({reason})"

    destination = cache_path(out, match_id)
    packed = compress(body)
    write_atomic(destination, packed)
    if read_cached(destination) != body:
        destination.unlink()
        return False, "rejected (gzip round trip mismatch, nothing written)"
    return True, f"cached {len(body):,} bytes as {len(packed):,} ({len(packed) / len(body):.0%})"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sources", nargs="*", help="Files containing match IDs, or literal IDs")
    parser.add_argument("--out", type=Path, default=Path("data/matches"))
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--margin", type=float, default=30.0,
                        help="Extra seconds to wait past the reset, so we never race it (default: 30)")
    parser.add_argument("--max-hours", type=float, default=12.0,
                        help="Give up after this long rather than run forever (default: 12)")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="Seconds between requests inside one window (default: 2)")
    args = parser.parse_args()

    ids = collect_ids(args.sources)
    if not ids:
        parser.error("no match IDs found in the given sources")

    args.out.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + args.max_hours * 3600

    outstanding = [i for i in ids if not is_cached(args.out, i)]
    log(f"{len(ids)} id(s) in the list, {len(ids) - len(outstanding)} already cached, "
        f"{len(outstanding)} to fetch")
    if not outstanding:
        log("Nothing to do.")
        return 0
    log(f"Will stop by {datetime.fromtimestamp(deadline).strftime('%Y-%m-%d %H:%M:%S')} "
        f"at the latest. Safe to kill at any time, rerunning resumes.")

    stored: list[str] = []
    problems: list[tuple[str, str]] = []
    window = 0

    while True:
        # Recompute from disk each pass, so a match fetched by any other means
        # in the meantime is picked up rather than re-requested.
        remaining = [i for i in outstanding
                     if not is_cached(args.out, i) and i not in dict(problems)]
        if not remaining:
            break
        if time.time() >= deadline:
            log(f"Reached the {args.max_hours}h limit with {len(remaining)} still outstanding. "
                f"Rerun to continue.")
            break

        window += 1
        log(f"--- window {window}, {len(remaining)} outstanding ---")
        wait_for: float | None = None

        for match_id in remaining:
            if time.time() >= deadline:
                break
            try:
                ok, detail = fetch_and_store(match_id, args.out, args.timeout)
            except RateLimited as exc:
                wait_for = exc.retry_after or FALLBACK_WAIT_S
                log(f"{match_id}: budget exhausted, resets in {wait_for:.0f}s")
                break

            if ok:
                stored.append(match_id)
                log(f"{match_id}: {detail}")
            else:
                # A 404 or a malformed body will not fix itself on the next
                # window, so record it and stop retrying it every hour.
                problems.append((match_id, detail))
                log(f"{match_id}: {detail}")
            time.sleep(args.delay)

        if wait_for is None:
            continue

        resume = time.time() + wait_for + args.margin
        if resume >= deadline:
            log(f"The next window would land past the {args.max_hours}h limit. Stopping. "
                f"Rerun to continue.")
            break
        log(f"Sleeping until {datetime.fromtimestamp(resume).strftime('%H:%M:%S')} "
            f"({(wait_for + args.margin) / 60:.0f} min). This is expected, not a hang.")
        time.sleep(wait_for + args.margin)

    still_missing = [i for i in ids if not is_cached(args.out, i)]
    log("")
    log(f"Done. {len(stored)} newly cached, {len(still_missing)} still missing, "
        f"{len(problems)} with a problem that will not resolve by waiting.")
    for match_id, detail in problems:
        log(f"  {match_id}: {detail}")
    if still_missing:
        log("Rerun this script to continue. Cached matches are never re-requested.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
