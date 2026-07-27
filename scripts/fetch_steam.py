#!/usr/bin/env python3
"""Fetch Steam profiles, applying the field allowlist before anything is written.

The Steam endpoint returns a `friends` array: a full social graph for every
account. That must never enter the dataset and never reach the public site,
so this script filters in memory and only ever writes the allowed fields.
The raw response is never cached, never logged, and never touches disk.

Allowed through:
    account_id, personaname, profileurl, countrycode, avatarmedium

Dropped: friends (social graph), realname (a legal name, not a handle),
last_updated, last_team_avg_badge, matches_played_last_30d.

Avatars are downloaded once into data/assets/avatars/ so the public site can
serve them locally. Hotlinking Steam's CDN from a public page would leak
every visitor's IP to Valve.

Standard library only.

Usage:
    python scripts/fetch_steam.py                 # every account in the match cache
    python scripts/fetch_steam.py --no-avatars
"""

from __future__ import annotations

import argparse
import gzip
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = "https://api.deadlock-api.com/v1"
USER_AGENT = "night-shift-scout-cache/1.0 (+local research tool)"

# The allowlist. Adding a field here is a deliberate act, which is the point:
# a denylist would silently admit any new field the API starts returning.
ALLOWED_FIELDS = ("account_id", "personaname", "profileurl", "countrycode", "avatarmedium")

DEFAULT_MATCHES = Path("data/matches")
DEFAULT_OUT = Path("data/assets/steam-profiles.json")
DEFAULT_AVATARS = Path("data/assets/avatars")
BATCH_SIZE = 50


def account_ids_from_cache(matches_dir: Path) -> list[int]:
    ids: set[int] = set()
    for path in sorted(matches_dir.glob("*.json.gz")):
        info = json.loads(gzip.decompress(path.read_bytes()))["match_info"]
        for player in info.get("players", []):
            if player.get("account_id") is not None:
                ids.add(player["account_id"])
    return sorted(ids)


def get(url: str, timeout: int = 60) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def filter_profile(raw: dict) -> dict:
    """Keep only allowlisted fields. This is the only path data takes to disk."""
    return {key: raw.get(key) for key in ALLOWED_FIELDS if key in raw}


def fetch_profiles(account_ids: list[int], delay: float) -> list[dict]:
    kept: list[dict] = []
    for start in range(0, len(account_ids), BATCH_SIZE):
        batch = account_ids[start:start + BATCH_SIZE]
        csv = ",".join(str(i) for i in batch)
        print(f"  profiles {start + 1} to {start + len(batch)} of {len(account_ids)} ... ", end="", flush=True)
        raw = json.loads(get(f"{API_BASE}/players/steam?account_ids={csv}"))
        # Filter immediately. `raw` goes out of scope and is never persisted.
        kept.extend(filter_profile(entry) for entry in raw)
        dropped = sorted({k for entry in raw for k in entry} - set(ALLOWED_FIELDS))
        print(f"{len(raw)} returned, dropped {len(dropped)} field(s): {', '.join(dropped)}")
        if start + BATCH_SIZE < len(account_ids):
            time.sleep(delay)
    return kept


def download_avatars(profiles: list[dict], out_dir: Path, delay: float) -> tuple[int, int, list[str]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = skipped = 0
    failed: list[str] = []
    for profile in profiles:
        url = profile.get("avatarmedium")
        account_id = profile.get("account_id")
        if not url or account_id is None:
            continue
        suffix = ".jpg" if ".jpg" in url.lower() else Path(url).suffix or ".img"
        destination = out_dir / f"{account_id}{suffix}"
        if destination.exists():
            skipped += 1
            continue
        try:
            body = get(url, timeout=30)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            failed.append(f"{account_id}: {exc}")
            continue
        temp = destination.with_name(destination.name + ".part")
        temp.write_bytes(body)
        temp.replace(destination)
        saved += 1
        time.sleep(delay)
    return saved, skipped, failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--matches", type=Path, default=DEFAULT_MATCHES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--avatar-dir", type=Path, default=DEFAULT_AVATARS)
    parser.add_argument("--no-avatars", action="store_true")
    parser.add_argument("--delay", type=float, default=0.25)
    args = parser.parse_args()

    account_ids = account_ids_from_cache(args.matches)
    print(f"{len(account_ids)} distinct account ID(s) in the match cache")

    profiles = fetch_profiles(account_ids, args.delay)
    profiles.sort(key=lambda p: p.get("account_id") or 0)

    # Belt and braces: prove no disallowed key survived before writing.
    leaked = sorted({k for p in profiles for k in p} - set(ALLOWED_FIELDS))
    if leaked:
        print(f"ERROR: disallowed field(s) reached the write path: {leaked}")
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "note": "Filtered at ingestion. Raw Steam responses are never cached. See scripts/fetch_steam.py.",
        "allowed_fields": list(ALLOWED_FIELDS),
        "profiles": profiles,
    }
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(profiles)} filtered profile(s) to {args.out}")

    if not args.no_avatars:
        print("downloading avatars ...")
        saved, skipped, failed = download_avatars(profiles, args.avatar_dir, args.delay)
        print(f"  {saved} downloaded, {skipped} already present, {len(failed)} failed")
        for line in failed:
            print(f"    {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
