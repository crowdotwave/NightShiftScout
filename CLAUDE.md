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

These field names were verified by reading the API's Rust source and the
Steam protobuf definitions. **Do not guess at these.** If something looks
wrong, check against the live response before changing it.

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

- `duration_s`, `start_time` (unix seconds), `winning_team`
- `average_badge_team0`, `average_badge_team1` (used for Opposition column)
- `players[]` with: `account_id`, `team`, `hero_id`, `net_worth`, `kills`,
  `deaths`, `assists`
- **Damage is not a top-level player field.** It lives in `players[].stats[]`,
  a time series. Take the entry with the highest `time_stamp_s` and read
  `player_damage` from it.

### Hero assets

`hero_type` is Deadlock's own internal archetype (`m_eHeroType` in the game
files), one of: `assassin`, `brawler`, `marksman`, `mystic`. It is optional
and can be absent. Icons are at `images.icon_image_small` or
`images.icon_hero_card`.

### Steam profiles

`personaname`, `profileurl`, `avatar`, `realname`, `last_team_avg_badge`.
Note the endpoint takes **SteamID64**, but match data gives **account_id**
(32-bit). Convert with `accountId + 76561197960265728n`.

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
- **Opposition** = average enemy team badge. See below for why this matters.

## Night Shift format, important context

Night Shift is **weekly with no seasons**. Editions are numbered (#48 was
July 22, 2026). Format is king of the hill: qualifier (Bo3), then
challenger (Bo1), then final (Bo3). The final's winner returns directly to
the next edition's final; the loser drops to the next challenger match.

**This creates a real stats bias.** Established teams play fewer but harder
games. Up and comers accumulate more games, including easy qualifier
stomps. That inflates newcomer averages. The Opposition column exists to
expose this rather than silently correcting for it with invented math.

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
   count. This has broken twice when adding columns.
5. Search the file for em dashes and remove any that crept in
