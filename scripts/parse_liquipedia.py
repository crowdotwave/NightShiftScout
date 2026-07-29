#!/usr/bin/env python3
"""Parse cached Liquipedia wikitext into one row per game.

Reads `data/liquipedia/pages/*.wiki.gz` and writes
`data/derived/liquipedia-games.json`, with a row per `{{Map}}` carrying:

    match_id, edition, region, stage, bestof, game_in_series,
    team1, team2, team1side, team2side, team1_heroes[6], team2_heroes[6],
    winner, length_s, source_url

Nothing here needs rosters, player identity, or our own match cache. That is
the point: side mapping and bracket stage are computable for every game the
wiki lists an ID for, including editions 1 to 16 where no rosters exist.

**Templates nest, so this does not use regex to find them.** `{{Match}}`
contains `{{Map}}` contains nothing, but `{{TeamOpponent}}` can contain
`{{PlayerSubstitutions}}` containing `{{Substitution}}`, and a regex for
`\\{\\{Map.*?\\}\\}` silently truncates at the first inner `}}`. Parameters are
split at brace depth zero for the same reason.

Parsing wikitext is scraping, and it will break when editors change format.
So this fails loudly: a page that yields no bracket, a `{{Map}}` with a match
ID but not six heroes a side, or an unresolvable stage are all reported. A
silently dropped game is far worse than a noisy one, because the result still
looks plausible.

Stage resolution, in the order the notes established:

1. `R<n>header=` on the bracket, most reliable where present.
2. The bracket template name, which is structural: `Bracket/2L2D` is
   Qualifier, Challenger, Finals; `Bracket/2L1D` is Challenger, Finals.
3. An HTML comment such as `<!-- Finals -->` above the match, which on a few
   `Bracket/2` pages is the only marker there is.

Standard library only.

Usage:
    python scripts/parse_liquipedia.py
    python scripts/parse_liquipedia.py --out out/games.json
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import urllib.parse
from pathlib import Path

DEFAULT_PAGES = Path("data/liquipedia/pages")
DEFAULT_OUT = Path("data/derived/liquipedia-games.json")

# Round to stage, keyed by bracket template. Structural, so it covers pages
# that carry no headers at all.
BRACKET_ROUNDS = {
    "Bracket/2L2D": {1: "qualifier", 2: "challenger", 3: "final"},
    "Bracket/2L1D": {1: "challenger", 2: "final"},
    "Bracket/2": {1: "final"},
}

STAGE_WORDS = {
    "qualifier": "qualifier", "qualifiers": "qualifier", "qualification": "qualifier",
    "challenger": "challenger", "challengers": "challenger",
    "final": "final", "finals": "final", "grand final": "final", "grand finals": "final",
    "semifinal": "semifinal", "semifinals": "semifinal",
}


def normalise_stage(raw: str | None) -> str | None:
    if not raw:
        return None
    return STAGE_WORDS.get(re.sub(r"\s+", " ", raw).strip().lower())


def match_brace(text: str, start: int) -> int:
    """Index just past the `}}` that closes the `{{` at `start`.

    Returns -1 if the braces never balance, which means the page is truncated
    or malformed and the caller should complain rather than guess.
    """
    depth = 0
    i = start
    while i < len(text) - 1:
        pair = text[i:i + 2]
        if pair == "{{":
            depth += 1
            i += 2
            continue
        if pair == "}}":
            depth -= 1
            i += 2
            if depth == 0:
                return i
            continue
        i += 1
    return -1


def split_params(body: str) -> list[str]:
    """Split a template body on `|` at brace depth zero.

    `[[a|b]]` link syntax also uses a pipe, so square brackets are tracked
    too. Without that, a piped wiki link would split one parameter into two.
    """
    parts, current, depth, square = [], [], 0, 0
    i = 0
    while i < len(body):
        pair = body[i:i + 2]
        if pair == "{{":
            depth += 1
            current.append(pair)
            i += 2
            continue
        if pair == "}}":
            depth -= 1
            current.append(pair)
            i += 2
            continue
        if pair == "[[":
            square += 1
            current.append(pair)
            i += 2
            continue
        if pair == "]]":
            square -= 1
            current.append(pair)
            i += 2
            continue
        char = body[i]
        if char == "|" and depth == 0 and square == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
        i += 1
    parts.append("".join(current))
    return parts


def parse_params(body: str) -> tuple[list[str], dict[str, str]]:
    """Return (positional, named) for a template body, name already removed."""
    positional, named = [], {}
    for part in split_params(body):
        if "=" in part:
            key, _, value = part.partition("=")
            key = key.strip()
            # A '=' inside a nested template is not a parameter separator.
            if key and "{{" not in key and "\n" not in key:
                named[key] = value.strip()
                continue
        stripped = part.strip()
        if stripped:
            positional.append(stripped)
    return positional, named


def find_template(text: str, start: int, name: str) -> tuple[int, int, str] | None:
    """Locate the next `{{name...}}` at or after `start`."""
    pattern = re.compile(r"\{\{" + re.escape(name) + r"\b")
    found = pattern.search(text, start)
    if not found:
        return None
    end = match_brace(text, found.start())
    if end == -1:
        return None
    return found.start(), end, text[found.start() + 2:end - 2]


def opponent_name(raw: str) -> str | None:
    """First positional argument of {{TeamOpponent}} or {{Opponent}}.

    Both spellings are in current use, which the notes flag explicitly.
    """
    for name in ("TeamOpponent", "Opponent"):
        found = find_template(raw, 0, name)
        if found:
            _, _, body = found
            positional, _ = parse_params(body[len(name):])
            if positional:
                return positional[0]
    return None


def length_to_seconds(raw: str | None) -> int | None:
    if not raw or ":" not in raw:
        return None
    try:
        minutes, seconds = raw.strip().split(":")
        return int(minutes) * 60 + int(seconds)
    except ValueError:
        return None


def parse_page(title: str, text: str, problems: list[str]) -> list[dict]:
    """Every game on one edition page."""
    parts = title.split("/")
    edition, region = int(parts[1]), parts[2].lower()
    source_url = f"https://liquipedia.net/deadlock/{urllib.parse.quote(title.replace(' ', '_'))}"
    rows: list[dict] = []

    cursor, brackets = 0, 0
    while True:
        found = find_template(text, cursor, "Bracket")
        if not found:
            break
        start, end, body = found
        cursor = end
        brackets += 1
        positional, named = parse_params(body[len("Bracket"):])
        template = positional[0] if positional else ""
        rounds = BRACKET_ROUNDS.get(template, {})

        for key, value in named.items():
            slot = re.fullmatch(r"R(\d+)M(\d+)", key)
            if not slot or "{{Match" not in value:
                continue
            round_no, match_no = int(slot.group(1)), int(slot.group(2))

            # Stage, best source first.
            stage = (normalise_stage(named.get(f"R{round_no}M{match_no}header"))
                     or normalise_stage(named.get(f"R{round_no}header"))
                     or rounds.get(round_no))
            if not stage:
                # Last resort: the nearest HTML comment above this key.
                anchor = text.find(f"|{key}=", start, end)
                if anchor != -1:
                    comments = re.findall(r"<!--\s*(.*?)\s*-->", text[start:anchor])
                    if comments:
                        stage = normalise_stage(comments[-1])
            if not stage:
                problems.append(f"{title} {key}: stage unresolved (bracket {template or '?'})")

            match_found = find_template(value, 0, "Match")
            if not match_found:
                continue
            _, _, match_body = match_found
            _, match_named = parse_params(match_body[len("Match"):])
            team1 = opponent_name(match_named.get("opponent1", ""))
            team2 = opponent_name(match_named.get("opponent2", ""))
            bestof = match_named.get("bestof")

            for map_key, map_value in sorted(match_named.items()):
                if not re.fullmatch(r"map\d+", map_key) or "{{Map" not in map_value:
                    continue
                map_found = find_template(map_value, 0, "Map")
                if not map_found:
                    continue
                _, _, map_body = map_found
                _, game = parse_params(map_body[len("Map"):])
                match_id = (game.get("matchid") or "").strip()
                if not match_id:
                    continue

                heroes1 = [game.get(f"t1h{i}") for i in range(1, 7)]
                heroes2 = [game.get(f"t2h{i}") for i in range(1, 7)]
                if not match_id.isdigit() or len(match_id) != 8:
                    problems.append(f"{title} {key} {map_key}: malformed matchid {match_id!r}")
                    continue
                for label, picks in (("t1", heroes1), ("t2", heroes2)):
                    if sum(1 for h in picks if h) != 6:
                        problems.append(
                            f"{title} {key} {map_key} (match {match_id}): "
                            f"{label} has {sum(1 for h in picks if h)} of 6 heroes")

                rows.append({
                    "match_id": match_id,
                    "edition": edition,
                    "region": region,
                    "stage": stage,
                    "bestof": int(bestof) if (bestof or "").isdigit() else None,
                    "game_in_series": int(map_key[3:]),
                    "team1": team1,
                    "team2": team2,
                    "team1side": (game.get("team1side") or "").strip().lower() or None,
                    "team2side": (game.get("team2side") or "").strip().lower() or None,
                    "team1_heroes": [h.strip().lower() if h else None for h in heroes1],
                    "team2_heroes": [h.strip().lower() if h else None for h in heroes2],
                    "winner": int(game["winner"]) if (game.get("winner") or "").isdigit() else None,
                    "length_s": length_to_seconds(game.get("length")),
                    "source_url": source_url,
                })

    if brackets == 0:
        problems.append(f"{title}: no bracket template found on the page")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pages", type=Path, default=DEFAULT_PAGES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    # The cache directory also holds player pages, which carry steam64ID and no
    # bracket. Only edition pages are parsed here. Without this filter a player
    # page reaches parse_page and its title fails to split into three parts,
    # which is how this crashed the first time publish.py ran end to end.
    files = sorted(p for p in args.pages.glob("*.wiki.gz")
                   if p.name.startswith("Deadlock_Night_Shift__"))
    if not files:
        parser.error(f"no cached edition pages in {args.pages}, "
                     f"run scripts/fetch_liquipedia.py first")

    problems: list[str] = []
    rows: list[dict] = []
    for path in files:
        title = path.name[: -len(".wiki.gz")].replace("__", "/").replace("_", " ")
        text = gzip.decompress(path.read_bytes()).decode("utf-8")
        rows.extend(parse_page(title, text, problems))

    rows.sort(key=lambda r: (r["edition"], r["region"], r["match_id"]))
    duplicates = len(rows) - len({r["match_id"] for r in rows})

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({
        "schema_version": 1,
        "source": "https://liquipedia.net/deadlock/",
        "license": "CC-BY-SA 3.0",
        "attribution": "Bracket data from Liquipedia, https://liquipedia.net/deadlock/, CC-BY-SA 3.0",
        "note": "Derived from data/liquipedia/pages/. Regenerate with scripts/parse_liquipedia.py.",
        "games": rows,
    }, indent=2) + "\n", encoding="utf-8")

    sided = sum(1 for r in rows if r["team1side"])
    staged = sum(1 for r in rows if r["stage"])
    full_picks = sum(1 for r in rows
                     if all(r["team1_heroes"]) and all(r["team2_heroes"]))
    print(f"{len(files)} page(s) parsed, {len(rows)} game(s) with a match ID")
    print(f"  {sided} ({sided / len(rows):.0%}) carry team1side")
    print(f"  {staged} ({staged / len(rows):.0%}) resolved a bracket stage")
    print(f"  {full_picks} ({full_picks / len(rows):.0%}) have all twelve hero picks")
    print(f"  {duplicates} duplicate match ID(s)")
    print(f"Wrote {args.out}")
    if problems:
        print(f"\n{len(problems)} problem(s):")
        for problem in problems[:40]:
            print(f"  {problem}")
        if len(problems) > 40:
            print(f"  ... and {len(problems) - 40} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
