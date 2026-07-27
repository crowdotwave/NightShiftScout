#!/usr/bin/env python3
"""Generate the static site from data/derived/dataset.json.

Emits exactly one page type: a player page at /players/<account_id>/.

Plain HTML and CSS. No framework, no build step, no JavaScript, and no
client side fetching: every number is baked in at generation time.

Three rules this generator is built around:

1. **Uncurated accounts are the normal state, not an error.** New accounts
   appear every week before anyone has time to identify them. They render as
   a bare account ID that links nowhere. A match is never dropped and the
   build never fails because a participant is uncurated.
2. **A guessed identity is never published.** Only `confirmed` and `probable`
   players get a page. Everyone else is a number.
3. **No coined metric names.** Stats are phrased so they need no glossary:
   "24% of team damage", not "Damage Share 1.21x". Every percentage is shown
   with the two integers it came from.

Win and loss are computed here, at render time, from
`match_team_index == winning_team_index`. No win flag exists in the dataset.

URLs key on account ID rather than handle because an account ID is permanent
and a handle is not. A player renaming must not break their page's URL.

Standard library only.

Usage:
    python scripts/build_site.py
    python scripts/build_site.py --dataset out/dataset.json --out site/ --banner "Preview"
"""

from __future__ import annotations

import argparse
import gzip
import html
import json
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REGION_NAMES = {"na": "North America", "eu": "Europe", "asia": "Asia",
                "sa": "South America", "oce": "Oceania"}


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def pct(numerator, denominator) -> str | None:
    if not denominator or numerator is None:
        return None
    return f"{numerator / denominator * 100:.0f}%"


def load_heroes(assets_dir: Path) -> dict[int, str]:
    snapshots = sorted(assets_dir.glob("heroes-*.json.gz"))
    if not snapshots:
        return {}
    heroes = json.loads(gzip.decompress(snapshots[-1].read_bytes()))
    return {h["id"]: h.get("name") or f"Hero {h['id']}" for h in heroes}


def night_label(night: dict) -> tuple[str, str | None]:
    """Return (label, caveat). Region is omitted when it is not confirmed.

    Region dependent output is suppressed rather than guessed for nights whose
    region label is unresolved, so an unverified claim never reaches the page.
    """
    base = f"Night Shift #{night.get('edition')}"
    if night.get("region_confirmed") is False:
        return base, "region unconfirmed"
    region = REGION_NAMES.get(night.get("region"), night.get("region"))
    return (f"{base}, {region}" if region else base), None


def fmt_date(date_str: str | None) -> str:
    if not date_str:
        return ""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d %B %Y").lstrip("0")
    except ValueError:
        return date_str


CSS = """
:root {
  --bg: #ffffff; --fg: #16191d; --dim: #5c6570; --line: #e3e7ec;
  --accent: #0b6d4f; --win: #0b6d4f; --loss: #a3322b; --panel: #f7f9fa;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #12151a; --fg: #e8ecf1; --dim: #9aa5b1; --line: #262d36;
    --accent: #3ddc97; --win: #3ddc97; --loss: #ef7a72; --panel: #181d24;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 2rem 1.25rem 4rem; background: var(--bg); color: var(--fg);
  font: 16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
main { max-width: 62rem; margin: 0 auto; }
a { color: var(--accent); }
h1 { font-size: 1.9rem; margin: 0 0 .2rem; }
h2 { font-size: 1.05rem; text-transform: uppercase; letter-spacing: .06em;
     color: var(--dim); margin: 2.5rem 0 .75rem; font-weight: 600; }
.banner { background: #8a5a00; color: #fff; padding: .6rem 1rem; border-radius: 6px;
          margin-bottom: 1.75rem; font-size: .9rem; }
@media (prefers-color-scheme: dark) { .banner { background: #6b4500; } }
.head { display: flex; gap: 1.1rem; align-items: center; }
.head img { width: 64px; height: 64px; border-radius: 8px; }
.sub { color: var(--dim); font-size: .92rem; }
.tag { display: inline-block; font-size: .72rem; text-transform: uppercase;
       letter-spacing: .05em; border: 1px solid var(--line); border-radius: 3px;
       padding: .1rem .4rem; color: var(--dim); margin-left: .4rem; vertical-align: middle; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr)); gap: .8rem; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: .9rem 1rem; }
.card .big { font-size: 1.55rem; font-weight: 650; }
.card .what { font-size: .9rem; }
.card .of { color: var(--dim); font-size: .8rem; margin-top: .15rem; }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: .93rem; }
th, td { text-align: left; padding: .55rem .6rem; border-bottom: 1px solid var(--line); white-space: nowrap; }
th { color: var(--dim); font-weight: 600; font-size: .78rem; text-transform: uppercase; letter-spacing: .05em; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
.win { color: var(--win); font-weight: 600; }
.loss { color: var(--loss); font-weight: 600; }
.unknown { color: var(--dim); font-variant-numeric: tabular-nums; }
.lineup { margin: 0 0 1.4rem; }
.lineup .who { display: flex; flex-wrap: wrap; gap: .4rem; margin-top: .3rem; }
.lineup .who span, .lineup .who a { border: 1px solid var(--line); border-radius: 999px;
                                     padding: .12rem .6rem; font-size: .85rem; }
.lineup .who span { color: var(--dim); }
.credit { margin-top: 1rem; padding-top: .8rem; border-top: 1px dotted var(--line); }
.credit a { word-break: break-all; }
footer { margin-top: 3rem; padding-top: 1.2rem; border-top: 1px solid var(--line);
         color: var(--dim); font-size: .84rem; }
"""


def credit(sink: dict, entity: dict | None) -> None:
    """Record that this page rendered a name owned by an outside source.

    Called at every point a curated name reaches the HTML. The footer is built
    from what this collects, so a credit cannot drift out of sync with what the
    page actually shows: rendering the name is what creates the obligation.
    """
    attr = (entity or {}).get("attribution") or (entity or {}).get("handle_attribution")
    if not attr:
        return
    entry = sink.setdefault(attr["provider"], {**attr, "urls": set()})
    entry["urls"].add(attr["url"])


def render_attribution(sink: dict) -> str:
    """The credit block. Returns empty string when nothing is owed."""
    if not sink:
        return ""
    parts = ['<div class="credit">']
    for attr in sorted(sink.values(), key=lambda a: a["name"]):
        links = ", ".join(f'<a href="{esc(u)}" rel="license noopener">{esc(u)}</a>'
                          for u in sorted(attr["urls"]))
        share = (" This page is therefore offered under the same licence."
                 if attr.get("share_alike") else "")
        parts.append(
            f'<p>Team names, rosters and bracket stages on this page come from '
            f'{esc(attr["name"])}, used under '
            f'<a href="{esc(attr["licence_url"])}" rel="license noopener">'
            f'{esc(attr["licence"])}</a>.{share} Source: {links}</p>')
    parts.append('</div>')
    return "".join(parts)


def render_player(account_id, ds, idx, heroes, banner, sink: dict) -> str:
    player = idx["players"][account_id]
    rows = sorted(idx["by_account"][account_id],
                  key=lambda r: idx["matches"][r["match_id"]].get("start_time") or 0)

    # Pooled totals. Pooling rather than averaging per game percentages means a
    # single short game cannot swing the headline number.
    tot = defaultdict(int)
    wins = 0
    nights_seen = {}
    for row in rows:
        match = idx["matches"][row["match_id"]]
        side = str(row["match_team_index"])
        totals = match["totals"][side]
        tot["damage"] += row.get("damage") or 0
        tot["team_damage"] += totals.get("damage") or 0
        tot["ka"] += (row.get("kills") or 0) + (row.get("assists") or 0)
        tot["team_kills"] += totals.get("kills") or 0
        tot["net_worth"] += row.get("net_worth") or 0
        tot["team_net_worth"] += totals.get("net_worth") or 0
        tot["kills"] += row.get("kills") or 0
        tot["deaths"] += row.get("deaths") or 0
        tot["assists"] += row.get("assists") or 0
        # Win is derived here, never stored.
        if row["match_team_index"] == match.get("winning_team_index"):
            wins += 1
        night = idx["nights"].get(match["night_id"])
        if night:
            nights_seen[night["night_id"]] = night

    name = player.get("handle") or f"Account {account_id}"
    if player.get("handle"):
        credit(sink, player)
    for night in nights_seen.values():
        credit(sink, night)
    steam = player.get("steam") or {}
    avatar = steam.get("avatar_local")

    out = ['<!doctype html>', '<html lang="en">', '<head>',
           '<meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width, initial-scale=1">',
           f'<title>{esc(name)} - Night Shift Scout</title>',
           '<link rel="stylesheet" href="../../assets/site.css">',
           '</head>', '<body>', '<main>']

    if banner:
        out.append(f'<div class="banner">{esc(banner)}</div>')

    out.append('<div class="head">')
    if avatar:
        out.append(f'<img src="../../assets/{esc(avatar)}" alt="" width="64" height="64">')
    out.append('<div>')
    tag = ' <span class="tag">identity probable</span>' if player.get("identified") == "probable" else ""
    out.append(f'<h1>{esc(name)}{tag}</h1>')
    bits = [f"Account {esc(account_id)}"]
    if steam.get("countrycode"):
        bits.append(esc(steam["countrycode"]))
    out.append(f'<div class="sub">{" &middot; ".join(bits)}</div>')
    out.append('</div></div>')

    # ---- summary, in plain language -------------------------------------
    night_list = sorted(nights_seen.values(), key=lambda n: n.get("date") or "")
    when = ""
    if night_list:
        labels = []
        for night in night_list:
            label, caveat = night_label(night)
            labels.append(label + (f" ({caveat})" if caveat else ""))
        when = f" on {esc(labels[0])}" if len(labels) == 1 else f" across {len(labels)} nights"
    out.append('<h2>Summary</h2>')
    out.append(f'<p>Played {len(rows)} game{"" if len(rows) == 1 else "s"}{when}, '
               f'winning {wins} of {len(rows)}.</p>')

    out.append('<div class="cards">')
    for big, what, of in [
        (pct(tot["damage"], tot["team_damage"]) or "n/a", "of their team's damage",
         f'{tot["damage"]:,} of {tot["team_damage"]:,}'),
        (pct(tot["ka"], tot["team_kills"]) or "n/a", "of their team's kills, with a kill or an assist",
         f'{tot["ka"]} of {tot["team_kills"]} team kills'),
        (pct(tot["net_worth"], tot["team_net_worth"]) or "n/a", "of their team's souls",
         f'{tot["net_worth"]:,} of {tot["team_net_worth"]:,}'),
        (f'{tot["kills"]} / {tot["deaths"]} / {tot["assists"]}', "kills, deaths, assists",
         f'across {len(rows)} game{"" if len(rows) == 1 else "s"}'),
    ]:
        out.append(f'<div class="card"><div class="big">{esc(big)}</div>'
                   f'<div class="what">{esc(what)}</div><div class="of">{esc(of)}</div></div>')
    out.append('</div>')

    # ---- per match -------------------------------------------------------
    out.append('<h2>Games</h2>')
    out.append('<div class="scroll"><table><thead><tr>'
               '<th>Night</th><th>Game</th><th>Hero</th>'
               '<th class="num">K / D / A</th>'
               '<th class="num">Damage</th><th class="num">Share of team damage</th>'
               '<th class="num">Souls</th><th class="num">Share of team souls</th>'
               '<th>Result</th></tr></thead><tbody>')
    for row in rows:
        match = idx["matches"][row["match_id"]]
        night = idx["nights"].get(match["night_id"], {})
        label, caveat = night_label(night)
        totals = match["totals"][str(row["match_team_index"])]
        won = row["match_team_index"] == match.get("winning_team_index")
        game = match.get("series_label") or (match.get("stage") or "").title()
        if match.get("game_in_series"):
            game = f'{game} game {match["game_in_series"]}'.strip()
        # Any of these can be absent for a player who left early or whose
        # stats series is incomplete. A gap renders as "not recorded" and
        # never stops the build.
        damage, net_worth = row.get("damage"), row.get("net_worth")
        team_damage, team_net_worth = totals.get("damage"), totals.get("net_worth")

        caveat_html = f'<br><span class="sub">{esc(caveat)}</span>' if caveat else ""
        date_html = f'<br><span class="sub">{esc(fmt_date(night.get("date")))}</span>'
        hero = heroes.get(row.get("hero_id")) or f'Hero {row.get("hero_id")}'

        def cell(value, denominator=None):
            """A number cell, or a muted 'not recorded' when the value is missing."""
            if value is None:
                return '<td class="num unknown">not recorded</td>'
            if denominator is None:
                return f'<td class="num">{value:,}</td>'
            share = pct(value, denominator)
            if share is None:
                return '<td class="num unknown">not recorded</td>'
            return (f'<td class="num">{share}'
                    f'<br><span class="sub">of {denominator:,}</span></td>')

        kda = " / ".join(str(row.get(k)) if row.get(k) is not None else "?"
                         for k in ("kills", "deaths", "assists"))
        out.append(
            "<tr>"
            f'<td>{esc(label)}{caveat_html}{date_html}</td>'
            f'<td>{esc(game)}</td>'
            f'<td>{esc(hero)}</td>'
            f'<td class="num">{esc(kda)}</td>'
            f'{cell(damage)}{cell(damage, team_damage)}'
            f'{cell(net_worth)}{cell(net_worth, team_net_worth)}'
            f'<td class="{"win" if won else "loss"}">{"Won" if won else "Lost"}</td>'
            "</tr>")
    out.append('</tbody></table></div>')

    # ---- lineups ---------------------------------------------------------
    out.append('<h2>Who played</h2>')
    for row in rows:
        match = idx["matches"][row["match_id"]]
        night = idx["nights"].get(match["night_id"], {})
        label, caveat = night_label(night)
        game = f' game {match["game_in_series"]}' if match.get("game_in_series") else ""
        out.append(f'<div class="lineup"><strong>{esc(label)}{esc(game)}</strong>')
        for side_index in (row["match_team_index"], 1 - row["match_team_index"]):
            who = "Teammates" if side_index == row["match_team_index"] else "Opponents"
            team_id = next((s.get("team_id") for s in match["sides"]
                            if s.get("match_team_index") == side_index), None)
            team = idx["teams"].get(team_id, {}) if team_id else {}
            team_name = team.get("name") if team_id else None
            if team_name:
                credit(sink, team)
            out.append(f'<div class="sub" style="margin-top:.5rem">{who}'
                       f'{" &middot; " + esc(team_name) if team_name else ""}</div><div class="who">')
            for other in sorted(idx["by_match_side"][(row["match_id"], side_index)],
                                key=lambda r: r["account_id"]):
                if other["account_id"] == account_id:
                    continue
                other_player = idx["players"].get(other["account_id"], {})
                # An uncurated account is a bare number that links nowhere.
                if other_player.get("publishable"):
                    credit(sink, other_player)
                    out.append(f'<a href="../{esc(other["account_id"])}/">'
                               f'{esc(other_player.get("handle"))}</a>')
                else:
                    out.append(f'<span title="Not yet identified">{esc(other["account_id"])}</span>')
            out.append('</div>')
        out.append('</div>')

    generated = ds.get("generated_utc", "")
    out.append('<footer>'
               '<p>Percentages are pooled across all of a player\'s games, not averaged per game, '
               'so one short match cannot distort them. Each percentage is shown with the two '
               'numbers it was calculated from.</p>'
               '<p>Accounts shown as a number have not been identified yet.</p>'
               f'<p>Generated {esc(generated)} from match data supplied by the community run '
               'deadlock-api.com. Not affiliated with Valve.</p>'
               + render_attribution(sink) +
               '</footer>')
    out += ['</main>', '</body>', '</html>']
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", type=Path, default=Path("data/derived/dataset.json"))
    parser.add_argument("--assets", type=Path, default=Path("data/assets"))
    parser.add_argument("--out", type=Path, default=Path("site"))
    parser.add_argument("--banner", default=None, help="Optional notice rendered at the top of every page")
    args = parser.parse_args()

    ds = json.loads(args.dataset.read_text(encoding="utf-8"))
    heroes = load_heroes(args.assets)

    idx = {
        "players": {p["account_id"]: p for p in ds["players"]},
        "matches": {m["match_id"]: m for m in ds["matches"]},
        "nights": {n["night_id"]: n for n in ds["nights"]},
        "teams": {t["team_id"]: t for t in ds.get("teams", [])},
        "by_account": defaultdict(list),
        "by_match_side": defaultdict(list),
    }
    for row in ds["player_matches"]:
        idx["by_account"][row["account_id"]].append(row)
        idx["by_match_side"][(row["match_id"], row["match_team_index"])].append(row)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "assets").mkdir(exist_ok=True)
    (args.out / "assets" / "site.css").write_text(CSS.strip() + "\n", encoding="utf-8")

    published, skipped = [], []
    credited: set[str] = set()
    for account_id, player in sorted(idx["players"].items(), key=lambda kv: int(kv[0])):
        if not player.get("publishable"):
            skipped.append(account_id)
            continue
        page_dir = args.out / "players" / account_id
        page_dir.mkdir(parents=True, exist_ok=True)
        sink: dict = {}
        page = render_player(account_id, ds, idx, heroes, args.banner, sink)
        # A licence obligation is created by rendering the name, so the check
        # is against the finished HTML rather than against intent. If a page
        # owes a credit and does not carry one, the build fails: publishing
        # uncredited CC-BY-SA content is a licence breach, not a warning.
        for provider, attr in sink.items():
            if attr["url"] not in page and not any(u in page for u in attr["urls"]):
                raise SystemExit(
                    f"attribution missing: /players/{account_id}/ renders names from "
                    f"{attr['name']} but the page carries no link back to them")
            credited.add(provider)
        (page_dir / "index.html").write_text(page, encoding="utf-8")
        published.append(account_id)

    # Only copy avatars for players who actually have a page.
    avatar_src = args.assets / "avatars"
    copied = 0
    if avatar_src.is_dir():
        dest = args.out / "assets" / "avatars"
        dest.mkdir(exist_ok=True)
        for account_id in published:
            for candidate in avatar_src.glob(f"{account_id}.*"):
                shutil.copy2(candidate, dest / candidate.name)
                copied += 1

    print(f"Generated {len(published)} player page(s) into {args.out}/players/")
    print(f"  {len(skipped)} account(s) not published (unidentified or guess level); "
          f"they render as bare account IDs inside other pages")
    print(f"  {copied} avatar(s) copied, {len(ds['matches'])} match(es) represented")
    if credited:
        print(f"  credited on every page that uses them: {', '.join(sorted(credited))}")
    else:
        print("  no outside-sourced names rendered, so no attribution was owed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
