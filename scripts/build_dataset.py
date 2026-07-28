#!/usr/bin/env python3
"""Process every cached match into data/derived/dataset.json.

Reads the raw match cache plus the hand curated layer, joins them, and writes
one derived file. Nothing in data/curated/ is ever written to by this script.

Three rules are enforced structurally rather than by convention:

1. The match team index (0/1) is only ever meaningful inside a single match.
   It is carried on rows so team relative denominators can be computed, and
   it is never used as a join key, a grouping key, or an identity.
2. `winning_team` from the API is the only outcome stored. No win flag is
   persisted at any level. The match history endpoint, whose `match_result`
   field is the winning team index rather than a win flag, is never read.
3. Steam data arrives pre-filtered by scripts/fetch_steam.py. The social
   graph never reaches this script.

Problems are reported, never silently corrected. A match with no curated
night, a player with no curated identity, or a side mapping that contradicts
the roster is surfaced in the report and left alone.

Standard library only.

Usage:
    python scripts/build_dataset.py
    python scripts/build_dataset.py --strict     # non-zero exit if any problem
"""

from __future__ import annotations

import argparse
import gzip
import json
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
BANNED_OUTCOME_KEYS = {"won", "is_win", "win", "result", "match_result", "outcome", "victor"}

# Outside sources whose content carries a licence obligation. Anything curated
# from one of these must name it, so the site generator can render the credit
# the licence requires. Adding a provider here is the only way to make it
# publishable: an unknown provider is an error, not a silent passthrough.
ATTRIBUTION_PROVIDERS = {
    "liquipedia": {
        "name": "Liquipedia",
        "licence": "CC-BY-SA 3.0",
        "licence_url": "https://creativecommons.org/licenses/by-sa/3.0/",
        "home": "https://liquipedia.net/deadlock/",
        "share_alike": True,
    },
}


def normalise_attribution(raw, where: str, report: "Report",
                          sink: dict | None = None) -> dict | None:
    """Validate one curated attribution block and return it normalised.

    Returns None when nothing is claimed, which is the ordinary case for data
    derived only from the match API. A claimed provider we do not know about,
    or a claim with no source URL, is an error: publishing it would mean
    crediting a source we cannot link to.
    """
    if not raw:
        return None
    if isinstance(raw, str):
        raw = {"provider": raw}
    provider = raw.get("provider")
    known = ATTRIBUTION_PROVIDERS.get(provider)
    if known is None:
        report.add("error", "unknown-attribution",
                   f"{where} claims attribution provider {provider!r}, which is not in "
                   f"ATTRIBUTION_PROVIDERS, so its licence terms are unknown")
        return None
    url = raw.get("url")
    if not url:
        report.add("error", "attribution-no-url",
                   f"{where} claims attribution to {known['name']} but gives no source url")
        return None
    out = {"provider": provider, "name": known["name"], "url": url,
           "licence": known["licence"], "licence_url": known["licence_url"],
           "share_alike": known["share_alike"]}
    if sink is not None:
        sink.setdefault(provider, {"provider": provider, "name": known["name"],
                                   "home": known["home"], "licence": known["licence"],
                                   "licence_url": known["licence_url"],
                                   "share_alike": known["share_alike"]})
    return out


class Report:
    """Collects problems by severity. Nothing here alters the data."""

    def __init__(self) -> None:
        self.items: list[tuple[str, str, str]] = []

    def add(self, severity: str, category: str, message: str) -> None:
        self.items.append((severity, category, message))

    def by_severity(self, severity: str) -> list[tuple[str, str, str]]:
        return [i for i in self.items if i[0] == severity]

    def render(self) -> str:
        if not self.items:
            return "No problems found."
        lines = []
        for severity in ("error", "warning", "info"):
            group = self.by_severity(severity)
            if not group:
                continue
            lines.append(f"\n{severity.upper()} ({len(group)})")
            by_cat: dict[str, list[str]] = defaultdict(list)
            for _, category, message in group:
                by_cat[category].append(message)
            for category, messages in sorted(by_cat.items()):
                lines.append(f"  {category}  [{len(messages)}]")
                for message in messages[:12]:
                    lines.append(f"    {message}")
                if len(messages) > 12:
                    lines.append(f"    ... and {len(messages) - 12} more")
        return "\n".join(lines)


def git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None
    except Exception:
        return None


def load_match(path: Path) -> dict:
    return json.loads(gzip.decompress(path.read_bytes()))["match_info"]


def final_damage(player: dict) -> int | None:
    """End of game damage lives only in the stats time series, at max time_stamp_s."""
    stats = player.get("stats")
    if not stats:
        return None
    last = max(stats, key=lambda s: s.get("time_stamp_s", -1))
    return last.get("player_damage")


def assert_no_outcome_flags(node, path: str, report: Report) -> None:
    """Recursively confirm no derived win flag was persisted anywhere."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key.lower() in BANNED_OUTCOME_KEYS:
                report.add("error", "outcome-flag-leaked", f"{path}.{key}")
            assert_no_outcome_flags(value, f"{path}.{key}", report)
    elif isinstance(node, list):
        for index, value in enumerate(node[:200]):
            assert_no_outcome_flags(value, f"{path}[{index}]", report)


def assert_no_social_graph(node, path: str, report: Report) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key.lower() == "friends":
                report.add("error", "social-graph-leaked", f"{path}.{key}")
            assert_no_social_graph(value, f"{path}.{key}", report)
    elif isinstance(node, list):
        for index, value in enumerate(node[:200]):
            assert_no_social_graph(value, f"{path}[{index}]", report)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--matches", type=Path, default=Path("data/matches"))
    parser.add_argument("--curated", type=Path, default=Path("data/curated"))
    parser.add_argument("--steam", type=Path, default=Path("data/assets/steam-profiles.json"))
    parser.add_argument("--out", type=Path, default=Path("data/derived/dataset.json"))
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if any error is reported")
    args = parser.parse_args()

    report = Report()

    # ---- load curated layer ------------------------------------------------
    teams_doc = json.loads((args.curated / "teams.json").read_text(encoding="utf-8"))
    players_doc = json.loads((args.curated / "players.json").read_text(encoding="utf-8"))
    teams = teams_doc.get("teams", {})
    curated_players = players_doc.get("players", {})

    night_files = sorted((args.curated / "nights").glob("*.json"))
    nights = [json.loads(p.read_text(encoding="utf-8")) for p in night_files]

    # match_id -> night, plus duplicate detection
    match_to_night: dict[str, dict] = {}
    match_entry: dict[str, dict] = {}
    for night in nights:
        for entry in night.get("matches", []):
            mid = str(entry.get("match_id"))
            if mid in match_to_night:
                report.add("error", "duplicate-match",
                           f"match {mid} appears in both {match_to_night[mid]['night_id']} and {night['night_id']}")
                continue
            match_to_night[mid] = night
            match_entry[mid] = entry

    # roster lookup: (night_id, team_id) -> {account_id: status}
    rosters: dict[tuple[str, str], dict[str, str]] = {}
    for night in nights:
        for roster in night.get("rosters", []):
            key = (night["night_id"], roster.get("team_id"))
            rosters[key] = {str(p["account_id"]): p.get("status", "starter") for p in roster.get("players", [])}
            if roster.get("team_id") not in teams:
                report.add("error", "undefined-team",
                           f"{night['night_id']} roster references team_id {roster.get('team_id')!r}, not in teams.json")

    steam_by_id: dict[str, dict] = {}
    if args.steam.exists():
        for profile in json.loads(args.steam.read_text(encoding="utf-8")).get("profiles", []):
            steam_by_id[str(profile["account_id"])] = profile
    else:
        report.add("warning", "steam-missing", f"{args.steam} not found, player display data will be absent")

    # ---- ingest matches ----------------------------------------------------
    cached = sorted(args.matches.glob("*.json.gz"))
    out_matches, out_player_matches = [], []
    seen_accounts: set[str] = set()

    for path in cached:
        mid = path.name.split(".")[0]
        info = load_match(path)
        night = match_to_night.get(mid)
        entry = match_entry.get(mid)

        # ---- tournament gate ----------------------------------------------
        # Night Shift is played in custom lobbies, which the API reports as
        # match_mode 2. Anything else is not a tournament game and must not
        # reach the dataset, whatever a wiki bracket claims about it.
        #
        # This exists because two cached matches are wrong match IDs typed on
        # Liquipedia, pointing at unrelated public games. See RETRACTIONS.md
        # entry R2. They stay in the cache on purpose: the cache is a raw
        # record of what the API returned, and those two are the evidence that
        # the wiki can be wrong. The filter belongs here, at the point where
        # raw data becomes a claim about Night Shift.
        #
        # The gate is mode alone, but the finding was not. Both matches were
        # identified by three converging signals: a hero pick overlap of 2 of 6
        # against a corpus where 265 of 273 score 6 of 6, a duration that
        # disagreed with the wiki by 218 and 630 seconds against a corpus where
        # 269 of 276 agree within 2, and match_mode. Mode is used as the gate
        # because it is a single field with no join and no threshold, but it
        # should never be the only thing that catches a bad ID: a wrong ID that
        # happens to point at another custom lobby would pass this and be
        # caught only by the hero pick check in scripts/check_side_mapping.py.
        if info.get("match_mode") != 2:
            report.add("warning", "non-tournament-match",
                       f"match {mid} is match_mode {info.get('match_mode')!r}, not 2, so it is not a "
                       f"custom lobby and not a Night Shift game. Kept in the cache, excluded here")
            continue

        if night is None:
            report.add("warning", "orphan-match",
                       f"match {mid} is cached but assigned to no night, excluded from the dataset")
            continue

        players = info.get("players", [])
        if len(players) != 12:
            report.add("warning", "unexpected-player-count", f"match {mid} has {len(players)} players, expected 12")

        # side mapping, match scoped only
        sides = {}
        for side in entry.get("sides", []):
            idx = side.get("match_team_index")
            if idx not in (0, 1):
                report.add("error", "bad-team-index",
                           f"match {mid} has match_team_index {idx!r}, must be 0 or 1")
                continue
            sides[idx] = side.get("team_id")
        if set(sides) != {0, 1}:
            report.add("error", "incomplete-sides",
                       f"match {mid} does not define both match_team_index 0 and 1")

        for team_id in sides.values():
            if team_id is not None and team_id not in teams:
                report.add("error", "undefined-team",
                           f"match {mid} maps a side to team_id {team_id!r}, not in teams.json")
        if any(v is None for v in sides.values()):
            report.add("warning", "unmapped-side",
                       f"match {mid} has a side with no team_id, team attribution unavailable")

        # ---- side mapping validator ---------------------------------------
        actual = {idx: {str(p["account_id"]) for p in players if p.get("team") == idx} for idx in (0, 1)}
        if all(sides.get(i) for i in (0, 1)):
            straight = sum(len(actual[i] & set(rosters.get((night["night_id"], sides[i]), {}))) for i in (0, 1))
            swapped = sum(len(actual[i] & set(rosters.get((night["night_id"], sides[1 - i]), {}))) for i in (0, 1))
            if straight == 0 and swapped == 0:
                report.add("warning", "side-mapping-uncheckable",
                           f"match {mid} has no roster overlap either way, rosters are probably empty")
            elif swapped > straight:
                report.add("error", "side-mapping-swapped",
                           f"match {mid} roster overlap is {straight}/12 as mapped but {swapped}/12 if swapped, "
                           f"the sides are very likely the wrong way round")

        # ---- date sanity ---------------------------------------------------
        start = info.get("start_time")
        if start and night.get("date"):
            match_day = datetime.fromtimestamp(start, timezone.utc).date()
            night_day = datetime.strptime(night["date"], "%Y-%m-%d").date()
            drift = abs((match_day - night_day).days)
            # The check exists to catch a match filed under the wrong night. It
            # assumes a night is one evening, and for most it is. It is not for
            # every edition: on some, the qualifier was played days before the
            # challenger and final, so a wide spread is the schedule rather than
            # a mistake.
            #
            # Where membership comes from the Liquipedia bracket, the wiki is
            # the authority on which edition a match belongs to and a date
            # cannot overrule it, so this reports rather than accuses. Say that
            # plainly instead of pretending it still validates anything: for
            # those nights it is an observation. The error is kept for hand
            # assigned nights, where it is the only guard there is.
            if drift > 2:
                if night.get("membership_source") == "liquipedia-bracket":
                    report.add("info", "edition-spans-days",
                               f"match {mid} starts {match_day}, {drift} days from the "
                               f"{night_day} start of {night['night_id']}, which ran over "
                               f"more than one day")
                else:
                    report.add("error", "date-drift",
                               f"match {mid} starts {match_day} but night {night['night_id']} is dated {night_day} "
                               f"({drift} days apart)")

        # ---- match level totals, numerator and denominator both stored -----
        totals = {}
        for idx in (0, 1):
            side_players = [p for p in players if p.get("team") == idx]
            damages = [final_damage(p) for p in side_players]
            totals[str(idx)] = {
                "net_worth": sum(p.get("net_worth") or 0 for p in side_players),
                "kills": sum(p.get("kills") or 0 for p in side_players),
                "deaths": sum(p.get("deaths") or 0 for p in side_players),
                "assists": sum(p.get("assists") or 0 for p in side_players),
                "damage": sum(d for d in damages if d is not None),
                "player_count": len(side_players),
            }

        net_worths = [p.get("net_worth") for p in players if p.get("net_worth") is not None]
        out_matches.append({
            "match_id": mid,
            "night_id": night["night_id"],
            "stage": entry.get("stage"),
            "series_label": entry.get("series_label"),
            "game_in_series": entry.get("game_in_series"),
            "start_time": start,
            "duration_s": info.get("duration_s"),
            # The only outcome field. Copied verbatim from the API.
            "winning_team_index": info.get("winning_team"),
            "sides": [{"match_team_index": i, "team_id": sides.get(i)} for i in (0, 1)],
            "totals": totals,
            "lobby": {
                "net_worth_total": sum(net_worths),
                "net_worth_avg": round(sum(net_worths) / len(net_worths), 1) if net_worths else None,
                "player_count": len(players),
            },
        })

        for player in players:
            account_id = str(player.get("account_id"))
            seen_accounts.add(account_id)
            idx = player.get("team")
            team_id = sides.get(idx)
            roster = rosters.get((night["night_id"], team_id), {})
            status = roster.get(account_id)
            if team_id is not None and roster and status is None:
                report.add("warning", "player-not-on-roster",
                           f"match {mid}: account {account_id} played for {team_id} but is not on that night's roster")
            damage = final_damage(player)
            if damage is None:
                report.add("warning", "missing-damage", f"match {mid}: account {account_id} has no player_damage")
            out_player_matches.append({
                "match_id": mid,
                "account_id": account_id,
                "match_team_index": idx,
                "team_id": team_id,
                "roster_status": status,
                "hero_id": player.get("hero_id"),
                "kills": player.get("kills"),
                "deaths": player.get("deaths"),
                "assists": player.get("assists"),
                "net_worth": player.get("net_worth"),
                "damage": damage,
                "last_hits": player.get("last_hits"),
                "denies": player.get("denies"),
            })

    # ---- participation, derived per match ----------------------------------
    # Who played which game is read from the match data, never asserted by a
    # night level roster. A roster says "these six played tonight", which a Bo3
    # with a substitution in game 2 makes false, and the per-game truth is then
    # unrecoverable.
    #
    # This deliberately does NOT resolve which lineup a side was. That needs
    # team identity, where two rosters overlapping five of six means a single
    # stand-in can flip the attribution silently. Participation needs none of
    # it: an account either appears in a match or it does not.
    #
    # Series are keyed by night plus stage plus label, all from the bracket.
    # Grouping by side would need identity, because match_team_index is not
    # stable across the games of a series. Grouping by account does not.
    series_games: dict[tuple, list[dict]] = defaultdict(list)
    for match in out_matches:
        key = (match["night_id"], match.get("stage"), match.get("series_label"))
        series_games[key].append(match)

    played: dict[tuple, set[str]] = defaultdict(set)
    match_series: dict[str, str] = {}
    out_series, out_participation = [], []

    for key, matches in sorted(series_games.items(), key=lambda kv: str(kv[0])):
        night_id, stage, label = key
        series_id = f"{night_id}|{stage or 'unknown'}|{label or 'unknown'}"
        numbers = [m.get("game_in_series") for m in matches if m.get("game_in_series")]
        cached_count = len(matches)
        # The bracket numbers the games, so the highest number is how many were
        # played. If we hold fewer than that, a player missing from the set has
        # two possible explanations and we cannot tell them apart from here.
        expected = max(numbers) if numbers else cached_count
        complete = cached_count >= expected
        if not complete:
            report.add("info", "series-incomplete",
                       f"series {series_id} has {cached_count} cached game(s) but the bracket numbers "
                       f"up to {expected}, so absence from a game cannot be read as being benched")
        out_series.append({
            "series_id": series_id,
            "night_id": night_id,
            "stage": stage,
            "series_label": label,
            "games_cached": cached_count,
            "games_expected": expected,
            "complete": complete,
        })
        for m in matches:
            match_series[m["match_id"]] = series_id

    for row in out_player_matches:
        series_id = match_series.get(row["match_id"])
        row["series_id"] = series_id
        if series_id:
            played[(series_id, row["account_id"])].add(row["match_id"])

    series_by_id = {s["series_id"]: s for s in out_series}
    for (series_id, account_id), match_ids in sorted(played.items()):
        series = series_by_id[series_id]
        count = len(match_ids)
        if not series["complete"]:
            status = "unknown"
        elif count == series["games_cached"]:
            status = "full"
        else:
            status = "partial"
        out_participation.append({
            "series_id": series_id,
            "account_id": account_id,
            "games_played": count,
            "games_in_series": series["games_cached"],
            "series_complete": series["complete"],
            # full    played every game we hold for this series
            # partial played some, so a substitution or a rotation happened
            # unknown the series is incomplete, so absence proves nothing
            "participation": status,
        })

    partials = [p for p in out_participation if p["participation"] == "partial"]
    if partials:
        report.add("info", "partial-participation",
                   f"{len(partials)} account-series where a player appeared in some but not all games "
                   f"of a complete series. These are the observable substitutions")

    # ---- curated night entries pointing at matches we do not have ----------
    cached_ids = {p.name.split(".")[0] for p in cached}
    for mid, night in match_to_night.items():
        if mid not in cached_ids:
            report.add("error", "missing-match",
                       f"night {night['night_id']} lists match {mid}, which is not in the cache")

    # ---- player identity ---------------------------------------------------
    out_players = []
    unmapped, guesses = [], []
    attributions: dict[str, dict] = {}
    for account_id in sorted(seen_accounts, key=int):
        curated = curated_players.get(account_id)
        if curated is None:
            unmapped.append(account_id)
            identified, handle = "unmapped", None
        else:
            identified = curated.get("identified", "guess")
            handle = curated.get("handle")
            if identified == "guess" or not handle:
                guesses.append(account_id)
        steam = steam_by_id.get(account_id, {})
        handle_attr = normalise_attribution(
            (curated or {}).get("handle_attribution"),
            f"player {account_id}", report, attributions)
        out_players.append({
            "account_id": account_id,
            "handle": handle,
            "identified": identified,
            # Which outside source, if any, the handle came from. The site
            # generator refuses to publish an attributable name without
            # rendering the corresponding credit.
            "handle_attribution": handle_attr,
            # Per the review decision, only confirmed and probable get a page.
            "publishable": bool(handle) and identified in ("confirmed", "probable"),
            "steam": {
                "personaname": steam.get("personaname"),
                "profileurl": steam.get("profileurl"),
                "countrycode": steam.get("countrycode"),
                "avatar_local": f"avatars/{account_id}.jpg" if steam.get("avatarmedium") else None,
                "avatar_source": steam.get("avatarmedium"),
            },
        })

    if unmapped:
        report.add("warning", "unmapped-account",
                   f"{len(unmapped)} account(s) play in cached matches but are absent from players.json: "
                   + ", ".join(unmapped[:10]) + (" ..." if len(unmapped) > 10 else ""))
    if guesses:
        report.add("info", "no-player-page",
                   f"{len(guesses)} account(s) are identified:guess or have no handle, so they get no player page "
                   f"and render as a bare account ID")

    for night in nights:
        if night.get("region_confirmed") is False:
            report.add("info", "region-unconfirmed",
                       f"night {night['night_id']} has an unresolved region label, "
                       f"its matches are excluded from region dependent output")
        if not night.get("rosters"):
            report.add("warning", "no-roster", f"night {night['night_id']} has no rosters, team attribution is unavailable")
        for entry in night.get("matches", []):
            if entry.get("stage") is None:
                report.add("warning", "no-stage",
                           f"night {night['night_id']} match {entry.get('match_id')} has no bracket stage")

    dataset = {
        "schema_version": SCHEMA_VERSION,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "generator": "scripts/build_dataset.py",
            "git_commit": git_commit(),
            "matches_cached": len(cached),
            "matches_ingested": len(out_matches),
            "nights_ingested": len(nights),
            "outcome_rule": "winning_team_index is copied from match_info.winning_team. No win flag is stored. "
                            "A player won if match_team_index == winning_team_index.",
            "team_index_rule": "match_team_index is meaningful only within its own match and is never a join key.",
            "tournament_gate": "Only match_mode 2 (custom lobby) is ingested. Other modes stay in the "
                               "cache and are excluded here. See RETRACTIONS.md entry R2.",
            "participation_rule": "participation[] is derived from the match data, never from a night "
                                  "roster. It says who played which game and nothing about which "
                                  "lineup a side was, which needs team identity.",
        },
        "teams": [{"team_id": k, **v,
                   "attribution": normalise_attribution(
                       v.get("attribution"), f"team {k}", report, attributions)}
                  for k, v in sorted(teams.items())],
        "nights": [{**{k: n.get(k) for k in
                       ("night_id", "series", "edition", "region", "region_confirmed",
                        "date", "source")},
                    "attribution": normalise_attribution(
                        n.get("attribution"), f"night {n['night_id']}", report, attributions)}
                   for n in nights],
        # Every distinct source credited anywhere in this dataset. The site
        # generator renders one credit block per entry actually used.
        "attributions": [attributions[k] for k in sorted(attributions)],
        "players": out_players,
        "series": out_series,
        "matches": out_matches,
        "player_matches": out_player_matches,
        "participation": out_participation,
    }

    assert_no_outcome_flags(dataset, "dataset", report)
    assert_no_social_graph(dataset, "dataset", report)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(dataset, indent=2) + "\n", encoding="utf-8")

    errors = report.by_severity("error")
    print(f"Ingested {len(out_matches)} of {len(cached)} cached match(es), "
          f"{len(out_player_matches)} player-match row(s), {len(out_players)} player(s).")
    complete_series = sum(1 for s in out_series if s["complete"])
    by_status: dict[str, int] = defaultdict(int)
    for row in out_participation:
        by_status[row["participation"]] += 1
    print(f"{len(out_series)} series ({complete_series} complete), "
          f"{len(out_participation)} account-series: "
          + ", ".join(f"{v} {k}" for k, v in sorted(by_status.items())))
    print(f"Wrote {args.out} ({args.out.stat().st_size:,} bytes)")
    print(report.render())
    if args.strict and errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
