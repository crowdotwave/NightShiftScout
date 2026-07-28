#!/usr/bin/env python3
"""Parse Liquipedia rosters out of the cached edition wikitext.

Writes `data/derived/liquipedia-rosters.json`, one row per rostered player per
edition page:

    edition, region, team, handle, page_title, role, status, source_url

`role` is `player` or `staff`, and staff are kept rather than dropped so a
coach is never mistaken for a missing player later. `status` carries `sub`
where the wiki flags a substitute.

Rosters live inside `{{TeamOpponent|<team>|players={{Persons|{{Person|...}}}}}}`.
**Templates nest**, so this reuses the brace matching in `parse_liquipedia.py`
rather than a regex: a naive `\\{\\{Person.*?\\}\\}` truncates at the first inner
`}}` and a fixed size window silently pulls players from the next team.

Note `{{Opponent|...}}` also appears, in prize pools and awards, wrapping a
single name that is not a roster. Only `{{TeamOpponent}}` is read here.

**Handle case is not identity.** MediaWiki capitalises the first letter of a
title, so `arctic` and `Arctic` are the same page. The `page_title` column
carries the capitalised form for joining; `handle` keeps what the page wrote.

Standard library only. Makes no network requests.

Usage:
    python scripts/parse_rosters.py
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
from pathlib import Path

import parse_liquipedia as lq

PAGE_NAME = re.compile(r"Deadlock_Night_Shift__(\d+)__(EU|NA)\.wiki\.gz")
SOURCE_BASE = "https://liquipedia.net/deadlock/Deadlock_Night_Shift"


def page_title(handle: str) -> str:
    """MediaWiki capitalises the first letter, so this is the join key."""
    handle = handle.strip()
    return handle[:1].upper() + handle[1:] if handle else handle


def parse_rosters(text: str, edition: int, region: str, problems: list[str]) -> list[dict]:
    """Both `{{TeamOpponent}}` and `{{Opponent}}` carry rosters.

    Newer pages use `TeamOpponent`, older ones use `Opponent`, and both forms
    are in current use. `Opponent` also appears in prize pools and award slots
    wrapping a single name with no `players=`, which is not a roster and is
    skipped rather than reported: it is the ordinary case, not a defect.
    """
    rows: list[dict] = []
    for template in ("TeamOpponent", "Opponent"):
        cursor = 0
        while True:
            found = lq.find_template(text, cursor, template)
            if not found:
                break
            start, end, body = found
            cursor = end
            # find_template returns the body with the template name still on
            # the front, which parse_params would otherwise read as the first
            # positional argument. opponent_name() in parse_liquipedia strips
            # it the same way.
            positional, named = lq.parse_params(body[len(template):])
            players_body = named.get("players")
            if not players_body:
                continue
            team = positional[0].strip() if positional else None
            if not team:
                problems.append(f"#{edition}/{region.upper()}: a {template} has a roster but no team name")
                continue

            inner = 0
            while True:
                person = lq.find_template(players_body, inner, "Person")
                if not person:
                    break
                p_start, p_end, p_body = person
                inner = p_end
                p_positional, p_named = lq.parse_params(p_body[len("Person"):])
                handle = p_positional[0].strip() if p_positional else None
                if not handle:
                    problems.append(f"#{edition}/{region.upper()} {team}: a Person has no handle")
                    continue
                rows.append({
                    "edition": edition,
                    "region": region,
                    "team": team,
                    "handle": handle,
                    "page_title": page_title(handle),
                    "role": "staff" if p_named.get("type") == "staff" else "player",
                    "status": p_named.get("status"),
                    "source_url": f"{SOURCE_BASE}/{edition}/{region.upper()}",
                })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pages", type=Path, default=Path("data/liquipedia/pages"))
    parser.add_argument("--out", type=Path, default=Path("data/derived/liquipedia-rosters.json"))
    args = parser.parse_args()

    rows: list[dict] = []
    problems: list[str] = []
    pages = 0
    for path in sorted(args.pages.glob("*.wiki.gz")):
        matched = PAGE_NAME.match(path.name)
        if not matched:
            continue
        pages += 1
        edition, region = int(matched.group(1)), matched.group(2).lower()
        text = gzip.decompress(path.read_bytes()).decode("utf-8")
        rows.extend(parse_rosters(text, edition, region, problems))

    players = [r for r in rows if r["role"] == "player"]
    titles = sorted({r["page_title"] for r in players})
    rostered_pages = {(r["edition"], r["region"]) for r in players}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({
        "schema_version": 1,
        "source": "https://liquipedia.net/deadlock/",
        "license": "CC-BY-SA 3.0",
        "attribution": "Content from Liquipedia, https://liquipedia.net/deadlock/, CC-BY-SA 3.0",
        "note": "Parsed from cached wikitext by scripts/parse_rosters.py. Handles are as "
                "written; page_title is the capitalised MediaWiki join key.",
        "player_page_titles": titles,
        "rows": rows,
    }, indent=2) + "\n", encoding="utf-8")

    print(f"{pages} page(s) parsed, {len(rows)} roster row(s)")
    print(f"  {len(players)} player, {len(rows) - len(players)} staff")
    print(f"  {len(titles)} distinct player page title(s)")
    print(f"  {len({r['team'] for r in players})} distinct team name(s)")
    print(f"  rosters present on {len(rostered_pages)} of {pages} page(s)")
    print(f"  {sum(1 for r in players if r['status'] == 'sub')} row(s) flagged as a substitute")
    print(f"wrote {args.out}")
    if problems:
        print(f"\n{len(problems)} problem(s):")
        for line in problems[:20]:
            print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
