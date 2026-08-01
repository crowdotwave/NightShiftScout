#!/usr/bin/env python3
"""The leaderboard metrics, computed from dataset.json rather than the live API.

A faithful port of `computeRows` in `index.html`. The console computes these in
the browser from raw API responses; the public site needs the same numbers baked
into static HTML with no fetching. **The formulas must not diverge**, so this
file is written to be read side by side with the JavaScript.

What it does NOT change, and why each matters:

- **Pooled, not averaged per game.** KDA is total kills plus assists over total
  deaths across every game, so one short stomp cannot distort it.
- **Team relative denominators.** Team Share divides a player by their own five
  teammates in that same match, which is what separates "I am the engine of
  this team" from "my team won".
- **Role Score is bucketed by balance patch**, each game scored against its own
  era, falling back to the pooled baseline where an era is too thin. This is the
  one metric a patch genuinely moves, since its baseline is per archetype rather
  than per team.

The one deliberate difference from the console is the eligibility bar, and it
is a caller's argument rather than a constant here. See LEADERBOARD_MIN_GAMES
in build_site.py.

Standard library only. Makes no network requests.
"""

from __future__ import annotations

import bisect
import datetime as dt
import gzip
import json
from collections import defaultdict
from pathlib import Path

# Below this many games in a role's baseline the average is noise, and that
# era falls back to the pooled all-patch baseline. Same value as index.html.
ROLE_BASELINE_MIN_GAMES = 10


def mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def load_patch_boundaries(assets_dir: Path) -> list[float]:
    """Balance patch dates as unix seconds, oldest first."""
    files = sorted(assets_dir.glob("patches-big-days-*.json"))
    if not files:
        return []
    days = json.loads(files[-1].read_text(encoding="utf-8"))["big_days"]
    return sorted(dt.datetime.fromisoformat(d.replace("Z", "+00:00")).timestamp()
                  for d in days)


def load_hero_roles(assets_dir: Path) -> dict[int, str | None]:
    snapshots = sorted(assets_dir.glob("heroes-*.json.gz"))
    if not snapshots:
        return {}
    return {h["id"]: h.get("hero_type")
            for h in json.loads(gzip.decompress(snapshots[-1].read_bytes()))}


def compute_rows(ds: dict, assets_dir: Path) -> list[dict]:
    """One row per account, with every leaderboard number on it."""
    boundaries = load_patch_boundaries(assets_dir)
    role_of = load_hero_roles(assets_dir)
    matches = {m["match_id"]: m for m in ds["matches"]}
    nights = {n["night_id"]: n for n in ds["nights"]}

    def era_of(start_time):
        if not boundaries:
            return None
        index = bisect.bisect_right(boundaries, start_time) - 1
        return boundaries[index] if index >= 0 else None

    # Team relative denominators are per match side, so group there first.
    by_side = defaultdict(list)
    for row in ds["player_matches"]:
        by_side[(row["match_id"], row["match_team_index"])].append(row)

    per_player = defaultdict(list)
    for (match_id, side), rows in by_side.items():
        match = matches[match_id]
        minutes = (match.get("duration_s") or 0) / 60 or None
        lobby_avg_nw = (match.get("lobby") or {}).get("net_worth_avg")
        team_avg_nw = mean([r["net_worth"] for r in rows])
        team_avg_dmg = mean([r["damage"] for r in rows])
        team_kills = sum(r["kills"] for r in rows)
        # Lobby average damage needs both sides, so read it off the stored
        # totals rather than recomputing from this side alone.
        totals = match.get("totals") or {}
        lobby_dmg = sum((totals.get(str(i)) or {}).get("damage") or 0 for i in (0, 1))
        lobby_players = (match.get("lobby") or {}).get("player_count") or 0
        lobby_avg_dmg = lobby_dmg / lobby_players if lobby_players else None
        night = nights.get(match.get("night_id")) or {}

        for r in rows:
            damage = r["damage"]
            per_player[r["account_id"]].append({
                "match_id": match_id,
                "stage": match.get("stage"),
                "night_id": match.get("night_id"),
                "edition": night.get("edition"),
                "region": night.get("region"),
                "date": night.get("date"),
                "start_time": match.get("start_time"),
                "era": era_of(match.get("start_time") or 0),
                "hero_id": r["hero_id"],
                "role": role_of.get(r["hero_id"]),
                "won": r["match_team_index"] == match.get("winning_team_index"),
                "kills": r["kills"], "deaths": r["deaths"], "assists": r["assists"],
                "souls_per_min": r["net_worth"] / minutes if minutes else None,
                "net_worth_share": r["net_worth"] / lobby_avg_nw if lobby_avg_nw else None,
                "team_nw_share": r["net_worth"] / team_avg_nw if team_avg_nw else None,
                "dpm": damage / minutes if minutes and damage is not None else None,
                "damage_share": damage / lobby_avg_dmg if lobby_avg_dmg and damage is not None else None,
                "team_dmg_share": damage / team_avg_dmg if team_avg_dmg and damage is not None else None,
                "kp": (r["kills"] + r["assists"]) / team_kills if team_kills else None,
                "kpd": ((r["kills"] + r["assists"]) / r["deaths"]) if r["deaths"] else None,
            })

    # ---- role baselines, per patch era with a pooled fallback -------------
    pooled_games = defaultdict(list)
    era_games = defaultdict(list)
    for games in per_player.values():
        for g in games:
            if not g["role"]:
                continue
            pooled_games[g["role"]].append(g)
            era_games[(g["era"], g["role"])].append(g)

    def baseline(games):
        base = {k: mean([g[k] for g in games])
                for k in ("team_nw_share", "team_dmg_share", "kp")}
        base["sample_games"] = len(games)
        return base

    pooled_base = {role: baseline(g) for role, g in pooled_games.items()}
    era_base = {key: baseline(g) for key, g in era_games.items()}

    def role_score(game) -> tuple[float | None, bool]:
        """(score, used_pooled_baseline) for one game."""
        if not game["role"]:
            return None, False
        base = era_base.get((game["era"], game["role"]))
        pooled = False
        if not base or base["sample_games"] < ROLE_BASELINE_MIN_GAMES:
            base = pooled_base.get(game["role"])
            pooled = True
        if not base:
            return None, False
        parts = [game[k] / base[k] for k in ("team_nw_share", "team_dmg_share", "kp")
                 if game[k] is not None and base[k]]
        return (mean(parts), pooled) if parts else (None, False)

    rows = []
    for account_id, games in per_player.items():
        wins = [g for g in games if g["won"]]
        losses = [g for g in games if not g["won"]]
        total_kills = sum(g["kills"] for g in games)
        total_deaths = sum(g["deaths"] for g in games)
        total_assists = sum(g["assists"] for g in games)

        scores, used_pooled = [], False
        for g in games:
            score, pooled = role_score(g)
            if score is not None:
                scores.append(score)
                used_pooled = used_pooled or pooled

        role_counts = defaultdict(int)
        hero_counts = defaultdict(int)
        stage_counts = defaultdict(int)
        for g in games:
            if g["role"]:
                role_counts[g["role"]] += 1
            hero_counts[g["hero_id"]] += 1
            stage_counts[g["stage"] or "Other"] += 1

        last = max(games, key=lambda g: g["start_time"] or 0)
        rows.append({
            "account_id": account_id,
            "games": len(games),
            "nights": len({g["night_id"] for g in games}),
            "wins": len(wins),
            "win_rate": len(wins) / len(games) if games else None,
            # Pooled, not an average of per game ratios.
            "pooled_kda": ((total_kills + total_assists) / total_deaths
                           if total_deaths else float(total_kills + total_assists)),
            "total_kills": total_kills, "total_deaths": total_deaths,
            "total_assists": total_assists,
            "avg_souls_per_min": mean([g["souls_per_min"] for g in games]),
            "avg_net_worth_share": mean([g["net_worth_share"] for g in games]),
            "avg_team_nw_share": mean([g["team_nw_share"] for g in games]),
            "team_share_wins": mean([g["team_nw_share"] for g in wins]) if wins else None,
            "team_share_losses": mean([g["team_nw_share"] for g in losses]) if losses else None,
            "avg_dpm": mean([g["dpm"] for g in games]),
            "avg_team_dmg_share": mean([g["team_dmg_share"] for g in games]),
            "avg_kp": mean([g["kp"] for g in games]),
            "role_score": mean(scores) if scores else None,
            "role_score_pooled_baseline": used_pooled,
            "primary_role": max(role_counts, key=role_counts.get) if role_counts else None,
            "role_counts": dict(role_counts),
            "stage_counts": dict(stage_counts),
            "heroes": [h for h, _ in sorted(hero_counts.items(), key=lambda kv: -kv[1])],
            "last_night_id": last["night_id"],
            "last_date": last["date"],
        })
    rows.sort(key=lambda r: -(r["role_score"] or -1))
    return rows


# ---------------------------------------------------------------------------
# Early game, the lane phase view
# ---------------------------------------------------------------------------
#
# Raw early numbers are not comparable across heroes: a pooled early damage
# board would rank heroes rather than players. Every figure below is compared
# to the same hero at the same minute, which removes that and removes the
# support confound with it, since the hero encodes the role.
#
# What is measured, and why each is here or not, from the reliability work in
# scripts/measure_stage_weighting.py's sibling analysis:
#
#   hero damage   split-half reliability 0.69 at 9 minutes, correlates +0.15
#                 with the full match Role Score, and a team's leave-one-out
#                 rating predicts the winner 61.2% of the time. Stable, new,
#                 and it means something. This is the primary early stat.
#   denies        reliability 0.80, correlation with Role Score +0.16, so it
#                 is the most stable and most independent thing here. But a
#                 side ahead on denies wins only 50.9% of matches, so we do
#                 NOT claim it predicts winning. Shown, never headlined.
#   kills         reliability 0.40 and zero on 44% of games. Card colour only,
#                 never a metric.
#   assists       reliability at 9 minutes is -0.06. Dropped entirely.
#   souls         reliable, but correlates +0.54 with Role Score, so it mostly
#                 repeats what the board already says. Kept off this surface.
#   last hits     the most reliable stat measured, 0.82, and deliberately
#                 unused. See the domain facts section of CLAUDE.md: last hits
#                 favour whoever is already ahead, so it is a consequence of
#                 winning the lane rather than evidence of skill. A stable
#                 number measuring the wrong thing is still the wrong thing.

EARLY_MIN_HERO_GAMES = 30      # heroes below this have no trustworthy baseline
EARLY_MIN_PLAYER_GAMES = 10    # the bar the reliability figures were measured at


def compute_early(ds: dict) -> dict:
    """Hero normalised lane phase figures, plus the lane matchup record."""
    matches = {m["match_id"]: m for m in ds["matches"]}
    rows = [r for r in ds["player_matches"] if r.get("early")]

    hero_games = defaultdict(list)
    for r in rows:
        hero_games[r["hero_id"]].append(r)
    eligible_heroes = {h for h, v in hero_games.items() if len(v) >= EARLY_MIN_HERO_GAMES}

    # Baselines are plain averages, stored with their sample size so a card can
    # always show what it compared against.
    baselines = {}
    for hero in eligible_heroes:
        games = hero_games[hero]
        baselines[hero] = {
            "games": len(games),
            "damage": mean([g["early"]["damage"] for g in games]),
            "denies": mean([g["early"]["denies"] for g in games]),
        }

    def spread(hero, key):
        values = [g["early"][key] for g in hero_games[hero]]
        average = mean(values)
        variance = mean([(v - average) ** 2 for v in values]) or 1.0
        return variance ** 0.5

    scored = []
    for r in rows:
        hero = r["hero_id"]
        if hero not in eligible_heroes:
            continue
        base = baselines[hero]
        sd = spread(hero, "damage") or 1.0
        scored.append({
            **r,
            "hero_baseline_damage": base["damage"],
            "hero_baseline_denies": base["denies"],
            "hero_baseline_games": base["games"],
            "damage_vs_hero": r["early"]["damage"] - base["damage"],
            "damage_z": (r["early"]["damage"] - base["damage"]) / sd,
            "denies_vs_hero": r["early"]["denies"] - base["denies"],
        })

    by_player = defaultdict(list)
    for r in scored:
        by_player[r["account_id"]].append(r)
    ratings = {}
    for account_id, games in by_player.items():
        if len(games) < EARLY_MIN_PLAYER_GAMES:
            continue
        ratings[account_id] = {
            "games": len(games),
            "damage_z": mean([g["damage_z"] for g in games]),
            "damage": mean([g["early"]["damage"] for g in games]),
            "baseline_damage": mean([g["hero_baseline_damage"] for g in games]),
            "denies": mean([g["early"]["denies"] for g in games]),
            "baseline_denies": mean([g["hero_baseline_denies"] for g in games]),
        }

    # ---- lane matchups -----------------------------------------------------
    # A lane is 2v2 on every cached match, so this needs no rosters. The two
    # players on a side share one outcome and the cards say so: nothing here
    # attributes a lane to one of the pair.
    lanes = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r.get("assigned_lane") is not None:
            lanes[(r["match_id"], r["assigned_lane"])][r["match_team_index"]].append(r)

    lane_rows, ahead_by_match = [], defaultdict(list)
    for (match_id, lane), sides in lanes.items():
        if set(sides) != {0, 1}:
            continue
        souls = {i: sum(x["early"]["net_worth"] for x in sides[i]) for i in (0, 1)}
        if souls[0] == souls[1]:
            continue
        ahead = 0 if souls[0] > souls[1] else 1
        winner = matches[match_id].get("winning_team_index")
        ahead_by_match[match_id].append(ahead)
        lane_rows.append({
            "match_id": match_id, "lane": lane, "ahead": ahead,
            "margin": abs(souls[0] - souls[1]),
            "souls": souls, "winner": winner,
            "lost_anyway": ahead != winner,
            "accounts": [x["account_id"] for x in sides[ahead]],
        })

    swept = [m for m, a in ahead_by_match.items() if len(a) == 3 and len(set(a)) == 1]
    swept_lost = [m for m in swept
                  if ahead_by_match[m][0] != matches[m].get("winning_team_index")]

    return {
        "timestamp_s": 540,
        "baselines": baselines,
        "hero_count": len(eligible_heroes),
        "scored": scored,
        "ratings": ratings,
        "lanes": lane_rows,
        "lanes_lost_anyway": [l for l in lane_rows if l["lost_anyway"]],
        "swept_lanes": swept,
        "swept_and_lost": swept_lost,
    }
