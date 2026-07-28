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
  `net_worth`, `kills`, `deaths`, `assists`. Twelve players, six a side, on
  269 of 270. Read the count anyway rather than dividing by 12, since it is
  free. The one exception has 8 and is **not a Night Shift game**: it is a
  4v4 Street Brawl match that reached the cache through a wrong match ID on
  the wiki. See the contamination section in `API-NOTES.md`.
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
  not nullish.
- **Every genuine Night Shift game is `match_mode: 2`.** 268 of 270 cached
  are, and the 2 that are not turned out not to be Night Shift games at all
  but wrong wiki match IDs pointing at public games. This corrects an earlier
  note here saying mode 2 was not universal and warning against filtering on
  it. Filtering on mode 2 would have caught both bad IDs on ingest, so it is
  a **useful integrity check**, though the hero pick join is stronger because
  it also catches a wrong ID that happens to be another custom lobby.
- **`teams[]` is often present, and always hollow.** Absent on 110 of 270
  matches and present on 160, where every entry has only `team` and an empty
  `team_tracked_stats`. No identity, no score. A truthiness check on it
  behaves differently across editions. **Checked 2026-07-27: nothing in this
  repository branches on it.** The only reader is
  `scripts/verify_api_claims.py`, which tests it deliberately. So the finding
  is real but our exposure is zero, and no code change was needed.

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
  against whichever role was actually played, so role-flexers are handled,
  and **against the balance patch that game was played under**, which is the
  one place the wide data window does not apply. See Data window below.
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

**Data window: use every game, and flag cross-patch on the page.** This
reverses the earlier rule that the window is the current balance patch.

The reasoning is that almost every metric here is **player against their own
five teammates in the same match**. Team Share, damage share and KP% all put
the player in the numerator and their own team in the denominator, so a patch
that inflates souls or damage moves both sides of the ratio and largely
cancels. Cutting to the current patch would discard roughly half the games we
hold to correct a distortion those metrics do not have.

The sizes matter, and the earlier "a patch window is only about 20 games" was
measured when the cache held 12 matches. Against the current boundary
(2026-03-11) the 270 cached matches split **133 after, 137 before**, spanning
2025-08-13 to 2026-07-23 across four patch eras that contain Night Shift
games.

**Role Score is the exception, and it is scoped by patch.** Its baselines are
per archetype rather than per team, so there is no teammate denominator to
cancel anything, and a balance patch genuinely moves what an average Marksman
deals. It is bucketed by the patch each game was played under, and **each game
is scored against its own era**, not against the current one, so widening the
window does not make older games unscorable. Where an era has fewer than
`ROLE_BASELINE_MIN_GAMES` games for a role it falls back to the pooled
all-patch baseline and the affected rows say so on hover. Every era-role
bucket in the current cache clears that bar, the smallest being 15.

The patch list is cached at `data/assets/patches-big-days-<date>.json` by
`scripts/fetch_patches.py`, and `index.html` carries the same list as a
fallback so bucketing still works when the live call fails. Note the current
patch is **138 days old against a median gap of 22 days**, so "current patch"
is a much wider window than the phrase suggests.

## Known gaps

- **No automatic match ID discovery.** IDs are pasted by hand, sourced from
  lockblaze.com tournament pages. Liquipedia scraping was attempted and
  returned HTTP 429; be careful about rate limits if revisiting this.
- **No automatic Steam to tournament-handle mapping.** No such data source
  exists. Current fallback chain: manual alias, then Steam persona name if
  it contains real characters, then the vanity slug from `profileurl`
  (`steamcommunity.com/id/<handle>`), then `realname`, then account ID.
- **No automatic team rosters.** Team tagging is manual for the same reason.
- **Role Score needs volume, now per patch era.** Under
  `ROLE_BASELINE_MIN_GAMES` (10) games per role *within a patch*, that era's
  baseline is not used and the pooled one stands in. Bucketing by patch cuts
  each baseline's sample, so this bar bites more often than it used to. In
  the current cache every era-role bucket clears it, the smallest being 15.
- **Role baselines include the player being scored.** Every player is part
  of the average they are measured against, which biases scores toward 1.00x
  for high-volume players. Measured on the 12-match sample: the largest
  leave-one-out shift across all 45 players was +0.03x, with no change to
  ranking order. Real but not currently worth fixing. **Worth rechecking now
  that baselines are patch-scoped**, since the bias grows as sample size
  falls and each bucket is smaller than the old pooled average.
- **No opposition-strength adjustment.** See the Night Shift format section.

## Next steps, roughly prioritised

1. Done for now: the cache holds 270 matches and 3,236 player-games across
   four patch eras, so Role Score baselines clear their sample bar in every
   bucket. 14 known match IDs are still outstanding, blocked on the 3/hour
   cold fetch limit.
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
