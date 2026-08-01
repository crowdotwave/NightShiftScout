#!/usr/bin/env python3
"""Generate the static site from data/derived/dataset.json.

Emits two page types: a player index at /, and a player page at
/players/<account_id>/.

Plain HTML and CSS. No framework, no build step, and **no client side
fetching: every number is baked in at generation time.**

The front page carries the only script on the site, an inline filter over the
board. It is held to the rule the no-JavaScript line was protecting:
**it computes no number and fetches nothing.** Every row, every count and
every link is already in the HTML, and the script only sets `hidden` on rows
that do not match what you typed. With JavaScript off the search box is
removed and the complete list renders, so nothing is reachable only by
script.

The front page carries Stars of the Show and the full board. Its look is
lifted from `index.html` so the site and the console read as one product; the
CSS is duplicated rather than shared because the console must keep working as
a standalone file opened straight off disk.

**Stage weighting is deliberately not applied.** It was measured first: at
plausible weights the ranking correlates 0.9986 with the unweighted one, and
even at implausible ones it is 0.98, because qualifiers are 7% of all games.
So the board shows each player's stage mix and lets the reader judge, which
is the house style anyway. See scripts/measure_stage_weighting.py.

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

import metrics

REGION_NAMES = {"na": "North America", "eu": "Europe", "asia": "Asia",
                "sa": "South America", "oce": "Oceania"}

# The public leaderboard's eligibility bar. **Deliberately different from
# DEFAULT_MIN_GAMES in index.html, which is 3, and the two must not be
# unified.** They serve different readers.
#
# The console is for scouting: three games is enough to be worth a look, and
# seeing thin sample players is the point of it. The public board is a claim
# about who is good, read by people who know the scene. Measured on the real
# data at a bar of 3, five of the top ten had fewer than ten games and rank 7
# sat on three, above a player with 75. That reads as the site being broken,
# and they would be right. At 8 the top ten median goes from 20 games to 54
# and every thin sample player leaves the top of the board.
#
# Players below the bar are still shown and still get a page. They are marked
# "not ranked", never silently dropped.
LEADERBOARD_MIN_GAMES = 8


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


# The only script on the site. It computes no number and fetches nothing: the
# table is complete in the HTML and this hides rows that do not match. The
# search box is hidden in markup and revealed here, so a visitor without
# JavaScript sees the full board rather than a control that does nothing.
FILTER_SCRIPT = """<script>
(function () {
  var input = document.getElementById('filter');
  var count = document.getElementById('filter-count');
  var label = input.closest('label');
  var rows = Array.prototype.slice.call(document.querySelectorAll('#players tbody tr'));
  label.style.display = 'block';
  function apply() {
    var q = input.value.trim().toLowerCase();
    var shown = 0;
    rows.forEach(function (row) {
      var hit = !q || row.getAttribute('data-name').indexOf(q) !== -1;
      row.hidden = !hit;
      if (hit) { shown++; }
    });
    count.textContent = q ? shown + ' of ' + rows.length + ' players' : '';
  }
  input.addEventListener('input', apply);
})();
</script>"""


CSS = """
@import url("fonts.css");

:root {
    --bg: #0a0d0b;
    --bg-panel: #101512;
    --bg-panel-2: #141b17;
    --line: #1f2e27;
    --text: #dcece3;
    --text-dim: #6f9384;
    --soul: #3eeb9e;
    --soul-bright: #7dffc4;
    --soul-dim: #1f5c42;
    --blood: #c24b4b;
    --win: #3eeb9e;
    --mono: "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
    --serif: "Barlow", "Helvetica Neue", Arial, sans-serif;
    --display: "Chakra Petch", "Barlow", Arial, sans-serif;
  }

  * { box-sizing: border-box; }

  body {
    margin: 0;
    background:
      radial-gradient(ellipse 700px 500px at 15% -5%, rgba(62,235,158,0.10), transparent 60%),
      radial-gradient(ellipse 500px 400px at 100% 20%, rgba(62,235,158,0.05), transparent 55%),
      var(--bg);
    color: var(--text);
    font-family: var(--serif);
    padding: 40px 24px 80px;
  }

  .wrap { max-width: 980px; margin: 0 auto; display: flex; flex-direction: column; }
  .wrap > * { order: 5; } /* default order for anything not explicitly placed */

  header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    border-bottom: 1px solid var(--line);
    padding: 6px 0 20px;
    margin-bottom: 26px;
    flex-wrap: wrap;
    gap: 10px;
    box-shadow: 0 1px 0 rgba(62,235,158,0.16);
  }

  h1 {
    font-family: var(--display);
    font-weight: 700;
    font-size: 30px;
    margin: 0;
    letter-spacing: -0.3px;
    text-transform: uppercase;
  }
  h1 span {
    color: var(--soul);
    font-style: normal;
    text-shadow: 0 0 24px rgba(62,235,158,0.45);
  }
  h1 span { color: var(--soul); font-style: italic; }

  .subtitle {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 1.5px;
  }

  .panel {
    background: var(--bg-panel);
    border: 1px solid var(--line);
    border-radius: 5px;
    padding: 20px 22px;
    margin-bottom: 20px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
  }

  .panel-label {
    font-family: var(--display);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: var(--soul);
    margin-bottom: 10px;
    display: block;
  }

  textarea {
    width: 100%;
    min-height: 190px;
    background: #0f0d0b;
    border: 1px solid var(--line);
    color: var(--text);
    font-family: var(--mono);
    font-size: 13px;
    line-height: 1.6;
    padding: 14px;
    border-radius: 2px;
    resize: vertical;
  }
  textarea:focus { outline: 1px solid var(--soul); border-color: var(--soul); }

  .row { display: flex; gap: 12px; align-items: center; margin-top: 14px; flex-wrap: wrap; }

  button {
    font-family: var(--display);
    font-weight: 600;
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 11px 22px;
    border-radius: 2px;
    border: 1px solid var(--soul);
    background: transparent;
    color: var(--soul-bright);
    cursor: pointer;
    transition: background 0.15s, color 0.15s;
  }
  button:hover:not(:disabled) { background: var(--soul); color: #06110c; box-shadow: 0 0 18px rgba(62,235,158,0.35); }
  button:disabled { opacity: 0.35; cursor: default; }

  button.ghost {
    border-color: var(--line);
    color: var(--text-dim);
  }
  button.ghost:hover:not(:disabled) { background: var(--bg-panel-2); color: var(--text); }

  .status {
    font-family: var(--mono);
    font-size: 12px;
    color: var(--text-dim);
    min-height: 18px;
  }
  .status.warn { color: var(--blood); }

  /* Soul motes. Deliberately scoped to focus areas only (the Stars panel
     and the header) rather than the whole page, so they pull the eye where
     it matters instead of becoming visual noise everywhere. */
  .copy-id {
    cursor: pointer;
    border-bottom: 1px dotted var(--text-dim);
  }
  .copy-id:hover { color: var(--soul-bright); border-color: var(--soul-bright); }

  .particle-host { position: relative; }
  .particle-canvas {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
    z-index: 0;
  }
  .particle-host > *:not(.particle-canvas) { position: relative; z-index: 1; }

  @media (prefers-reduced-motion: reduce) {
    .particle-canvas { display: none; }
  }

  .stars-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(215px, 1fr));
    gap: 12px;
  }
  .star-card {
    background: linear-gradient(160deg, rgba(62,235,158,0.09), rgba(62,235,158,0.02) 60%, transparent);
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 14px 16px;
    position: relative;
    overflow: hidden;
  }
  .star-card::after {
    content: "";
    position: absolute;
    top: -40px; right: -40px;
    width: 110px; height: 110px;
    background: radial-gradient(circle, rgba(62,235,158,0.16), transparent 70%);
    pointer-events: none;
  }
  .star-cat {
    font-family: var(--display);
    font-weight: 600;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 1.4px;
    color: var(--soul);
    display: block;
    margin-bottom: 10px;
  }
  .star-val {
    font-family: var(--mono);
    font-size: 30px;
    font-weight: 700;
    color: var(--soul-bright);
    text-shadow: 0 0 20px rgba(125,255,196,0.5);
    line-height: 1;
    font-variant-numeric: tabular-nums;
  }
  .star-name {
    font-family: var(--display);
    font-weight: 600;
    font-size: 17px;
    color: var(--text);
    margin-top: 8px;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .star-sub {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--text-dim);
    margin-top: 4px;
  }
  .star-runner {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--text-dim);
    margin-top: 9px;
    padding-top: 8px;
    border-top: 1px solid var(--line);
  }

  .table-scroll { overflow-x: auto; }
  table {
    width: 100%;
    border-collapse: collapse;
    font-family: var(--mono);
    font-size: 13px;
  }
  thead th {
    text-align: left;
    font-family: var(--display);
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-dim);
    padding: 8px 10px;
    border-bottom: 1px solid var(--line);
    cursor: pointer;
    user-select: none;
  }
  thead th:hover { color: var(--soul); }
  tbody tr {
    border-bottom: 1px solid var(--line);
    cursor: pointer;
  }
  tbody tr:hover { background: var(--bg-panel-2); }
  tbody td { padding: 10px; }
  .rank { color: var(--text-dim); width: 34px; }
  .souls-val { color: var(--soul-bright); font-weight: 600; font-variant-numeric: tabular-nums; text-shadow: 0 0 12px rgba(125,255,196,0.45); }
  .player-cell { display: flex; align-items: center; gap: 8px; }
  .player-avatar { width: 24px; height: 24px; border-radius: 3px; border: 1px solid var(--line); display: block; }
  .player-link { color: var(--text); text-decoration: none; border-bottom: 1px dotted var(--text-dim); }
  .player-link:hover { color: var(--soul-bright); border-color: var(--soul-bright); }
  .player-sub { color: var(--text-dim); font-size: 11px; }
  .win-tag { color: var(--win); text-shadow: 0 0 10px rgba(62,235,158,0.35); }
  .loss-tag { color: var(--blood); }

  .detail-row td {
    background: #0c100d;
    padding: 4px 10px 14px 40px;
    font-size: 12px;
    color: var(--text-dim);
  }
  .detail-row table { margin-top: 6px; }
  .detail-row th, .detail-row td { padding: 4px 8px; border-bottom: 1px solid #182420; }

  .match-card {
    background: var(--bg-panel-2);
    border: 1px solid var(--line);
    border-radius: 3px;
    padding: 14px 16px;
    margin-bottom: 10px;
    font-family: var(--mono);
    font-size: 12px;
  }
  .match-card .match-rank {
    color: var(--soul-bright);
    font-weight: 700;
    font-size: 14px;
    margin-right: 8px;
  }
  .match-card .match-meta { color: var(--text-dim); margin: 4px 0 8px; }
  .match-card .match-players { display: flex; flex-wrap: wrap; gap: 6px 14px; }
  .match-card .match-players span { color: var(--text); }
  .match-card .team1 { color: var(--soul-bright); }

  .hidden { display: none; }

  footer {
    margin-top: 36px;
    font-family: var(--mono);
    font-size: 11px;
    color: #3c5348;
    line-height: 1.7;
  }
  footer a { color: var(--text-dim); }

/* ---------------------------------------------------------------------------
   Everything above is lifted verbatim from index.html so the public site and
   the console look like one product. The duplication is deliberate: the
   console is a standalone single file by design and must keep working when
   opened straight off disk, so the site build does not read from it.

   Below: the public site's own additions, plus aliases mapping the player page
   class names onto the same tokens.
   --------------------------------------------------------------------------- */
:root {
  --fg: var(--text); --dim: var(--text-dim); --accent: var(--soul);
  --loss: var(--blood); --panel: var(--bg-panel);
}
main { max-width: 980px; margin: 0 auto; }
a { color: var(--soul); }
.lede { color: var(--text-dim); margin: 0 0 18px; max-width: 60ch; }
.banner { background: #6b4500; color: #fff; padding: .6rem 1rem; border-radius: 6px;
          margin-bottom: 22px; font-size: .9rem; }
.avatar-fallback { display: inline-flex; align-items: center; justify-content: center;
                   background: var(--bg-panel-2); border: 1px solid var(--line);
                   border-radius: 6px; color: var(--text-dim); font-weight: 650;
                   font-family: var(--display); flex: none; }
.head { display: flex; gap: 16px; align-items: center; margin-bottom: 8px; }
.head img { width: 64px; height: 64px; border-radius: 8px; }
.sub { color: var(--text-dim); font-size: 13px; }
.tag { display: inline-block; font-size: 10px; text-transform: uppercase; letter-spacing: .06em;
       border: 1px solid var(--line); border-radius: 3px; padding: 1px 5px;
       color: var(--text-dim); margin-left: 5px; vertical-align: middle;
       font-family: var(--mono); }
.filter { display: block; font-family: var(--display); font-size: 12px; text-transform: uppercase;
          letter-spacing: .08em; color: var(--text-dim); margin: 0 0 14px; }
.filter input { display: block; width: 100%; max-width: 320px; margin-top: 6px;
                padding: 9px 12px; font-family: var(--serif); font-size: 14px; color: var(--text);
                background: var(--bg-panel); border: 1px solid var(--line); border-radius: 4px; }
.filter input:focus { outline: none; border-color: var(--soul-dim); }
#filter-count { margin: 6px 0 0; min-height: 1.2em; font-family: var(--mono); font-size: 11px; }
.scroll { overflow-x: auto; }
td.player { display: flex; align-items: center; gap: 9px; }
td.player img, td.player .avatar-fallback { width: 26px; height: 26px; border-radius: 5px;
                                            font-size: 12px; }
.rank { font-family: var(--mono); color: var(--text-dim); text-align: right; }
.unranked td { opacity: .62; }
.unranked-note { font-family: var(--mono); font-size: 11px; color: var(--text-dim);
                 text-transform: none; letter-spacing: 0; }
.stagemix { font-family: var(--mono); font-size: 11px; color: var(--text-dim); white-space: nowrap; }
.stagemix b { color: var(--text); font-weight: 500; }
.section-note { color: var(--text-dim); font-size: 13px; margin: 0 0 14px; max-width: 68ch; }
.credit { margin-top: 18px; padding-top: 12px; border-top: 1px dotted var(--line); }
.credit a { word-break: break-all; }
footer { margin-top: 46px; padding-top: 18px; border-top: 1px solid var(--line);
         color: var(--text-dim); font-size: 12.5px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; }
.card { background: var(--bg-panel); border: 1px solid var(--line); border-radius: 8px;
        padding: 14px 16px; }
.card .big { font-size: 25px; font-weight: 650; font-family: var(--display); color: var(--soul); }
.card .what { font-size: 13px; }
.card .of { color: var(--text-dim); font-size: 11.5px; margin-top: 3px; font-family: var(--mono); }
.lineup { margin: 0 0 20px; }
.lineup .who { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 5px; }
.lineup .who span, .lineup .who a { border: 1px solid var(--line); border-radius: 999px;
                                    padding: 2px 10px; font-size: 12.5px; }
.lineup .who span { color: var(--text-dim); }
.win { color: var(--win); font-weight: 600; }
.loss { color: var(--blood); font-weight: 600; }
.unknown { color: var(--text-dim); font-family: var(--mono); }
td.num { text-align: right; font-family: var(--mono); }
h2 { font-family: var(--display); font-size: 15px; text-transform: uppercase;
     letter-spacing: .08em; color: var(--text-dim); margin: 38px 0 12px; font-weight: 600; }
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


def avatar_tag(avatar: str | None, name: str, assets_dir: Path, depth: str, size: int) -> str:
    """An avatar image, or a lettered placeholder when the file is not there.

    Steam returns 404 for some avatars, so `avatar_local` in the dataset is a
    claim about a URL rather than proof of a file. Rendering it unchecked put
    one broken image on the site. The check is against the file on disk at
    build time, which is the only thing that can actually be wrong later.

    The placeholder is a styled span rather than an image, so it costs no
    request and cannot itself 404.
    """
    if avatar and (assets_dir / avatar).exists():
        return (f'<img src="{depth}assets/{esc(avatar)}" alt="" '
                f'width="{size}" height="{size}">')
    letter = next((c for c in (name or "?") if c.isalnum()), "?").upper()
    return (f'<span class="avatar-fallback" aria-hidden="true" '
            f'style="width:{size}px;height:{size}px;font-size:{max(12, size // 2)}px">'
            f'{esc(letter)}</span>')


def possessive(name: str) -> str:
    """Apostrophe for a name, without doubling the s on Abrams or Graves."""
    return "'" if name.endswith(("s", "S")) else "'s"


def render_early_game(ds, idx, assets_dir: Path, sink: dict) -> str:
    """The lane phase cards. Named findings with the arithmetic underneath.

    Every card states both numbers it compared, so nothing here needs a scale
    to be understood: "9,173 hero damage at 9 minutes, against an average
    Abrams' 2,867" is a sentence, not a metric.
    """
    early = idx["early"]
    heroes = idx["heroes"]
    published = {a for a, p in idx["players"].items() if p.get("publishable")}

    def named(account_id):
        player = idx["players"].get(account_id) or {}
        if account_id not in published:
            return None
        credit(sink, player)
        tag = (' <span class="tag">probable</span>'
               if player.get("identified") == "probable" else "")
        return (f'<a href="players/{esc(account_id)}/">'
                f'{esc(player.get("handle"))}</a>{tag}')

    def card(label, headline, detail, footnote=None):
        note = f'<div class="of">{footnote}</div>' if footnote else ""
        return (f'<div class="card"><div class="of">{esc(label)}</div>'
                f'<div class="big">{headline}</div>'
                f'<div class="what">{detail}</div>{note}</div>')

    cards = []

    # 1. Won the lane, lost the game. The launch finding, and the only card
    #    here that is a count rather than a person.
    lost = early["lanes_lost_anyway"]
    biggest = max(lost, key=lambda l: l["margin"]) if lost else None
    if biggest:
        who = [named(a) for a in biggest["accounts"]]
        who = [w for w in who if w]
        match = idx["matches"].get(biggest["match_id"]) or {}
        night = idx["nights"].get(match.get("night_id")) or {}
        label, _ = night_label(night) if night else ("", None)
        if night:
            credit(sink, night)
        detail = (f'Biggest: {" and ".join(who)} were {biggest["margin"]:,} souls ahead in '
                  f'their lane at 9 minutes and lost the match.') if who else (
                  f'Biggest margin: {biggest["margin"]:,} souls.')
        cards.append(card(
            "Won the lane, lost the game",
            f'{len(lost)} of {len(early["lanes"])}',
            detail,
            f'{esc(label)}. A lane is two players a side, so both are credited '
            f'with the lead equally. Nothing here splits a lane between them.'))

    # 2. Lane demon. Best average early hero damage against their own heroes.
    ratings = {a: r for a, r in early["ratings"].items() if a in published}
    if ratings:
        top = max(ratings, key=lambda a: ratings[a]["damage_z"])
        r = ratings[top]
        who = named(top)
        cards.append(card(
            "Lane demon",
            f'{round(r["damage"]):,}',
            f'{who} averages {round(r["damage"]):,} hero damage by 9 minutes, against '
            f'{round(r["baseline_damage"]):,} for an average game on the same heroes.',
            f'Across {r["games"]} games. Each game compared to that hero, not pooled.'))

    # 3. Ahead by nine. The single most dominant early game.
    scored = [s for s in early["scored"] if s["account_id"] in published]
    if scored:
        best = max(scored, key=lambda s: s["damage_z"])
        who = named(best["account_id"])
        hero = heroes.get(best["hero_id"], "?")
        cards.append(card(
            "Ahead by nine",
            f'{best["early"]["damage"]:,}',
            f'{who} dealt {best["early"]["damage"]:,} hero damage in nine minutes on '
            f'{esc(hero)}, against an average {esc(hero)}{possessive(hero)} '
            f'{round(best["hero_baseline_damage"]):,}.',
            f'Baseline from {best["hero_baseline_games"]} games on {esc(hero)}.'))

    # 4. Denied. Shown, deliberately not headlined: see the note under the row.
    if scored:
        best = max(scored, key=lambda s: s["denies_vs_hero"])
        who = named(best["account_id"])
        hero = heroes.get(best["hero_id"], "?")
        cards.append(card(
            "Denied",
            f'{best["early"]["denies"]}',
            f'{who} took {best["early"]["denies"]} denies in nine minutes on {esc(hero)}, '
            f'against {best["hero_baseline_denies"]:.1f} for an average {esc(hero)}.',
            'A deny has to be taken off the opponent, so it is contested.'))

    if not cards:
        return ""

    out = ['<h2>The lane phase</h2>']
    out.append('<p class="section-note">State at exactly 9 minutes, which is a real sample '
               'rather than an interpolation: the API records every player at 3, 6, 9, 12 and '
               '15 minutes on all 3,348 player-games we hold. Early numbers are compared to '
               'the same hero rather than pooled, because pooling damage across heroes ranks '
               f'heroes rather than players. {early["hero_count"]} heroes have enough games '
               'for a baseline.</p>')
    out.append('<div class="cards">' + "".join(cards) + '</div>')
    out.append('<p class="section-note">Denies are shown because they are the most stable and '
               'most independent early figure we measured, and they are not headlined because '
               'we cannot yet say what they are worth: a side ahead on denies at 9 minutes wins '
               '50.9% of matches, which is a coin flip. Early hero damage is the one that also '
               'predicts, at 61.2%. Last hits are deliberately absent, since they favour whoever '
               'is already ahead and so measure the state of the lane rather than the player.</p>')
    return "".join(out)


def render_index(ds, idx, banner, assets_dir: Path, sink: dict) -> str:
    """The front page: Stars of the Show, then the full board.

    Ranked players first, then everyone else marked "not ranked" rather than
    quietly dropped. Omitting them would make the board look like the whole
    population when it is a minority of it.
    """
    rows = idx["metric_rows"]
    published = {a for a, p in idx["players"].items() if p.get("publishable")}

    def name_of(account_id):
        player = idx["players"].get(account_id) or {}
        return player.get("handle") or f"Account {account_id}"

    def player_cell(account_id, size=26):
        player = idx["players"].get(account_id) or {}
        name = name_of(account_id)
        avatar = (player.get("steam") or {}).get("avatar_local")
        tag = ' <span class="tag">probable</span>' if player.get("identified") == "probable" else ""
        img = avatar_tag(avatar, name, assets_dir, "", size)
        if account_id in published:
            credit(sink, player)
            return f'{img}<a href="players/{esc(account_id)}/">{esc(name)}</a>{tag}'
        return f'{img}<span class="unknown">{esc(account_id)}</span>'

    # Only published players appear. An unidentified account is a number on a
    # match row, never a name on the front page.
    board = [r for r in rows if r["account_id"] in published]
    ranked = [r for r in board
              if r["games"] >= LEADERBOARD_MIN_GAMES and r["role_score"] is not None]
    ranked_ids = {r["account_id"] for r in ranked}
    unranked = [r for r in board if r["account_id"] not in ranked_ids]
    ranked.sort(key=lambda r: -r["role_score"])
    unranked.sort(key=lambda r: (-r["games"], name_of(r["account_id"]).lower()))

    out = ['<!doctype html>', '<html lang="en">', '<head>',
           '<meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width, initial-scale=1">',
           '<title>Night Shift Scout</title>',
           '<link rel="stylesheet" href="assets/site.css">',
           '</head>', '<body>', '<div class="wrap">']
    if banner:
        out.append(f'<div class="banner">{esc(banner)}</div>')
    out.append('<header><h1>Night <span>Shift</span> Scout</h1>'
               '<div class="subtitle">Deadlock esports scouting</div></header>')

    nights = len({m.get("night_id") for m in ds["matches"]})
    out.append(f'<p class="lede">Per-player performance across {len(ds["matches"])} games from '
               f'{nights} Night Shift nights. Every number compares a player to their own five '
               f'teammates in the same match rather than to the lobby, so a one sided game does '
               f'not flatter everyone on the winning side.</p>')

    star_pool = ranked or board
    stars = [
        ("Best KDA", "pooled_kda", lambda v: f"{v:.2f}",
         lambda r: f'{r["total_kills"]}/{r["total_deaths"]}/{r["total_assists"]} across {r["games"]} games'),
        ("Most souls per minute", "avg_souls_per_min", lambda v: f"{round(v):,}",
         lambda r: f'{r["games"]} games, {r["win_rate"] * 100:.0f}% win rate'),
        ("Most damage per minute", "avg_dpm", lambda v: f"{round(v):,}",
         lambda r: f'{r["games"]} games, {r["win_rate"] * 100:.0f}% win rate'),
        ("Highest kill participation", "avg_kp", lambda v: f"{v * 100:.0f}%",
         lambda r: f'in {r["avg_kp"] * 100:.0f}% of their team kills'),
    ]
    out.append('<h2>Stars of the show</h2>')
    out.append(f'<p class="section-note">Best in each category among the {len(star_pool)} ranked '
               f'players. One strong game cannot crown anyone, because ranking needs at least '
               f'{LEADERBOARD_MIN_GAMES} games.</p>')
    out.append('<div class="cards">')
    for label, key, fmt, sub in stars:
        candidates = [r for r in star_pool if r.get(key) is not None]
        if not candidates:
            continue
        top = max(candidates, key=lambda r: r[key])
        out.append(f'<div class="card"><div class="of">{esc(label)}</div>'
                   f'<div class="big">{esc(fmt(top[key]))}</div>'
                   f'<div class="what">{player_cell(top["account_id"], 22)}</div>'
                   f'<div class="of">{esc(sub(top))}</div></div>')
    out.append('</div>')

    out.append(render_early_game(ds, idx, assets_dir, sink))

    out.append('<h2>The board</h2>')
    out.append('<p class="section-note">Role score compares a player to the average player on the '
               'same hero archetype, within the same balance patch. 1.00 is exactly average. '
               'Stage mix is shown rather than corrected for: weighting games by bracket stage '
               'was measured and changes almost nothing, because qualifiers are 7% of all games.'
               '</p>')
    out.append('<label class="filter">Search players'
               '<input type="search" id="filter" autocomplete="off" placeholder="Type a name">'
               '</label><p class="sub" id="filter-count" role="status"></p>')
    out.append('<div class="scroll"><table id="players"><thead><tr>'
               '<th class="rank">#</th><th>Player</th><th class="num">Role score</th>'
               '<th class="num">Games</th><th>Stage mix</th><th class="num">KDA</th>'
               '<th class="num">Souls/min</th><th class="num">Team kills</th>'
               '<th class="num">Win rate</th></tr></thead><tbody>')

    def stage_mix(row):
        counts = row["stage_counts"]
        parts = [f'<b>{counts[key]}</b>{short}'
                 for short, key in (("Q", "Qualifier"), ("C", "Challenger"), ("F", "Finals"))
                 if counts.get(key)]
        return " ".join(parts) or '<span class="unknown">not recorded</span>'

    for position, row in enumerate(ranked, 1):
        out.append(
            f'<tr data-name="{esc(name_of(row["account_id"]).lower())}">'
            f'<td class="rank">{position}</td>'
            f'<td class="player">{player_cell(row["account_id"])}</td>'
            f'<td class="num">{row["role_score"]:.2f}</td>'
            f'<td class="num">{row["games"]}</td>'
            f'<td class="stagemix">{stage_mix(row)}</td>'
            f'<td class="num">{row["pooled_kda"]:.2f}</td>'
            f'<td class="num">{round(row["avg_souls_per_min"]):,}</td>'
            f'<td class="num">{row["avg_kp"] * 100:.0f}%</td>'
            f'<td class="num">{row["win_rate"] * 100:.0f}%</td></tr>')

    for row in unranked:
        out.append(
            f'<tr class="unranked" data-name="{esc(name_of(row["account_id"]).lower())}">'
            f'<td class="rank">&middot;</td>'
            f'<td class="player">{player_cell(row["account_id"])}</td>'
            f'<td class="unranked-note" colspan="2">not ranked, fewer than '
            f'{LEADERBOARD_MIN_GAMES} games ({row["games"]})</td>'
            f'<td class="stagemix">{stage_mix(row)}</td>'
            f'<td class="num">{row["pooled_kda"]:.2f}</td>'
            f'<td class="num">{round(row["avg_souls_per_min"]):,}</td>'
            f'<td class="num">{row["avg_kp"] * 100:.0f}%</td>'
            f'<td class="num">{row["win_rate"] * 100:.0f}%</td></tr>')
    out.append('</tbody></table></div>')

    unpublished = len(idx["players"]) - len(published)
    out.append('<footer>'
               f'<p>{len(ranked)} players ranked, {len(unranked)} shown but not ranked. '
               f'Three good games are not scouting data, so ranking needs {LEADERBOARD_MIN_GAMES}. '
               f'An unranked player still has a page with every game on it.</p>'
               f'<p>{unpublished} further accounts have played but are not identified. They appear '
               f'as plain numbers inside match rows rather than being guessed at.</p>'
               f'<p>Generated {esc(ds.get("generated_utc", ""))} from match data supplied by the '
               'community run <a href="https://deadlock-api.com/" rel="noopener">deadlock-api</a>.'
               '</p>')
    out.append(render_attribution(sink))
    out.append('</footer>')
    out.append(FILTER_SCRIPT)
    out.append('</div></body></html>')
    return "".join(out)


def render_player(account_id, ds, idx, heroes, banner, assets_dir: Path, sink: dict) -> str:
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
    out.append(avatar_tag(avatar, name, assets_dir, "../../", 64))
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
        # Leaderboard numbers, computed by scripts/metrics.py, which is a
        # faithful port of computeRows in index.html. Verified against the
        # running console on 24 matches and 74 players: every metric agreed to
        # floating point precision, worst relative difference 3.4e-16.
        "metric_rows": metrics.compute_rows(ds, args.assets),
        "heroes": heroes,
        "early": metrics.compute_early(ds),
    }
    for row in ds["player_matches"]:
        idx["by_account"][row["account_id"]].append(row)
        idx["by_match_side"][(row["match_id"], row["match_team_index"])].append(row)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "assets").mkdir(exist_ok=True)
    (args.out / "assets" / "site.css").write_text(CSS.strip() + "\n", encoding="utf-8")

    # Avatar existence is checked against the SOURCE assets, since that is what
    # exists while pages render. The copy into the output happens afterwards
    # and only for files that are actually there.
    avatars_dir = args.assets

    published, skipped = [], []
    credited: set[str] = set()
    for account_id, player in sorted(idx["players"].items(), key=lambda kv: int(kv[0])):
        if not player.get("publishable"):
            skipped.append(account_id)
            continue
        page_dir = args.out / "players" / account_id
        page_dir.mkdir(parents=True, exist_ok=True)
        sink: dict = {}
        page = render_player(account_id, ds, idx, heroes, args.banner, avatars_dir, sink)
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

    # Remove pages for accounts that are no longer publishable. Downgrading an
    # identity is exactly the correction that must actually take effect: without
    # this, retracting a name leaves the old page live on any deployed copy.
    retracted = []
    players_dir = args.out / "players"
    if players_dir.is_dir():
        keep = set(published)
        for existing in players_dir.iterdir():
            if existing.is_dir() and existing.name.isdigit() and existing.name not in keep:
                shutil.rmtree(existing)
                retracted.append(existing.name)

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

    # Fonts and hero icons are served locally so a visitor makes no request to
    # Google or to the community asset bucket. See scripts/fetch_web_assets.py.
    fonts_css = args.assets / "fonts.css"
    if fonts_css.exists():
        shutil.copy2(fonts_css, args.out / "assets" / "fonts.css")
        shutil.copytree(args.assets / "fonts", args.out / "assets" / "fonts",
                        dirs_exist_ok=True)
    hero_icons = args.assets / "hero-icons"
    if hero_icons.is_dir():
        shutil.copytree(hero_icons, args.out / "assets" / "hero-icons", dirs_exist_ok=True)

    # The index is rendered last, so it can only ever list pages that exist.
    index_sink: dict = {}
    index_html = render_index(ds, idx, args.banner, avatars_dir, index_sink)
    for provider, attr in index_sink.items():
        if attr["url"] not in index_html and not any(u in index_html for u in attr["urls"]):
            raise SystemExit(
                f"attribution missing: the index renders names from {attr['name']} "
                f"but carries no link back to them")
        credited.add(provider)
    (args.out / "index.html").write_text(index_html, encoding="utf-8")

    print(f"Generated {len(published)} player page(s) into {args.out}/players/")
    print(f"  index at {args.out}/index.html listing {len(published)} player(s)")
    print(f"  {len(skipped)} account(s) not published (unidentified or guess level); "
          f"they render as bare account IDs inside other pages")
    print(f"  {copied} avatar(s) copied, {len(ds['matches'])} match(es) represented")
    if retracted:
        print(f"  {len(retracted)} page(s) removed, no longer publishable: "
              f"{', '.join(sorted(retracted))}")
    if credited:
        print(f"  credited on every page that uses them: {', '.join(sorted(credited))}")
    else:
        print("  no outside-sourced names rendered, so no attribution was owed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
