#!/usr/bin/env python3
"""Generate night files from the cached wiki bracket data.

Every cached match belongs to an edition and a region, and every game the wiki
lists carries a bracket stage. All three are mechanical: they come from the
page path and the bracket template, with no judgment involved. Without night
files the builder drops a match as an orphan, which is why 258 of 270 cached
matches were not reaching the dataset.

**This script curates nothing.** It never writes a team_id, never writes a
roster, and never touches player identity. Sides are oriented but left
unattributed, so accounts continue to render as bare IDs.

Existing night files are **merged, not replaced**. Curated content wins on
every field: a team_id, a roster, a hand written stage, an attribution block
and a date are all preserved exactly as found. This script only fills nulls
and appends matches that were missing. Losing the hand curation of #48 NA to
a regeneration would be a far worse outcome than any orphan match.

## Side orientation

Sides are oriented by the **hero pick join**, never by `team1side`.

The wiki lists six heroes per side, our cached match lists a `hero_id` and a
`team` per player, so comparing the two says which `match_team_index` the
wiki's `opponent1` actually played on. That needs no rosters and no identity,
which is what makes it usable on editions #1 to #16 where the wiki names no
players at all.

`team1side` is recorded as a **cross check only**. It is right 95% of the
time and inverts on 13 known games, so it decides nothing here. Where it
disagrees with the hero evidence, the match entry carries
`side_check.team1side_agrees: false` and the disagreement is reported. See
LIQUIPEDIA-NOTES.md for the measurement.

The wiki team name is recorded per side as `_wiki_team`, prefixed to mark it
as an annotation rather than a join key. Turning those names into team_ids is
deliberately not done here: team renames are an unsolved design problem, see
TEAM-IDENTITY-PROPOSAL.md, and auto-slugging names would fragment history
under exactly the renames that proposal is about.

Standard library only.

Usage:
    python scripts/generate_nights.py --dry-run
    python scripts/generate_nights.py
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_side_mapping import (  # noqa: E402
    SIDE_RULE,
    load_hero_ids,
    load_match_sides,
    normalise_hero,
)

DEFAULT_GAMES = Path("data/derived/liquipedia-games.json")
DEFAULT_MATCHES = Path("data/matches")
DEFAULT_NIGHTS = Path("data/curated/nights")
DEFAULT_ASSETS = Path("data/assets")

STAGE_LABELS = {"qualifier": "Qualifier", "challenger": "Challenger",
                "final": "Finals", "semifinal": "Semifinal"}

DATE_NOTE = ("UTC date of the earliest cached match, with date_span giving first and "
             "last. Derived, not curated, and it can differ by a day from the local "
             "broadcast date. An edition is NOT always a single evening: on some "
             "editions the qualifier was played days before the challenger and final, "
             "so date_span can be several days wide. That is a real property of the "
             "schedule, not a misassignment.")

SIDE_NOTE = ("Sides are oriented by the hero pick join against our own match cache, "
             "never by the wiki's team1side, which inverts on 13 known games. "
             "_wiki_team is an annotation and is not a join key.")


def load_match_info(path: Path) -> dict | None:
    try:
        return json.loads(gzip.decompress(path.read_bytes())).get("match_info") or None
    except (OSError, ValueError):
        return None


def orient(game: dict, sides: dict[int, Counter], hero_ids: dict[str, int]) -> dict:
    """Which match_team_index did the wiki's opponent1 play on?

    Returns a dict describing the decision, including its evidence, so a weak
    call is visible in the night file rather than indistinguishable from a
    strong one.
    """
    picks = game["team1_heroes"]
    if not all(picks) or any(normalise_hero(h) not in hero_ids for h in picks):
        return {"method": "unresolved", "reason": "wiki lists no usable hero picks",
                "team1_index": None, "margin": None, "team1side_agrees": None}

    wanted = Counter(hero_ids[normalise_hero(h)] for h in picks)
    score = {index: sum((wanted & sides[index]).values()) for index in (0, 1)}
    if score[0] == score[1]:
        return {"method": "unresolved", "reason": f"hero evidence is tied at {score[0]}",
                "team1_index": None, "margin": 0, "team1side_agrees": None}

    team1_index = 0 if score[0] > score[1] else 1
    predicted = SIDE_RULE.get(game.get("team1side"))
    return {
        "method": "hero-picks",
        "team1_index": team1_index,
        "margin": abs(score[0] - score[1]),
        "overlap": [score[0], score[1]],
        # None when the wiki gives no side at all, which is not a disagreement.
        "team1side_agrees": None if predicted is None else (predicted == team1_index),
    }


def build_match_entry(game: dict, info: dict, decision: dict) -> dict:
    """One match entry, with sides oriented but never attributed to a team."""
    stage = STAGE_LABELS.get(game.get("stage") or "", None)
    bestof = game.get("bestof")
    series_label = None
    if stage:
        series_label = f"{stage}, best of {bestof}" if bestof else stage

    observed = defaultdict(list)
    for player in info.get("players", []):
        if player.get("team") in (0, 1):
            observed[player["team"]].append(player.get("account_id"))

    sides = []
    for index in (0, 1):
        wiki_team = None
        if decision.get("team1_index") is not None:
            wiki_team = game["team1"] if index == decision["team1_index"] else game["team2"]
        sides.append({
            "match_team_index": index,
            "team_id": None,
            "_wiki_team": wiki_team,
            "_observed_account_ids": sorted(a for a in observed[index] if a is not None),
        })

    return {
        "match_id": game["match_id"],
        "stage": stage,
        "series_label": series_label,
        "game_in_series": game.get("game_in_series"),
        "side_check": decision,
        "sides": sides,
    }


def merge_match(existing: dict, generated: dict) -> list[str]:
    """Fill gaps in a curated match entry. Returns what changed.

    Curated values always win. Only a null is ever replaced.
    """
    changed = []
    for field in ("stage", "series_label", "game_in_series"):
        if existing.get(field) is None and generated.get(field) is not None:
            existing[field] = generated[field]
            changed.append(field)
    if "side_check" not in existing:
        existing["side_check"] = generated["side_check"]
        changed.append("side_check")

    by_index = {s.get("match_team_index"): s for s in existing.get("sides", [])}
    for side in generated["sides"]:
        target = by_index.get(side["match_team_index"])
        if target is None:
            existing.setdefault("sides", []).append(side)
            changed.append(f"side {side['match_team_index']}")
            continue
        # team_id is curation and is never touched, even to fill a null.
        if target.get("_wiki_team") is None and side["_wiki_team"] is not None:
            target["_wiki_team"] = side["_wiki_team"]
            changed.append(f"side {side['match_team_index']} _wiki_team")
        if not target.get("_observed_account_ids"):
            target["_observed_account_ids"] = side["_observed_account_ids"]
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--games", type=Path, default=DEFAULT_GAMES)
    parser.add_argument("--matches", type=Path, default=DEFAULT_MATCHES)
    parser.add_argument("--nights", type=Path, default=DEFAULT_NIGHTS)
    parser.add_argument("--assets", type=Path, default=DEFAULT_ASSETS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    hero_ids = load_hero_ids(args.assets)
    games = json.loads(args.games.read_text(encoding="utf-8"))["games"]
    held = {p.name.split(".")[0] for p in args.matches.glob("*.json.gz")}

    existing_by_id: dict[str, tuple[Path, dict]] = {}
    for path in sorted(args.nights.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        existing_by_id[doc["night_id"]] = (path, doc)

    by_night: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for game in games:
        if game["match_id"] in held:
            by_night[(game["edition"], game["region"])].append(game)

    covered = {g["match_id"] for gs in by_night.values() for g in gs}
    orphans = sorted(held - covered)

    stats = Counter()
    disagreements, unresolved, multi_day = [], [], []
    written: list[tuple[str, str, int]] = []

    for (edition, region), night_games in sorted(by_night.items()):
        night_id = f"ns{edition:03d}-{region}"
        entries, earliest, latest = [], None, None

        for game in sorted(night_games, key=lambda g: (g["match_id"])):
            info = load_match_info(args.matches / f"{game['match_id']}.json.gz")
            if info is None:
                stats["match unreadable"] += 1
                continue
            sides = load_match_sides(args.matches / f"{game['match_id']}.json.gz")
            decision = orient(game, sides, hero_ids) if sides else {
                "method": "unresolved", "reason": "our match has no usable teams",
                "team1_index": None, "margin": None, "team1side_agrees": None}

            stats[f"side {decision['method']}"] += 1
            if decision.get("team1side_agrees") is False:
                disagreements.append((game["match_id"], edition, region))
            if decision["method"] == "unresolved":
                unresolved.append((game["match_id"], edition, region, decision["reason"]))

            start = info.get("start_time")
            if start:
                earliest = start if earliest is None else min(earliest, start)
                latest = start if latest is None else max(latest, start)
            entries.append(build_match_entry(game, info, decision))

        if not entries:
            continue
        date = (datetime.fromtimestamp(earliest, timezone.utc).date().isoformat()
                if earliest else None)
        last = (datetime.fromtimestamp(latest, timezone.utc).date().isoformat()
                if latest else None)
        source_url = night_games[0]["source_url"]
        if date and last and date != last:
            stats["editions spanning more than one day"] += 1
            multi_day.append((night_id, date, last))

        if night_id in existing_by_id:
            path, doc = existing_by_id[night_id]
            by_match = {str(m.get("match_id")): m for m in doc.get("matches", [])}
            added, touched = 0, 0
            for entry in entries:
                if entry["match_id"] in by_match:
                    if merge_match(by_match[entry["match_id"]], entry):
                        touched += 1
                else:
                    doc.setdefault("matches", []).append(entry)
                    added += 1
            doc["matches"].sort(key=lambda m: str(m.get("match_id")))
            doc.setdefault("side_note", SIDE_NOTE)
            stats["nights merged"] += 1
            stats["matches added to existing nights"] += added
            stats["matches updated in existing nights"] += touched
            if not args.dry_run:
                path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
            written.append((night_id, f"merged (+{added} new, {touched} filled)", len(doc["matches"])))
            continue

        doc = {
            "schema_version": 1,
            "night_id": night_id,
            "series": "night-shift",
            "edition": edition,
            "region": region,
            "region_confirmed": True,
            "region_source": "Liquipedia page path, which names the region explicitly",
            "date": date,
            "date_span": [date, last],
            "date_note": DATE_NOTE,
            "membership_source": "liquipedia-bracket",
            "source": source_url,
            "_generated": ("Generated by scripts/generate_nights.py from cached wiki bracket "
                           "data. Edition, region and stage are mechanical. No team_id, no "
                           "roster and no player identity is curated here."),
            "side_note": SIDE_NOTE,
            "attribution": {"provider": "liquipedia", "url": source_url},
            "rosters": [],
            "matches": sorted(entries, key=lambda m: m["match_id"]),
        }
        stats["nights created"] += 1
        stats["matches in new nights"] += len(entries)
        if not args.dry_run:
            (args.nights / f"{date}-{night_id}.json").write_text(
                json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        written.append((night_id, "created", len(entries)))

    print(f"{'DRY RUN, nothing written' if args.dry_run else 'Wrote night files'}")
    print(f"  {len(held)} cached match(es), {len(covered)} placed into a night, "
          f"{len(orphans)} still orphaned")
    for key in sorted(stats):
        print(f"  {stats[key]:>4}  {key}")
    print(f"\n{len(written)} night(s):")
    for night_id, action, count in written:
        print(f"  {night_id:<12} {action:<34} {count} match(es)")
    if disagreements:
        print(f"\n{len(disagreements)} team1side disagreement(s), flagged not applied:")
        for match_id, edition, region in disagreements:
            print(f"  {match_id}  #{edition} {region.upper()}")
    if unresolved:
        print(f"\n{len(unresolved)} match(es) with unresolved sides "
              f"(they still ingest, sides are simply unattributed):")
        for match_id, edition, region, reason in unresolved:
            print(f"  {match_id}  #{edition} {region.upper()}: {reason}")
    if multi_day:
        print(f"\n{len(multi_day)} edition(s) span more than one day, which is a real "
              f"schedule fact and not a misassignment:")
        for night_id, first, last in multi_day:
            print(f"  {night_id}  {first} to {last}")
    if orphans:
        print(f"\n{len(orphans)} cached match(es) the wiki does not list, still orphaned:")
        for match_id in orphans[:20]:
            print(f"  {match_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
