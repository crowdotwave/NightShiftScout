#!/usr/bin/env python3
"""Test the Liquipedia side mapping rule against every match we hold.

The rule recorded in LIQUIPEDIA-NOTES.md, established on 12 matches:

    team1side = amber     ->  opponent1 is match_team_index 0
    team1side = sapphire  ->  opponent1 is match_team_index 1

Note this is the opposite of the intuitive guess. The point of this script is
to re-test it on the full cache rather than trust a 12 match sample.

The test needs no rosters and no player identity, which is what makes it
usable on editions 1 to 16 where the wiki names no players at all. It joins
purely on hero picks: the wiki lists six heroes per side, our cached match
lists a `hero_id` per player with a `team` of 0 or 1, so the two can be
matched without knowing who anyone is.

Method, per game:

1. Turn the wiki's six hero names for opponent1 into hero IDs.
2. Count how many of those appear on our team 0, and on our team 1.
3. Whichever side scores higher is where opponent1 played. A tie, or an
   equal score, is recorded as unresolved rather than guessed.
4. Compare that answer with what the amber/sapphire rule predicts.

Hero picks are compared as multisets, because a mirror pick of the same hero
on both sides would otherwise be counted once and quietly weaken the signal.

Standard library only.

Usage:
    python scripts/check_side_mapping.py
    python scripts/check_side_mapping.py --verbose
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
from collections import Counter
from pathlib import Path

DEFAULT_GAMES = Path("data/derived/liquipedia-games.json")
DEFAULT_MATCHES = Path("data/matches")
DEFAULT_ASSETS = Path("data/assets")

# The rule under test.
SIDE_RULE = {"amber": 0, "sapphire": 1}


# Wiki shorthands that no amount of normalising will reach. Kept explicit and
# tiny on purpose: each one is a claim about what an editor meant, so it should
# be visible and auditable rather than buried in a regex.
HERO_ALIASES = {
    "mo": "moandkrill",  # #21 EU, one game, the usual shorthand for Mo & Krill
    # #49 NA finals games 2 and 3, where an editor wrote the short name. Both
    # matches were left side-unresolved by the ingest until this was added,
    # because one unknown hero name rejects the whole game rather than
    # resolving on the other five. That refusal is correct: five of six is how
    # a wrong match ID looks too, so the parser must not guess. The fix is to
    # teach it the name, not to lower the bar.
    "geist": "ladygeist",
}


def normalise_hero(name: str) -> str:
    """Fold wiki spelling into the assets spelling.

    Handles the two real divergences generically rather than by lookup table:
    `&` versus `and` (`Mo & Krill`), and a leading article (`The Doorman`).
    Anything else already matches once lowercased and stripped of punctuation.
    """
    text = name.strip().lower().replace("&", "and")
    text = re.sub(r"^the\s+", "", text)
    key = re.sub(r"[^a-z0-9]+", "", text)
    return HERO_ALIASES.get(key, key)


def load_hero_ids(assets: Path) -> dict[str, int]:
    snapshots = sorted(assets.glob("heroes-*.json.gz"))
    if not snapshots:
        raise SystemExit(f"no hero asset snapshot in {assets}")
    heroes = json.loads(gzip.decompress(snapshots[-1].read_bytes()))
    return {normalise_hero(h["name"]): h["id"] for h in heroes if h.get("name")}


def load_match_sides(path: Path) -> dict[int, Counter] | None:
    """Hero ID multiset per match_team_index, from our own cached match."""
    try:
        data = json.loads(gzip.decompress(path.read_bytes()))
    except (OSError, ValueError):
        return None
    players = (data.get("match_info") or {}).get("players") or []
    sides: dict[int, Counter] = {0: Counter(), 1: Counter()}
    for player in players:
        team, hero = player.get("team"), player.get("hero_id")
        if team in (0, 1) and hero is not None:
            sides[team][hero] += 1
    if not sides[0] or not sides[1]:
        return None
    return sides


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--games", type=Path, default=DEFAULT_GAMES)
    parser.add_argument("--matches", type=Path, default=DEFAULT_MATCHES)
    parser.add_argument("--assets", type=Path, default=DEFAULT_ASSETS)
    parser.add_argument("--verbose", action="store_true", help="List every disagreement and gap")
    args = parser.parse_args()

    hero_ids = load_hero_ids(args.assets)
    games = json.loads(args.games.read_text(encoding="utf-8"))["games"]

    counts = Counter()
    unknown_heroes = Counter()
    agree_by_side = Counter()
    disagreements, unresolved, margins = [], [], []

    for game in games:
        counts["wiki games"] += 1
        match_path = args.matches / f"{game['match_id']}.json.gz"
        if not match_path.exists():
            counts["not in our cache"] += 1
            continue
        counts["held"] += 1

        picks = game["team1_heroes"]
        if not all(picks):
            counts["no hero picks on the wiki"] += 1
            continue
        side = game.get("team1side")
        if side not in SIDE_RULE:
            counts["no team1side on the wiki"] += 1
            continue

        sides = load_match_sides(match_path)
        if sides is None:
            counts["our match has no usable teams"] += 1
            continue

        wanted = Counter()
        missing = [h for h in picks if normalise_hero(h) not in hero_ids]
        for hero in missing:
            unknown_heroes[hero] += 1
        if missing:
            counts["hero name not in assets"] += 1
            continue
        for hero in picks:
            wanted[hero_ids[normalise_hero(hero)]] += 1

        # Multiset intersection, so a duplicated hero counts twice.
        score = {index: sum((wanted & sides[index]).values()) for index in (0, 1)}
        counts["comparable"] += 1

        if score[0] == score[1]:
            unresolved.append((game, score))
            counts["unresolved, equal evidence"] += 1
            continue

        observed = 0 if score[0] > score[1] else 1
        predicted = SIDE_RULE[side]
        margins.append(abs(score[0] - score[1]))
        if observed == predicted:
            counts["rule correct"] += 1
            agree_by_side[side] += 1
        else:
            counts["rule WRONG"] += 1
            disagreements.append((game, score, observed, predicted))

    print("Side mapping check: team1side=amber -> index 0, sapphire -> index 1")
    print("=" * 66)
    order = ["wiki games", "not in our cache", "held", "no hero picks on the wiki",
             "no team1side on the wiki", "our match has no usable teams",
             "hero name not in assets", "comparable", "unresolved, equal evidence",
             "rule correct", "rule WRONG"]
    for key in order:
        if counts[key]:
            print(f"  {counts[key]:>4}  {key}")

    decided = counts["rule correct"] + counts["rule WRONG"]
    print()
    if decided:
        print(f"Accuracy: {counts['rule correct']}/{decided} "
              f"({counts['rule correct'] / decided:.2%}) across "
              f"{decided} decidable games")
        strong = sum(1 for m in margins if m >= 4)
        print(f"Evidence strength: median margin {sorted(margins)[len(margins) // 2]} of 6, "
              f"{strong}/{len(margins)} games decided by 4 or more")
        print(f"By side: " + ", ".join(f"{s} {agree_by_side[s]}" for s in sorted(agree_by_side)))
    else:
        print("No decidable games. The rule was not tested.")

    if unknown_heroes:
        print(f"\nHero names not found in assets: "
              f"{', '.join(sorted(unknown_heroes))}")

    if disagreements:
        print(f"\n{len(disagreements)} DISAGREEMENT(S), the rule is not universal:")
        for game, score, observed, predicted in disagreements:
            print(f"  match {game['match_id']} (#{game['edition']} {game['region'].upper()}, "
                  f"{game['stage']}): team1side={game['team1side']} predicts index {predicted}, "
                  f"heroes say {observed} (overlap {score[0]} vs {score[1]})")

    if unresolved and args.verbose:
        print(f"\n{len(unresolved)} unresolved:")
        for game, score in unresolved:
            print(f"  match {game['match_id']} (#{game['edition']} {game['region'].upper()}): "
                  f"overlap {score[0]} vs {score[1]}")

    return 1 if disagreements else 0


if __name__ == "__main__":
    raise SystemExit(main())
