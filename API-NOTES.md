# API-NOTES.md

What `api.deadlock-api.com/v1` actually returns, established by real requests.

Every claim below was checked against live responses on **July 27 2026**,
using the 12 cached Night Shift matches (editions 46 to 48, 144 player-games)
plus live calls to each endpoint. Nothing here is inferred from field names.
Where a field exists but is useless, that is stated rather than left for
someone to rediscover.

One section is an exception and says so in its own opening line: **Rate
limits** is read from the API's published OpenAPI spec, because rate limit
policy cannot be established by observation without abusing the thing being
measured. Everything else remains observation only.

**Read the sampling section below before trusting any "confirmed" count in
this file.** Most of them were established on 12 matches from three
consecutive editions. Some have since been re-tested on 281 and held. Some
did not.

Anything fetched to establish a fact here belongs in the repository, not in a
scratch directory. Rate limits were missing from these notes for exactly that
reason, and it cost a backfill run that stalled with no visible cause.

Counts like "144/144" mean the check ran over every player-game in the cache.

The API is community run, open source, and unofficial. CORS is wildcard-open,
no key and no proxy needed.

---

## Summary of the things that will bite you

| Finding | Detail |
| --- | --- |
| `match_result` is not win/loss | It is the **winning team index**. See below, verified 9/9. |
| `average_badge_team0/1` is always `0` on tournament games | Present, typed `int`, never populated for `match_mode: 2`. |
| `teams[]` carries nothing usable | Often **present** rather than absent, but every entry is hollow. See below. |
| `match_outcome` is always `0` | Does not indicate who won. Use `winning_team`. |
| Leaderboard gives **candidate** account IDs | `possible_account_ids` is an array, exactly one candidate only 58% of the time. |
| Match history **does** exist per account | And it includes tournament matches. |
| Metadata rate limit depends on **where the match is stored** | Cached 100/s, S3 100/10s, **cold from Steam 3/hour**. See below. |
| **Two cached matches are not Night Shift games at all** | Wrong match IDs on the wiki. Three independent signals agree. See below. |

---

## The 12 match sample, and what survived leaving it

Every "confirmed" claim originally in this file came from the **same 12
matches**: editions #46 to #48, 144 player-games, all from July 2026.

That sample is what produced the amber/sapphire side mapping error. The rule
held 12 of 12 and looked like a law; across 261 games it is 95% and inverts
on 13. Three consecutive recent editions are not a random sample of 49, and
**every conclusion drawn from those 12 inherits that weakness**. Not wrong,
but untested anywhere else.

`scripts/verify_api_claims.py` re-tests everything the cache alone can
settle, now across **281 matches and 3,368 player-games, editions #1 to #48**.
It makes no network requests. Results:

### Held, and now on a 22x larger sample

| Claim | Was | Now |
| --- | --- | --- |
| Final `stats[]` entry carries `player_damage` | 144/144 | **3368/3368** |
| Max `time_stamp_s` equals `duration_s` exactly | 144/144 | **3368/3368** |
| `winning_team` is 0 or 1 | 12/12 | **281/281** |
| `match_outcome` is always 0 | 12/12 | **281/281** |
| `banned_hero_ids` is empty | 12/12 | **281/281** |

The damage extraction the whole app depends on is now genuinely well tested.

### Did not survive

- **`teams[]` is not "empty".** It is **present on 171 of 281 matches** and
  absent on the rest. The 12 match sample happened to contain only the absent
  case. The substance of the claim still holds and is why this is a wording
  fix rather than a retraction: all 342 entries across those 171 matches
  carry exactly two keys, `team` and an empty `team_tracked_stats`. There is
  still no team identity and no score. But code that tests `if teams:` will
  now take a branch it never took on the old sample.
- **"All Night Shift games are `match_mode: 2`" survives, and the apparent
  exceptions were the discovery.** 279 of 281 cached matches are mode 2. The
  2 that are not turned out not to be Night Shift games at all, but wrong
  match IDs on the wiki pointing at public games. Corrected on 2026-07-27;
  this bullet previously read "is false" and treated the 2 as tournament
  games. See "Two contaminated match IDs" above.
- **Twelve players per match is not universal, but the exception is not a
  tournament game.** Match `83756240` has **8**, and it is a 4v4 Street Brawl
  game, one of the two contaminants. Still read the actual count rather than
  dividing by 12, since that costs nothing, but do not expect a genuine
  Night Shift match to be anything other than 6v6.
- **`hero_type` coverage is lower than measured.** Was 143/144, 99.3%. Across
  the full cache it is **3319/3368, 98.5%**, and all 49 gaps are hero 79. The
  conclusion that role is dense enough to build on survives, the exact figure
  does not.

### Still resting on the 12, and why

These need data the cache does not hold, so they could not be re-tested
without spending requests:

- ~~`last_team_avg_badge` is 115 or 116 for everyone.~~ **Settled on 155
  accounts, see the Steam section. The conclusion holds, the wording did not.**
- `possible_account_ids` is unique only 58% of the time. Needs `/leaderboard`.
- `match_result` is the winning team index, 9/9. Needs
  `/players/{id}/match-history`.

The remaining two are still provisional. The badge claim was the one flagged
here as most dangerous, on the grounds that 45 players from three editions is
the shape of sample that has already misled us once. It has since been tested
on **155 accounts** and the conclusion survived, with the wording corrected.
See the Steam section. That is one down and two to go, and the two left are
both cheap to settle whenever a request budget allows.

---

## Two contaminated match IDs

**Found 2026-07-27 while re-checking the reference tables below.** Two of the
281 cached matches are not Night Shift games. They are ordinary public games
that the wiki lists under a Night Shift bracket, so a wrong `matchid=` was
typed and we ingested it faithfully.

| Match | Listed as | What it actually is |
| --- | --- | --- |
| `44465516` | #9 NA challenger | A public 6v6 match, `match_mode: 1` |
| `83756240` | #39 EU challenger | A **Street Brawl** game, `game_mode: 4`, 4v4 |

Three signals agree, and each was computed independently of the others:

1. **Hero picks.** Scoring every cached game against the wiki's own hero
   picks, 265 of 273 match 6 of 6 and 6 match 5 of 6. These two match **2 of
   6**. There is nothing else in the distribution between 2 and 5.
2. **Match mode.** All 279 other cached games are `match_mode: 2`, a custom
   lobby. These two are `match_mode: 1`, public matchmaking. Night Shift is
   not played in matchmaking.
3. **Duration.** Wiki length agrees with `duration_s` to within 2 seconds on
   269 of 276 games. These two are out by **218 and 630 seconds**. This is the
   weakest of the three signals: match `85256685`, added later and confirmed
   genuine by a 6 of 6 hero match, is out by 112 seconds, so a large delta
   alone is a prompt to look rather than a verdict.

`83756240` is worth looking at directly, because it explains several oddities
recorded elsewhere in this file. It has 8 players (4 per side), `game_mode: 4`,
a populated `street_brawl_rounds` of 5 rounds, a non-empty `team_score` of
`[2, 3]`, and a `net_worth` of exactly `48000` for all 8 players, which is how
Street Brawl works. It is not a 6v6 game and never was.

**What this corrects:**

- "One match in the cache has 8 players, read the count" is true but misleading.
  The 8 player match is not a Night Shift match. Code should still read the
  count rather than assume 12, since that costs nothing, but the exception is
  contamination and not a property of tournament games.
- "`match_mode: 2` is not universal, do not filter on it" [R2] was the wrong
  lesson. **Every genuine Night Shift game in the cache is `match_mode: 2`.**
  Filtering on it would have caught both bad IDs on ingest. It is a usable
  integrity check, though the hero pick join is the stronger one because it
  also catches a wrong ID that happens to be another custom lobby.
- "2 mode 1 matches carry a real badge of 11" was wrong on the count.
  **Only `44465516` carries 11.** `83756240` is mode 1 and carries `0`, so
  even the "mode 1 populates the badge" mechanism is not universal, and
  Street Brawl looks like another case Valve does not populate.

**Not yet removed from the cache.** Dropping them changes headline counts
that appear across every document here (281 matches, 3,368 player-games), so
it is a decision to take deliberately rather than a side effect of a doc fix.
Until then, every count in this file includes both.

---

## Rate limits, and why they look inconsistent

**This section is read from the API's own OpenAPI spec at
`https://api.deadlock-api.com/openapi.json`, not from our own probing.** It is
documentation, not an observed fact, and is marked as such. The 3/hour figure
below was separately confirmed live: a cold match returned HTTP 429 carrying
`ratelimit-limit: 3`, `ratelimit-period: 3600`, `retry-after: 1575`.

The limit on `GET /matches/{match_id}/metadata` is **not one number**. It
depends on which tier serves the request:

| Tier | IP | With API key | Global |
| --- | --- | --- | --- |
| From Cache | 100 req/s | 100 req/s | 100 req/s |
| From S3 | 100 req/10s | 100 req/s | 700 req/s |
| **From Steam** | **3 req/hour** | **300 req/hour** | 1500 req/hour |

"From Steam" means the API does not hold the match and has to pull it from
Valve on our behalf. That is the expensive path and it is throttled roughly
33,000 times harder than the cached path.

**This explains a result that otherwise looks impossible.** Backfilling 258
matches at 0.25s spacing succeeded with no rate limiting at all, and then 13
matches from the same list refused to fetch at more than 3 per hour. Nothing
changed at the API and our spacing was not at fault. The 258 were already in
their cache or S3; the 13 are cold and each one costs a Steam pull. A match
being old does not predict this, and there is no documented way to ask which
tier a given match will hit without requesting it.

**Cold is a temporary state, and waiting is a real strategy.** On 2026-07-28
the bulk endpoint was asked about all 14 outstanding IDs in one request. It
held **11 of the 14**, and all 11 then fetched through the normal metadata
endpoint in about 0.3 seconds each with no rate limiting. They had been cold a
day earlier. The likely mechanism is that a 429'd cold request still queues the
Steam pull, so yesterday's failures warmed the cache for today. Only 3 remain
genuinely cold: `38766744`, `92586699`, `92592573`.

The practical rule: **before running `backfill_cold.py`, spend one bulk request
asking which IDs are actually cold.** It costs nothing and in this case it
turned a five hour drip into a 30 second fetch.

Practical consequences:

- **Spacing does not help a cold match.** No polite delay converts a 3/hour
  budget into a workable one. Only a key, or the bulk endpoint, does.
- **An API key raises the cold path 100x**, from 3/hour to 300/hour. Keys are
  tied to sponsorship (Patreon or GitHub Sponsors), with the project Discord
  `https://discord.gg/XMF9Xrgfqu` as the contact route. We do not have one.
- `GET /matches/{match_id}/metadata/raw` carries **identical** limits, so
  dropping to the raw protobuf buys nothing.

### `GET /matches/metadata`, the bulk endpoint we were not using

Undocumented in these notes until now, and it changes the backfill story.

Takes `match_ids` as a comma separated list, **up to 1000 per call**, with a
`limit` up to 10000 and optional `format=ndjson`. Rate limit is **10 req/min
per IP**, with no Steam tier listed, which is consistent with it being served
from their own store rather than pulled from Valve.

Two cautions before relying on it:

- **`match_mode` defaults to `ranked,unranked`, which excludes Night Shift.**
  Tournament games are private lobbies. The filter has to be set explicitly or
  the response comes back empty and looks like the matches do not exist.
- Being served from their store means it can only return matches they already
  hold. It is not a way to force a cold match to be ingested. It is, however, a
  single cheap request that tells us **which** of our missing matches are cold,
  instead of discovering it one 429 at a time.

### What the bulk endpoint actually returns, measured

**Probed 2026-07-28.** Three things the spec does not make obvious:

1. **By default it is a summary, not metadata.** Two matches came back in
   **523 bytes**, with `match_id`, `start_time`, `winning_team`, `duration_s`,
   `match_outcome`, `match_mode`, `game_mode`, the badge fields, `not_scored`
   and `banned_hero_ids`. **No `players` array at all.** As a cold check that
   is ideal, and as a data source it is useless on its own.
2. **`include_player_final_stats=true` adds the players**, at about 13 KB per
   match against roughly 1.1 MB for full metadata. Each player carries
   `account_id`, `hero_id`, `player_slot`, `team`, `hero_build_id` and a
   `final_stats` object that does include `net_worth` and `player_damage`.
3. **A 404 means "we hold none of these", and it is an answer rather than an
   error.** Measured: requesting only the 3 known cold IDs returns HTTP 404,
   while requesting one warm ID plus one cold one returns 200 with just the
   warm entry. So the endpoint 404s when its result set would be empty.
   Reading that as a failed request is what made the first end to end
   `publish.py` run fall back to fetching cold matches and then die on their
   404s.
4. `match_mode` here takes **names, not integers**. Valid values are
   `unranked`, `private_lobby`, `coop_bot`, `ranked`, `server_test`,
   `tutorial`, `hero_labs`, and Night Shift is `private_lobby`. The default of
   `ranked,unranked` excludes every tournament game, so an unfiltered request
   returns empty and looks like the matches do not exist.

**Do not swap `final_stats` in for the top-level player fields.** Checked
against our own cache on match `95172627`, `final_stats` reproduces the final
`stats[]` entry exactly on all of `net_worth`, `kills`, `deaths`, `assists` and
`player_damage`. But the final `stats[]` entry is **not** the same as the
top-level `players[]` fields, and across 3,216 cached tournament player-games
they disagree far more often than expected:

| Field | Player-games where the final series sample differs from the top-level field | Largest gap |
| --- | --- | --- |
| `kills` | 894 (27.8%) | 4 |
| `deaths` | 921 (28.6%) | 3 |
| `assists` | 229 (7.1%) | 2 |
| `net_worth` | 45 (1.4%) | 201 |

So the time series is a periodic snapshot that misses end-of-game events, even
though its last `time_stamp_s` equals `duration_s`. The app's current split is
the right one and should stay: **top-level fields for K/D/A and net worth,
`stats[]` only for damage**, which has no top-level equivalent. Adopting
`final_stats` wholesale would silently change a quarter of all kill and death
figures.

---

## `GET /matches/{match_id}/metadata`

Top level is an object with exactly three keys:

| Key | Type | Notes |
| --- | --- | --- |
| `match_info` | object | Everything useful |
| `hero_build_ids` | object | Map of `account_id` (as string) to build ID (int) |
| `banned_hero_ids` | array | Empty on **281/281** |

### `match_info` fields

All 31 fields are present on **281/281** cached matches. Types observed:

| Field | Type | Notes |
| --- | --- | --- |
| `match_id` | int | |
| `duration_s` | int | Seconds. Range across the 279 genuine matches: **1165 to 3056**. |
| `start_time` | int | Unix seconds, UTC |
| `winning_team` | int | `0` or `1`. **The authoritative win field.** 281/281. |
| `match_mode` | int | `2` on **all 279** genuine Night Shift games. `1` is public matchmaking, and the only 2 cached are the contaminated IDs above. |
| `game_mode` | int | `1` on 280/281. The exception is `4`, Street Brawl, on `83756240`. |
| `players` | array | 12 entries on 280/281. The exception has 8 and is not a Night Shift game. **Read the count anyway**, it is free. |
| `match_outcome` | int | **Always `0`**, 281/281, including on matches won by team 1. Useless. |
| `average_badge_team0` | int | **`0` on 280/281.** See below. |
| `average_badge_team1` | int | **`0` on 280/281.** See below. |
| `teams` | array | **Present on 171/281, absent on 110.** Where present, every entry is `{team: int, team_tracked_stats: []}`. **No team identity, no score.** |
| `team_score` | array | Empty on 280/281. Non-empty only on the Street Brawl match, where it is a round score `[2, 3]`. |
| `objectives_mask_team0` / `1` | int | Bitmask, not decoded here |
| `objectives` | array | Populated, not decoded here |
| `damage_matrix` | object | Populated. Potentially useful, not explored yet. |
| `match_paths` | object | Populated, not decoded here |
| `mid_boss` | array | Populated |
| `match_tracked_stats` | array | Populated |
| `custom_user_stats` | array | Populated |
| `match_pauses`, `street_brawl_rounds`, `watched_death_replays` | array | Empty on all 12 |
| `legacy_objectives_mask` | null | Always null |
| `bot_difficulty`, `game_mode_version` | int | |
| `low_pri_pool`, `new_player_pool`, `not_scored`, `rewards_eligible`, `is_high_skill_range_parties` | bool | |

### `average_badge_team0` / `average_badge_team1`

**Do not use these.** Present and typed `int` on every match, and equal to
`0` on **all 279 genuine tournament matches**. Not null, not absent, so
`?? null` and `|| null` both fail to catch it.

Control test: public match `95694731` (`match_mode: 1`) returns `116` for
both teams. The field works, Valve simply never populates it for custom
lobbies, and every Night Shift game is a custom lobby.

The one cached match returning a non-zero badge is `44465516`, at `11` for
both teams, and it is a public game wrongly listed on the wiki rather than a
Night Shift game. The other contaminated match is mode 1 and still returns
`0`, so "mode 1 means the badge is populated" is a tendency too, not a rule.

### `players[]` fields

28 fields, all present on **3368/3368** player-games. The ones that matter:

| Field | Type | Notes |
| --- | --- | --- |
| `account_id` | int | 32-bit Steam account ID, not SteamID64 |
| `team` | int | `0` or `1`. **Explicit, never inferred.** See team assignment below. |
| `player_slot` | int | `1` to `12`, unique within a match |
| `hero_id` | int | Joins to `/assets/heroes` `id` |
| `net_worth` | int | Final souls |
| `kills`, `deaths`, `assists` | int | |
| `last_hits`, `denies`, `level`, `ability_points` | int | |
| `assigned_lane` | int | Only values `1`, `4`, `6` observed across **3368** player-games, near enough evenly split (1078 / 1080 / 1078). Not the 1-to-6 range you might assume. |
| `mvp_rank` | int or null | Only nullable scalar on the player object |
| `stats` | array | Time series, see below |
| `abandon_match_time_s` | null | Always null in cache |
| `earned_holiday_award_2025` | null | Always null in cache |
| `items`, `ability_stats`, `death_details`, `accolades`, `pings`, `book_rewards`, `power_up_buffs`, `player_tracked_stats`, `stats_type_stat` | array | Populated, not decoded here |
| `hero_data` | object | Populated, not decoded here |
| `rewards_eligible` | bool | |

**Damage is not a top-level player field.** It lives only in
`players[].stats[]`.

### `players[].stats[]`

A periodic time series, roughly one entry every four minutes (9 entries on a
2075 second match). Each entry has 50 fields, including `player_damage`,
`player_damage_taken`, `player_healing`, `net_worth`, `kills`, `deaths`,
`assists`, `level`, `shots_hit`, `shots_missed`, `creep_damage`,
`neutral_damage`, `boss_damage`, and a set of `gold_*` source breakdowns.

To get end-of-game damage, take the entry with the highest `time_stamp_s`
and read `player_damage`. Verified on **3368/3368 player-games**, no misses,
and the highest `time_stamp_s` equals `duration_s` exactly on every one, so
that entry really is the final snapshot rather than a truncated one. This is
the best tested claim in this file.

---

## Team and side assignment: explicit, not inferred

`players[].team` is an `int` that is always present and always `0` or `1`.
The split is exactly six per team on **280 of 281** matches. The exception is
the Street Brawl contaminant, which is 4 and 4.

`player_slot` maps to team deterministically on the same **280 of 281**:

- slots `1` to `6` are team `0`
- slots `7` to `12` are team `1`

Both were checked across all 3,368 player-games; they never disagreed except
on that one match. `team` is the field to use, with `player_slot` available as
a cross-check.

**Win determination:** a player won if `players[].team == match_info.winning_team`.
Do not use `match_outcome`, which is `0` on every match regardless of who won.

**What the API does not give you:** which real-world team a `team: 0` or
`team: 1` corresponds to. The `teams[]` array contains only
`{team, team_tracked_stats: []}` with an empty stats list, and `team_score`
is empty. Team identity is purely positional within a single match, and
carries no meaning across matches. This is one of the two gaps the curated
dataset in step 3 has to fill.

---

## `GET /players/{account_id}/match-history`

**Yes, this endpoint exists and it does return match history for a given
account ID.** This directly answers the step 2 question.

Returns a bare JSON **array** (not wrapped in an object). Two players probed:
account `244109796` returned 2,101 entries spanning 2024-08-24 to 2026-07-26;
account `1009703898` returned 3,536 entries.

**It includes tournament matches.** Of `244109796`'s 2,101 entries, 426 are
`match_mode: 2`. For `1009703898`, 364 of 3,536. Every cached Night Shift
match that a probed player appeared in was present in their history: 6/6 for
the first player, 3/3 for the second, with zero missing.

Fields, all present on every entry sampled (2,000 per player):

| Field | Type | Notes |
| --- | --- | --- |
| `match_id` | int | Joins to the metadata endpoint |
| `account_id` | int | Same for every entry, echoes the request |
| `hero_id` | int | |
| `player_team` | int | `0` or `1`, this player's side |
| `match_result` | int | **See the warning below** |
| `start_time` | int | Unix seconds |
| `match_duration_s` | int | |
| `match_mode`, `game_mode` | int | `match_mode: 2` is tournament |
| `player_kills`, `player_deaths`, `player_assists` | int | Note the `player_` prefix, unlike the metadata endpoint |
| `net_worth`, `last_hits`, `denies`, `hero_level` | int | |
| `objectives_mask_team0` / `1` | int | |
| `abandoned_time_s` | int or null | |
| `team_abandoned` | bool or null | |
| `brawl_score_team0` / `1`, `brawl_avg_round_time_s` | int or null | Null outside brawl modes |

### `match_result` is the winning team, not a win flag

This reads like "did I win", and it is not. It is the **index of the winning
team**, the same value as `winning_team` in match metadata.

Cross-checked 9 player-match pairs across 2 players against the cached
metadata:

- `match_result == winning_team`: **9/9**
- `match_result == (did this player win)`: **3/9**

The 3 that matched did so only because that player happened to be on team 0.

**To determine a win from history alone:** `match_result == player_team`.

There is no damage field in match history. Damage requires the metadata
endpoint.

---

## `GET /players/steam?account_ids=<csv>`

Takes **SteamID64**, but match data gives 32-bit `account_id`. Convert with
`account_id + 76561197960265728`.

Returns an array, one object per requested ID. All fields present on both
probed profiles:

| Field | Type | Notes |
| --- | --- | --- |
| `account_id` | int | 32-bit, echoed back |
| `personaname` | string | Current Steam display name |
| `profileurl` | string | `/id/<vanity>` or `/profiles/<steamid64>` |
| `avatar`, `avatarmedium`, `avatarfull` | string | |
| `realname` | string or null | Null on both probed |
| `countrycode` | string or null | |
| `last_team_avg_badge` | int | Populated, but see below |
| `matches_played_last_30d` | int | |
| `last_updated` | string | ISO 8601 timestamp |
| `friends` | array | Objects of `{account_id, friend_since}`. Noted for privacy: this returns a social graph. |

### `last_team_avg_badge`, now tested properly

**Re-tested 2026-07-28 on all 155 accounts that appear in a genuine tournament
match**, up from the 45 the original claim rested on. Reproduce with
`python scripts/check_badge_spread.py`, which fetches the field, counts it in
memory, and **writes nothing per account**, because the field is deliberately
outside the `fetch_steam.py` allowlist and stays there.

| Badge | Players | Share |
| --- | --- | --- |
| 116 | 120 | 77.4% |
| 115 | 8 | 5.2% |
| 114 | 1 | 0.6% |
| 113 | 1 | 0.6% |
| 104 | 1 | 0.6% |
| **null** | **24** | **15.5%** |

**The conclusion holds and the old wording did not.** Of the 131 accounts
returning a value, **128 (97.7%) are 115 or 116**, a two point range at the
very top of the ladder. A six player team average drawn from that pool cannot
differ from another by enough to mean anything, so badge still cannot separate
Night Shift teams and the Opposition column stays dead.

Two corrections to what this file used to say:

- "115 or 116 for every one of them" is **false** at this sample size. Three
  accounts sit lower, one of them at 104, which is a different tier entirely.
- **24 accounts return `null`**, which the 45 profile sample never showed at
  all. Any code reading this field has to handle null, and a naive average
  over 155 accounts would silently be an average over 131.

---

## `GET /assets/heroes?only_active=false`

Returns an array of 57 hero objects.

| Field | Type | Coverage |
| --- | --- | --- |
| `id` | int | 57/57, joins to `players[].hero_id` |
| `name` | string | 57/57 |
| `class_name` | string | 57/57 |
| `hero_type` | string | **37/57** |
| `disabled`, `in_development`, `player_selectable` | bool | 57/57 |
| `complexity` | int | 57/57 |
| `images` | object | 57/57 |

`hero_type` is Deadlock's own archetype (`m_eHeroType`), one of `assassin`,
`brawler`, `marksman`, `mystic`. The 20 heroes missing it are almost all
`disabled: true`. Among the 38 active heroes, exactly one (Rem) lacks it.
Across the cache, **3319/3368 player-games, 98.5%**, resolve to a role, and
all 49 gaps are hero 79. The earlier figure of 143/144, 99.3%, came from 12
matches and was slightly optimistic.

Icons: `images.icon_image_small` is present on every active hero.

---

## `GET /leaderboard/{region}`

Regions confirmed as valid values in the console app: `Europe`, `NAmerica`,
`Asia`, `SAmerica`, `Oceania`. Only `Europe` was probed.

Returns an **object** with a single key `entries`, an array of 1,000.

| Field | Type | Notes |
| --- | --- | --- |
| `account_name` | string | Display name |
| `possible_account_ids` | array of int | **Candidates, not an ID.** See below. |
| `rank` | int | 1 to 1000 |
| `badge_level` | int | `115` or `116` across the whole EU top 1000 |
| `ranked_rank`, `ranked_subrank` | int | `11` and `6` decompose `116` |
| `top_hero_ids` | array of int | |

### `possible_account_ids` is ambiguous and often badly so

This is a resolution guess, not an identity. Distribution across the 1,000 EU
entries:

- Exactly one candidate: **583 (58%)**
- Zero candidates: 36
- Two or more: 381, with a long tail reaching **5,199 candidates** for a
  single entry

So the leaderboard cannot be used as an authoritative name-to-account-ID
mapping. It is a hint at best. Of the 45 distinct Night Shift account IDs in
the cache **at the time this was probed**, 20 appear somewhere in the EU
candidate lists, but appearing in a candidate list is not the same as being
identified. The cache now holds **170** distinct accounts and the overlap has
not been re-measured, so treat the 20 as a figure about the old sample.

This reinforces that account-ID-to-player mapping has to be hand-curated.

---

## `GET /matches/active`

Returns an array of live matches, 150 at time of probing.

Notable: `duration_s`, `winning_team`, and `winning_team_parsed` are **null
on all 150**, as expected for in-progress games. Includes `match_id`,
`lobby_id`, `start_time`, `match_score`, `net_worth_team_0` / `_1`,
`spectators`, `open_spectator_slots`, `players`, and human-readable
`*_parsed` variants of `game_mode`, `match_mode`, and `region_mode`.

---

## `GET /patches/big-days`

Returns a bare array of 15 ISO 8601 timestamp strings, newest first. Most
recent at probe time: `2026-03-11T04:39:40Z`.

**"All cached matches postdate it" was true of the 12 match cache and is now
false.** Against that boundary the 281 cached matches split **144 after and
137 before**, and the cache spans 2025-08-13 to 2026-07-23. That is the
finding behind the data window decision recorded in `CLAUDE.md`: a patch
scoped window is no longer a small slice of the data, but it is also no
longer the whole of it.

---

## What the API cannot tell you

These are the gaps the curated dataset has to fill, and they are not
solvable with more probing:

1. **Which matches belong to which tournament night.** Nothing in the match
   payload references an edition, bracket stage, or event. `match_mode: 2`
   only says "custom lobby", which includes any private game.
2. **Which account ID is which player, on which team.** `team` is positional
   per match and carries no identity. The leaderboard's `possible_account_ids`
   is ambiguous 42% of the time. Steam `personaname` is a current display
   name, not a tournament handle, and changes freely.

Item 2 is why the alias and team-tag files are the most valuable data in the
repository: they are not reproducible from any endpoint.
