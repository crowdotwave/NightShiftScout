#!/usr/bin/env python3
"""Measure whether stage weighting would change the leaderboard at all.

Before building a correction, find out if it corrects anything. The format
bias is real and documented: established teams play fewer, harder games while
newcomers accumulate easy qualifier stomps, which inflates newcomer averages.
The proposed fix is to weight a game by its bracket stage. The question this
answers is whether that moves any rank enough to be worth the machinery, or
whether it is a correction to three decimal places.

The ranking metric is **Role Score**, because that is what the app sorts by
and it is the one metric with a per-archetype baseline rather than a purely
team-relative one. It is reproduced here exactly as `index.html` computes it,
including patch era bucketing and the pooled fallback for thin eras, so this
measures the real leaderboard rather than a simplified stand-in.

Weighted Role Score is the same per-game scores combined with a weighted mean
instead of a flat one. Several weight schemes are tried, from mild to
deliberately extreme, because a correction that only bites under implausible
weights is not a correction worth shipping.

Also prints each player's **stage mix**, which is the alternative to weighting:
show the arithmetic and let the reader judge, rather than adjusting the number
behind the scenes.

Standard library only. Makes no network requests.

Usage:
    python scripts/measure_stage_weighting.py
"""

from __future__ import annotations

import argparse
import bisect
import gzip
import json
from collections import defaultdict
from pathlib import Path

DEFAULT_MIN_GAMES = 3
ROLE_BASELINE_MIN_GAMES = 10

# Mild is a plausible shipping choice, strong is aggressive, extreme is past
# anything defensible and is here to bound the effect: if ranks barely move
# even under extreme, weighting cannot matter.
WEIGHT_SCHEMES = {
    "mild":    {"Qualifier": 0.85, "Challenger": 1.00, "Finals": 1.15},
    "strong":  {"Qualifier": 0.60, "Challenger": 1.00, "Finals": 1.40},
    "extreme": {"Qualifier": 0.25, "Challenger": 1.00, "Finals": 2.00},
}


def mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def spearman(rank_a: dict, rank_b: dict) -> float:
    """Rank correlation over the shared keys. 1.0 means identical ordering."""
    keys = sorted(set(rank_a) & set(rank_b))
    n = len(keys)
    if n < 2:
        return 1.0
    d2 = sum((rank_a[k] - rank_b[k]) ** 2 for k in keys)
    return 1 - (6 * d2) / (n * (n ** 2 - 1))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", type=Path, default=Path("data/derived/dataset.json"))
    parser.add_argument("--assets", type=Path, default=Path("data/assets"))
    parser.add_argument("--min-games", type=int, default=DEFAULT_MIN_GAMES)
    args = parser.parse_args()

    ds = json.loads(args.dataset.read_text(encoding="utf-8"))
    snapshots = sorted(args.assets.glob("heroes-*.json.gz"))
    heroes = json.loads(gzip.decompress(snapshots[-1].read_bytes())) if snapshots else []
    role_of = {h["id"]: h.get("hero_type") for h in heroes}

    patch_files = sorted(args.assets.glob("patches-big-days-*.json"))
    boundaries = sorted(
        __import__("datetime").datetime.fromisoformat(d.replace("Z", "+00:00")).timestamp()
        for d in json.loads(patch_files[-1].read_text(encoding="utf-8"))["big_days"]
    ) if patch_files else []

    def era_of(start_time):
        if not boundaries:
            return None
        i = bisect.bisect_right(boundaries, start_time) - 1
        return boundaries[i] if i >= 0 else None

    matches = {m["match_id"]: m for m in ds["matches"]}

    # ---- per game metrics, exactly as index.html computes them -------------
    by_match_side = defaultdict(list)
    for row in ds["player_matches"]:
        by_match_side[(row["match_id"], row["match_team_index"])].append(row)

    games_by_account = defaultdict(list)
    for (match_id, side), rows in by_match_side.items():
        match = matches[match_id]
        team_nw = mean([r["net_worth"] for r in rows])
        team_dmg = mean([r["damage"] for r in rows])
        team_kills = sum(r["kills"] for r in rows)
        for r in rows:
            games_by_account[r["account_id"]].append({
                "match_id": match_id,
                "stage": match.get("stage"),
                "era": era_of(match["start_time"]),
                "role": role_of.get(r["hero_id"]),
                "team_nw_share": r["net_worth"] / team_nw if team_nw else None,
                "team_dmg_share": r["damage"] / team_dmg if team_dmg else None,
                "kp": (r["kills"] + r["assists"]) / team_kills if team_kills else None,
            })

    # ---- role baselines, per patch era with a pooled fallback -------------
    pooled = defaultdict(list)
    per_era = defaultdict(list)
    for games in games_by_account.values():
        for g in games:
            if not g["role"]:
                continue
            pooled[g["role"]].append(g)
            per_era[(g["era"], g["role"])].append(g)

    def baseline(games):
        return {k: mean([g[k] for g in games]) for k in ("team_nw_share", "team_dmg_share", "kp")} \
               | {"n": len(games)}

    pooled_base = {role: baseline(g) for role, g in pooled.items()}
    era_base = {key: baseline(g) for key, g in per_era.items()}

    def score(g):
        if not g["role"]:
            return None
        base = era_base.get((g["era"], g["role"]))
        if not base or base["n"] < ROLE_BASELINE_MIN_GAMES:
            base = pooled_base.get(g["role"])
        if not base:
            return None
        parts = [g[k] / base[k] for k in ("team_nw_share", "team_dmg_share", "kp")
                 if g[k] is not None and base[k]]
        return mean(parts) if parts else None

    # ---- rank unweighted, then under each scheme --------------------------
    eligible = {}
    for account_id, games in games_by_account.items():
        if len(games) < args.min_games:
            continue
        scored = [(g, score(g)) for g in games]
        scored = [(g, s) for g, s in scored if s is not None]
        if not scored:
            continue
        eligible[account_id] = scored

    handles = {p["account_id"]: (p.get("handle") or p["account_id"]) for p in ds["players"]}

    def ranks_for(weights):
        values = {}
        for account_id, scored in eligible.items():
            if weights is None:
                values[account_id] = mean([s for _, s in scored])
            else:
                total = sum(weights.get(g["stage"], 1.0) for g, _ in scored)
                values[account_id] = sum(weights.get(g["stage"], 1.0) * s
                                         for g, s in scored) / total if total else None
        order = sorted(values, key=lambda a: -values[a])
        return {a: i + 1 for i, a in enumerate(order)}, values

    base_ranks, base_values = ranks_for(None)

    print(f"Leaderboard: {len(eligible)} players with at least {args.min_games} games, "
          f"ranked by Role Score")
    stage_counts = defaultdict(int)
    for games in games_by_account.values():
        for g in games:
            stage_counts[g["stage"]] += 1
    total_pg = sum(stage_counts.values())
    print("Stage mix across all player-games: "
          + ", ".join(f"{k} {v} ({100*v/total_pg:.0f}%)"
                      for k, v in sorted(stage_counts.items(), key=lambda kv: -kv[1])))
    print()

    for name, weights in WEIGHT_SCHEMES.items():
        ranks, values = ranks_for(weights)
        moves = {a: abs(ranks[a] - base_ranks[a]) for a in base_ranks}
        moved = [a for a, m in moves.items() if m > 0]
        big = [a for a, m in moves.items() if m >= 3]
        top10_before = {a for a, r in base_ranks.items() if r <= 10}
        top10_after = {a for a, r in ranks.items() if r <= 10}
        print(f"--- {name}  {weights}")
        print(f"  Spearman correlation with unweighted : {spearman(base_ranks, ranks):.4f}")
        print(f"  players whose rank moves at all      : {len(moved)} of {len(base_ranks)}")
        print(f"  players moving 3 or more places      : {len(big)}")
        print(f"  largest single move                  : {max(moves.values())} places")
        print(f"  top 10 membership changes            : {len(top10_before ^ top10_after) // 2}")
        biggest = sorted(moves, key=lambda a: -moves[a])[:3]
        for a in biggest:
            if moves[a] == 0:
                continue
            print(f"    {handles.get(a, a)[:18]:<18} rank {base_ranks[a]} -> {ranks[a]} "
                  f"(score {base_values[a]:.3f} -> {values[a]:.3f})")
        print()

    # ---- the alternative: show the mix rather than adjust the number ------
    print("Stage mix for the top 15 unweighted, which is what a row would show:")
    print(f"  {'player':<20}{'rank':>5}{'games':>7}{'qual':>7}{'chal':>7}{'final':>7}")
    for account_id in sorted(base_ranks, key=lambda a: base_ranks[a])[:15]:
        games = games_by_account[account_id]
        counts = defaultdict(int)
        for g in games:
            counts[g["stage"]] += 1
        print(f"  {handles.get(account_id, account_id)[:19]:<20}{base_ranks[account_id]:>5}"
              f"{len(games):>7}{counts['Qualifier']:>7}{counts['Challenger']:>7}{counts['Finals']:>7}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
