# API-NOTES.md

What `api.deadlock-api.com/v1` actually returns, established by real requests.

Every claim below was checked against live responses on **July 27 2026**,
using the 12 cached Night Shift matches (editions 46 to 48, 144 player-games)
plus live calls to each endpoint. Nothing here is taken from documentation or
inferred from field names. Where a field exists but is useless, that is stated
rather than left for someone to rediscover.

Counts like "144/144" mean the check ran over every player-game in the cache.

The API is community run, open source, and unofficial. CORS is wildcard-open,
no key and no proxy needed.

---

## Summary of the things that will bite you

| Finding | Detail |
| --- | --- |
| `match_result` is not win/loss | It is the **winning team index**. See below, verified 9/9. |
| `average_badge_team0/1` is always `0` on tournament games | Present, typed `int`, never populated for `match_mode: 2`. |
| `teams[]` and `team_score` are empty | Carry no team identity or score. |
| `match_outcome` is always `0` | Does not indicate who won. Use `winning_team`. |
| Leaderboard gives **candidate** account IDs | `possible_account_ids` is an array, exactly one candidate only 58% of the time. |
| Match history **does** exist per account | And it includes tournament matches. |

---

## `GET /matches/{match_id}/metadata`

Top level is an object with exactly three keys:

| Key | Type | Notes |
| --- | --- | --- |
| `match_info` | object | Everything useful |
| `hero_build_ids` | object | Map of `account_id` (as string) to build ID (int) |
| `banned_hero_ids` | array | Empty on all 12 tournament matches |

### `match_info` fields

All 31 fields are present on 12/12 cached matches. Types observed:

| Field | Type | Notes |
| --- | --- | --- |
| `match_id` | int | |
| `duration_s` | int | Seconds. Range in cache: 1694 to 2924. |
| `start_time` | int | Unix seconds, UTC |
| `winning_team` | int | `0` or `1`. **The authoritative win field.** |
| `match_mode` | int | `2` on all Night Shift games. `1` is public matchmaking. |
| `game_mode` | int | `1` on all cached matches |
| `players` | array | Always exactly 12 entries |
| `match_outcome` | int | **Always `0`**, including on matches won by team 1. Useless. |
| `average_badge_team0` | int | **Always `0`** on `match_mode: 2`. See below. |
| `average_badge_team1` | int | **Always `0`** on `match_mode: 2`. See below. |
| `teams` | array | Two entries, each `{team: int, team_tracked_stats: []}`. **No team identity.** |
| `team_score` | array | **Empty** on all 12 |
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
`0` on 12/12 cached tournament matches. Not null, not absent, so `?? null`
and `|| null` both fail to catch it.

Control test: public match `95694731` (`match_mode: 1`) returns `116` for
both teams. The field works, Valve simply never populates it for custom
lobbies, and every Night Shift game is a custom lobby.

### `players[]` fields

28 fields, all present on 144/144 player-games. The ones that matter:

| Field | Type | Notes |
| --- | --- | --- |
| `account_id` | int | 32-bit Steam account ID, not SteamID64 |
| `team` | int | `0` or `1`. **Explicit, never inferred.** See team assignment below. |
| `player_slot` | int | `1` to `12`, unique within a match |
| `hero_id` | int | Joins to `/assets/heroes` `id` |
| `net_worth` | int | Final souls |
| `kills`, `deaths`, `assists` | int | |
| `last_hits`, `denies`, `level`, `ability_points` | int | |
| `assigned_lane` | int | Only values `1`, `4`, `6` observed, 48 each. Not the 1-to-6 range you might assume. |
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
and read `player_damage`. Verified on **144/144 player-games**, no misses,
and the highest `time_stamp_s` equals `duration_s` exactly, so that entry
really is the final snapshot rather than a truncated one.

---

## Team and side assignment: explicit, not inferred

`players[].team` is an `int` that is always present and always `0` or `1`.
Across 144 player-games the split is exactly 72 / 72, six players per team
per match. Nothing needs to be inferred.

`player_slot` maps to team deterministically across all 12 matches:

- slots `1` to `6` are team `0`
- slots `7` to `12` are team `1`

Both were checked; they never disagreed. `team` is the field to use, with
`player_slot` available as a cross-check.

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

`last_team_avg_badge` is populated for all 45 Night Shift players but is
either `115` or `116` for every one of them, so it cannot separate teams at
this level of play.

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
Across the cache, **143/144 player-games** resolve to a role.

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
the cache, 20 appear somewhere in the EU candidate lists, but appearing in a
candidate list is not the same as being identified.

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
recent at probe time: `2026-03-11T04:39:40Z`. All cached Night Shift matches
postdate it, so the whole cache is within the current balance patch.

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
