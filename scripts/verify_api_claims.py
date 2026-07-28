#!/usr/bin/env python3
"""Re-test the API claims in our docs against the whole match cache.

Every "confirmed" claim in CLAUDE.md and API-NOTES.md was established on the
same 12 matches, editions #46 to #48, 144 player-games. That is the sample
that produced the amber/sapphire side mapping error: the rule held perfectly
on those 12 and inverts on 13 games elsewhere, because three consecutive
recent editions are not a random sample of 49 editions.

**Every other conclusion drawn from those 12 matches inherits that weakness.**
Not that they are wrong, but that they were never tested anywhere else. This
script re-tests the ones the cache alone can settle, across every match in the
cache. It prints the counts rather than hardcoding how many there are, because
a hardcoded total is the same mistake one level up.

Claims needing a live API call, the Steam profile endpoint, the leaderboard,
or match history, cannot be re-tested here and are listed as such at the end
rather than quietly omitted.

It also writes `data/derived/verified-facts.json`. The project rule is that
**no number appears in a document unless a committed script prints it**, since
hand measured figures copied between files are exactly how the entries in
RETRACTIONS.md came about.

Note this counts the RAW CACHE, which deliberately includes matches that are
excluded at ingest. `scripts/build_dataset.py` gates on `match_mode == 2`, so
its totals are smaller and the two numbers are not meant to agree.

Standard library only. Makes no network requests.

Usage:
    python scripts/verify_api_claims.py
"""

from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def final_damage_entry(player: dict) -> dict | None:
    stats = player.get("stats") or []
    if not stats:
        return None
    return max(stats, key=lambda s: s.get("time_stamp_s") or 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--matches", type=Path, default=Path("data/matches"))
    parser.add_argument("--assets", type=Path, default=Path("data/assets"))
    parser.add_argument("--facts", type=Path,
                        default=Path("data/derived/verified-facts.json"))
    args = parser.parse_args()

    snapshots = sorted(args.assets.glob("heroes-*.json.gz"))
    heroes = json.loads(gzip.decompress(snapshots[-1].read_bytes())) if snapshots else []
    hero_type = {h["id"]: h.get("hero_type") for h in heroes}

    c = Counter()
    exceptions: dict[str, list[str]] = {}

    def note(key: str, detail: str) -> None:
        exceptions.setdefault(key, []).append(detail)

    for path in sorted(args.matches.glob("*.json.gz")):
        mid = path.name.split(".")[0]
        try:
            doc = json.loads(gzip.decompress(path.read_bytes()))
        except (OSError, ValueError):
            c["unreadable match"] += 1
            continue
        info = doc.get("match_info") or {}
        c["matches"] += 1

        # Top level keys.
        if set(doc) != {"match_info", "hero_build_ids", "banned_hero_ids"}:
            note("top level keys differ", f"{mid}: {sorted(doc)}")
        if doc.get("banned_hero_ids"):
            c["banned_hero_ids non-empty"] += 1
            note("banned_hero_ids non-empty", f"{mid}: {doc['banned_hero_ids']}")
        else:
            c["banned_hero_ids empty"] += 1

        players = info.get("players") or []
        if len(players) == 12:
            c["matches with exactly 12 players"] += 1
        else:
            note("player count not 12", f"{mid}: {len(players)}")

        mode = info.get("match_mode")
        c[f"match_mode {mode}"] += 1

        # average_badge, claimed always 0 on tournament games.
        for field in ("average_badge_team0", "average_badge_team1"):
            value = info.get(field)
            if value == 0:
                c[f"{field} is 0"] += 1
            elif value is None:
                c[f"{field} absent"] += 1
            else:
                c[f"{field} non-zero"] += 1
                note(f"{field} non-zero", f"{mid} (mode {mode}): {value}")

        if info.get("match_outcome") in (0, None):
            c["match_outcome 0 or absent"] += 1
        else:
            note("match_outcome non-zero", f"{mid}: {info.get('match_outcome')}")

        if info.get("winning_team") in (0, 1):
            c["winning_team is 0 or 1"] += 1
        else:
            note("winning_team not 0/1", f"{mid}: {info.get('winning_team')!r}")

        if info.get("teams"):
            note("teams[] non-empty", f"{mid}")
        else:
            c["teams[] empty or absent"] += 1

        duration = info.get("duration_s")
        for player in players:
            c["player-games"] += 1

            entry = final_damage_entry(player)
            if entry is None:
                note("no stats[] series", f"{mid}/{player.get('account_id')}")
            else:
                if entry.get("player_damage") is None:
                    note("final stats entry has no player_damage",
                         f"{mid}/{player.get('account_id')}")
                else:
                    c["player_damage present in final stats entry"] += 1
                if duration is not None and entry.get("time_stamp_s") == duration:
                    c["max time_stamp_s equals duration_s"] += 1
                else:
                    note("max time_stamp_s != duration_s",
                         f"{mid}/{player.get('account_id')}: "
                         f"{entry.get('time_stamp_s')} vs {duration}")

            if player.get("net_worth") is None:
                note("net_worth missing", f"{mid}/{player.get('account_id')}")
            role = hero_type.get(player.get("hero_id"))
            if role:
                c["player-games resolving a hero_type"] += 1
            else:
                note("hero_type missing", f"hero {player.get('hero_id')} in {mid}")

    print("Re-test of the 12 match claims across the whole cache")
    print("=" * 62)
    for key in sorted(c):
        print(f"  {c[key]:>6}  {key}")

    print("\nExceptions found")
    print("-" * 62)
    if not exceptions:
        print("  none")
    for key, items in sorted(exceptions.items()):
        print(f"  {len(items):>5}  {key}")
        for item in items[:4]:
            print(f"           {item}")
        if len(items) > 4:
            print(f"           ... and {len(items) - 4} more")

    print("\nClaims this script CANNOT re-test, because the cache does not")
    print("contain the data:")
    for line in [
        "possible_account_ids is unique only 58% of the time  (needs /leaderboard)",
        "match_result is the winning team index, 9/9  (needs /players/{id}/match-history)",
        "Role Score leave-one-out shift is at most +0.03x  (recomputable, but it is a "
        "property of our metric rather than of the API)",
    ]:
        print(f"  - {line}")
    print("  (last_team_avg_badge is settled, see scripts/check_badge_spread.py)")

    # ---- machine readable output -------------------------------------------
    # Every count quoted in a document should be traceable to a script anyone
    # can re-run. Numbers measured once by hand and then copied are how the
    # entries in RETRACTIONS.md happened, so the counts get written to a file
    # rather than only to a terminal nobody kept.
    facts = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "scripts/verify_api_claims.py",
        "note": "Counts over the raw match cache, including matches excluded at ingest. "
                "See RETRACTIONS.md for the rule that produced this file.",
        "counts": dict(sorted(c.items())),
        "exceptions": {key: sorted(items) for key, items in sorted(exceptions.items())},
    }
    args.facts.parent.mkdir(parents=True, exist_ok=True)
    args.facts.write_text(json.dumps(facts, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {args.facts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
