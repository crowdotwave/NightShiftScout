# Night Shift Scout

A single-file browser app for scouting Deadlock esports talent, focused
specifically on the Deadlock Night Shift weekly tournament series.

Everything lives in `index.html`. No build step, no server, no
dependencies. Open it directly in a browser and it runs. Keep it that way
unless there is a strong reason not to: the zero-install property is what
makes it easy to share with orgs, players, and community members.

## House rules

- **Never use em dashes** anywhere: not in UI copy, not in code comments,
  not in commit messages. Use commas, colons, periods, or parentheses.
  This applies to every file in this project.
- Do not introduce a framework or build step without asking first.
- Do not use `localStorage` for anything the user has not explicitly asked
  to persist. Currently persisted: match IDs, aliases, team tags,
  watchlist, top-elo match log.

## What it does

Paste Deadlock match IDs, get a scouting leaderboard. Core panels in
display order:

1. **Match IDs** input, remembers the last set and re-analyses on load
2. **Stars of the Show**, auto-generated headline cards
3. **Leaderboard**, full sortable table
4. **Team View**, rollups from manually tagged player to team mappings
5. **Share Card**, generates a PNG for Reddit and Twitter
6. Config panels: Aliases, Team Tags, Watchlist, Top Elo Lobby

Panel order is controlled by CSS `order` on a flex column wrapper, not by
DOM position. This was deliberate: it lets the visual order change without
moving large HTML blocks and breaking element IDs.

## Verified API facts

All data comes from `https://api.deadlock-api.com/v1`. It is a community
run, open source, unofficial API. CORS is wildcard-open, so the browser can
call it directly with no key and no proxy.

**Do not guess at these.** If something looks wrong, check against the live
response before changing it.

Two different levels of confidence are recorded below, and the difference
matters:

- **Confirmed live** means checked against actual responses from this API,
  including real Night Shift tournament matches, on July 26 2026.
- **Source-read** means taken from the API's Rust source or the Steam
  protobuf definitions but never observed in a tournament response. A field
  existing in the schema does **not** mean it carries a usable value.

That distinction cost real work once already. `average_badge_team0/team1`
was source-read, is genuinely in the schema, and is hardcoded to `0` on
every tournament match, which shipped a leaderboard column of zeros.

### Endpoints in use

| Endpoint | Purpose |
| --- | --- |
| `GET /matches/{id}/metadata` | Full match data, the main source |
| `GET /matches/active` | Live in-progress matches |
| `GET /players/{account_id}/match-history` | A player's recent games |
| `GET /players/steam?account_ids=<csv of steamid64>` | Names and avatars |
| `GET /assets/heroes?only_active=false` | Hero names, icons, archetypes |
| `GET /leaderboard/{region}` | Ranked ladder, regions like `Europe`, `NAmerica` |
| `GET /patches/big-days` | Balance patch dates, used for the stale-data warning |

### Match metadata shape

Response is `{ match_info: { ... } }`. Relevant fields on `match_info`:

- **Confirmed live:** `duration_s`, `start_time` (unix seconds),
  `winning_team`, `match_mode`
- **Confirmed live:** `players[]` with `account_id`, `team`, `hero_id`,
  `net_worth`, `kills`, `deaths`, `assists`. Usually twelve players per
  match, but **not always**: one match in 270 has 8. Read the count, do not
  assume it.
- **Confirmed live, and re-tested on 3,236 player-games: damage is not a
  top-level player field.** It lives in `players[].stats[]`, a time series.
  Take the entry with the highest `time_stamp_s` and read `player_damage`
  from it. **3236 of 3236** across editions #1 to #48, no misses. The highest
  `time_stamp_s` equals `duration_s` exactly on every one, so that really is
  the end-of-game snapshot. This is the best tested claim we have.
- **Do not use `average_badge_team0` / `average_badge_team1`.** The fields
  exist, but on tournament matches (`match_mode: 2`) they are always `0`,
  not null and not absent. Public matchmaking games (`match_mode: 1`) do
  return real values, so the field works, Valve simply never populates it for
  custom lobbies. Note that `?? null` will **not** catch this, because `0` is
  not nullish. **Almost all Night Shift games are `match_mode: 2`, but not
  all**: 268 of 270 cached, with 2 coming back as mode 1 carrying a real
  badge of 11. Do not filter on mode 2 assuming it is universal.
- **`teams[]` is often present, and always hollow.** Absent on 110 of 270
  matches and present on 160, where every entry has only `team` and an empty
  `team_tracked_stats`. No identity, no score. A truthiness check on it
  behaves differently across editions.

### Hero assets

`hero_type` is Deadlock's own internal archetype (`m_eHeroType` in the game
files), one of: `assassin`, `brawler`, `marksman`, `mystic`. Icons are at
`images.icon_image_small` or `images.icon_hero_card`.

**Confirmed live and reliable.** Of 57 heroes, 37 carry a `hero_type`. The
20 without one are almost all `disabled: true`, so among the 38 active
heroes exactly one (Rem) is missing it. Across the full cache, **3188 of
3236** player-games resolve to a role, 98.5%, with all 48 gaps on hero 79.
The earlier figure of 143 of 144 came from 12 recent matches and was
slightly optimistic. Treat role as optional in code, since it can be absent,
but it is dense enough to base Role Score on. Every active hero has
`icon_image_small`.

### Steam profiles

`personaname`, `profileurl`, `avatar`, `avatarmedium`, `avatarfull`,
`realname`, `countrycode`, `last_team_avg_badge`, `matches_played_last_30d`.
All confirmed live. Note the endpoint takes **SteamID64**, but match data
gives **account_id** (32-bit). Convert with `accountId + 76561197960265728n`.

`last_team_avg_badge` is populated, but it is not a usable stand-in for the
old Opposition column. **Provisional, and the weakest claim we rely on:** it
rests on 45 profiles from three consecutive editions, which is the same shape
of sample that produced the amber/sapphire error, and we now know of 170
accounts. All 45 players across the sample tournament set came
back as either 115 or 116. At Night Shift level everyone is Eternus V or VI,
so badge cannot separate these teams no matter where the number comes from.

### Badge encoding

Badge value is `tier * 10 + subrank`. Eternus is tier 11, so Eternus VI is
116. It is unconfirmed whether Eternus actually subdivides into I-VI; the
Eternus scan falls back to the whole tier and says so if the strict filter
returns nothing.

## Metric design, and why

The central problem this app exists to solve: raw stats lie about who is
actually good, because they conflate individual skill with team dominance
and with role. Each metric below is a specific fix. **Do not replace these
with a single opaque composite score.** Being able to explain each number
in one sentence is a hard requirement.

- **KDA** = `(K + A) / D`, pooled across all games rather than averaging
  per-game ratios, so one lucky game cannot distort it. Chosen over raw K/D
  because Deadlock is 6v6 and teamfight heavy, so assists carry real signal.
- **Net Worth Share** = player net worth divided by the 12-player match
  average. Cancels out game length but *not* team dominance.
- **Team Share** = player net worth divided by their own five teammates'
  average. This is the real fairness fix: it separates "I am the engine of
  this team" from "my team is winning." Also split by win and loss, which
  is the single most useful scouting signal in the app.
- **Role Score** = performance versus the average player *on the same
  archetype*, where baselines are computed from the loaded dataset rather
  than hardcoded. Self-calibrates as the dataset grows. Scored per game
  against whichever role was actually played, so role-flexers are handled.
- **KP%** = `(K + A) / team's total kills`, team-relative so it holds up
  whether a game had 20 kills or 80.

**Minimum games.** Players below `DEFAULT_MIN_GAMES` (currently 3) are not
ranked. Averages over one or two games are not scouting data, they are
noise, and without this the board opened on whoever had a single good game.
The constant is defined once at the top of the script and drives both the
leaderboard filter and the Stars panel eligibility bar. Do not reintroduce
a second hardcoded copy: the two used to disagree, and the table happily
ranked one-game players while Stars quietly required three.

**Removed: Opposition.** This was average enemy team badge, intended to
expose the format bias described below. It shipped as a column of zeros
because the underlying API field is never populated for tournament lobbies.
See the match metadata notes above before considering any revival.

## Night Shift format, important context

Night Shift is **weekly with no seasons**. Editions are numbered (#48 was
July 22, 2026). Format is king of the hill: qualifier (Bo3), then
challenger (Bo1), then final (Bo3). The final's winner returns directly to
the next edition's final; the loser drops to the next challenger match.

**An edition is not always a single evening.** On #36 NA the qualifier was
played five days before the challenger and final, and on #37 NA three days
before. Twenty two editions span more than one UTC date, though most of those
are just a broadcast running past midnight. Night files therefore carry a
`date_span`, and code should not assume one edition means one date.

**This creates a real stats bias.** Established teams play fewer but harder
games. Up and comers accumulate more games, including easy qualifier
stomps. That inflates newcomer averages.

**This bias is currently unmitigated, and that is a known weakness.** The
Opposition column was the intended fix and it did not work, because neither
the match badge fields nor Steam's `last_team_avg_badge` can tell these
teams apart (see the API notes above). Anything that replaces it has to be
computed from data the app already trusts, for example bracket stage, or
opponent quality derived from the loaded dataset such as the average Role
Score of the enemy team. Do not reach for a badge field again.

**Data window:** since there are no seasons, the meaningful boundary is the
balance patch, not a number of weeks. The app pulls `/patches/big-days` and
warns when loaded games predate the current patch.

## Known gaps

- **No automatic match ID discovery.** IDs are pasted by hand, sourced from
  lockblaze.com tournament pages. Liquipedia scraping was attempted and
  returned HTTP 429; be careful about rate limits if revisiting this.
- **No automatic Steam to tournament-handle mapping.** No such data source
  exists. Current fallback chain: manual alias, then Steam persona name if
  it contains real characters, then the vanity slug from `profileurl`
  (`steamcommunity.com/id/<handle>`), then `realname`, then account ID.
- **No automatic team rosters.** Team tagging is manual for the same reason.
- **Role Score needs volume.** Under roughly 10 games per role the
  baselines are noisy. The UI warns about this already.
- **Role baselines include the player being scored.** Every player is part
  of the average they are measured against, which biases scores toward 1.00x
  for high-volume players. Measured on the 12-match sample: the largest
  leave-one-out shift across all 45 players was +0.03x, with no change to
  ranking order. Real but not currently worth fixing. Recheck if the dataset
  ever gets small per role, since the bias grows as sample size falls.
- **No opposition-strength adjustment.** See the Night Shift format section.

## Next steps, roughly prioritised

1. Load a larger match set from the current patch so Role Score baselines
   and per-player samples become trustworthy
2. Auto-render an infographic-style summary view in the page itself, not
   just the downloadable share card
3. Consider hero-specific baselines once there is enough data
4. Lane phase splits, using the time series data already being fetched

## Verifying changes

There is no test suite. Before considering a change done:

1. Open the file in a browser and confirm no console errors
2. Click Analyze with the default sample IDs and confirm the table populates
3. Expand a player row and confirm the per-game detail matches
4. Confirm colspan on the detail row still equals the main table's column
   count. This has broken twice when adding columns. Currently both are 14,
   and the inner per-game table is 12 wide.
5. Search the file for em dashes and remove any that crept in

**Verify behaviour by running a full Analyze, not by poking the DOM.** A
default that is correct in the HTML can still be overwritten at runtime.
That exact bug shipped: `runAnalysis` reset the min-games input on every
run, so the attribute said 3 and the app behaved as 1, and setting the
field by hand before re-rendering hid it.

`.claude/launch.json` defines a static server (`python -m http.server 8000`)
for previewing. Opening the file over `file://` also works, since the API is
wildcard-CORS. Note that `http.server` sends no cache headers, so after an
edit the browser will happily serve a stale copy: hard-reload or append a
`?v=N` query string before trusting what you see.
