#!/usr/bin/env python3
"""Test whether `last_team_avg_badge` can separate Night Shift teams.

This is the one claim in `API-NOTES.md` that the cache cannot re-test, and it
is load bearing: it is the sole basis for believing no badge field can express
opponent strength at this level, which is why the Opposition column stays dead.
It rested on 45 profiles from three consecutive editions, which is the same
shape of sample that produced the amber/sapphire error.

**This script deliberately writes nothing per account.** `last_team_avg_badge`
is excluded from the `scripts/fetch_steam.py` allowlist, and that stays true:
the field is fetched, counted in memory, and only the aggregate distribution is
printed. Attaching a badge to an account ID on disk is exactly what the
allowlist exists to prevent, and the claim under test needs only the spread.

Standard library only. One request per 50 accounts.

Usage:
    python scripts/check_badge_spread.py
"""

from __future__ import annotations

import argparse
import collections
import gzip
import json
import time
import urllib.request
from pathlib import Path

API_BASE = "https://api.deadlock-api.com/v1"
USER_AGENT = "night-shift-scout-cache/1.0 (+local research tool)"
STEAM64_OFFSET = 76561197960265728
BATCH_SIZE = 50


def account_ids_from_cache(matches_dir: Path) -> list[int]:
    ids: set[int] = set()
    for path in sorted(matches_dir.glob("*.json.gz")):
        info = json.loads(gzip.decompress(path.read_bytes()))["match_info"]
        # Only genuine tournament games. The cache holds two wrong match IDs
        # pointing at public matches, and their players are not Night Shift
        # competitors, so counting them would answer a different question.
        if info.get("match_mode") != 2:
            continue
        for player in info.get("players", []):
            if player.get("account_id") is not None:
                ids.add(player["account_id"])
    return sorted(ids)


def fetch_badges(account_ids: list[int], delay: float) -> collections.Counter:
    """Return a badge histogram. No account ID is ever paired with a badge."""
    spread: collections.Counter = collections.Counter()
    for start in range(0, len(account_ids), BATCH_SIZE):
        batch = account_ids[start:start + BATCH_SIZE]
        csv = ",".join(str(i + STEAM64_OFFSET) for i in batch)
        request = urllib.request.Request(
            f"{API_BASE}/players/steam?account_ids={csv}",
            headers={"User-Agent": USER_AGENT},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = json.loads(response.read())
        for entry in raw:
            spread[entry.get("last_team_avg_badge")] += 1
        print(f"  {start + len(batch)} of {len(account_ids)} profiles read")
        if start + BATCH_SIZE < len(account_ids):
            time.sleep(delay)
    return spread


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--matches", type=Path, default=Path("data/matches"))
    parser.add_argument("--delay", type=float, default=0.25)
    args = parser.parse_args()

    account_ids = account_ids_from_cache(args.matches)
    print(f"{len(account_ids)} distinct account(s) across genuine tournament matches")

    spread = fetch_badges(account_ids, args.delay)
    total = sum(spread.values())
    print(f"\n{total} profile(s) returned a value\n")
    print(f"{'badge':>7}  {'players':>7}  share")
    for badge, count in sorted(spread.items(), key=lambda kv: (kv[0] is None, kv[0])):
        label = "null" if badge is None else str(badge)
        print(f"{label:>7}  {count:>7}  {100 * count / total:5.1f}%")

    distinct = {b for b in spread if b is not None}
    print()
    if len(distinct) <= 1:
        print("VERDICT: one distinct value. Badge cannot separate anything.")
    else:
        lo, hi = min(distinct), max(distinct)
        print(f"VERDICT: {len(distinct)} distinct value(s), range {lo} to {hi}.")
        print("A range wider than a subrank or two means the claim that badge")
        print("cannot separate these teams needs revisiting, not that it is wrong:")
        print("separating PLAYERS is not the same as separating TEAMS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
