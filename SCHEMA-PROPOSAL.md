# Versioned dataset schema, proposal

Status: **accepted, decisions recorded below.** See "Decisions" at the end for
the five points that were open at review and how they were resolved.

Covers matches, players, teams, and match nights, and holds the two things no
endpoint can give (see `API-NOTES.md`): which matches belong to which
tournament night, and which account ID is which player on which team.

---

## Governing principle: curated and derived are different kinds of thing

| | Curated | Derived |
| --- | --- | --- |
| Written by | You, by hand | `scripts/build_dataset.py` |
| If deleted | **Gone forever** | Rebuild in seconds |
| Reviewed in git | Line by line, carefully | Skim the diff |
| Source of truth for | Night membership, identity, rosters | Nothing |

The two never share a file. Every hand-curated fact lives in a file that a
generator will never write to, so no script can ever clobber your work.

### The exception: reviewed appliers

**Settled 2026-07-28, so it does not get re-litigated.**

The rule's intent is that **generated output never contaminates curation**. It
is not that curated files may only be typed by hand. Naming 82 accounts by
hand from a candidate file would be slower and would introduce transcription
errors into the one layer that cannot be rebuilt, which is the opposite of
what the rule protects.

So a script may write to `data/curated/` if, and only if, it meets **all** of:

1. **It is not part of any build.** No pipeline calls it. `build_dataset.py`
   and `build_site.py` must never invoke it, directly or otherwise.
2. **It is gated on an explicit flag.** The default run reports what it would
   do and writes nothing.
3. **It never overwrites a curated value with a different one.** A
   disagreement is reported and the curated value survives, because a human
   put it there on evidence the script cannot see.
4. **It never downgrades.** An existing `confirmed` is not lowered.
5. **Its refusals are in code, not in silence.** An account the script
   declines to apply carries its reason inline, so the decision is reviewable.
6. **Its output is reviewed as a diff before committing.** The applier makes
   the edit; git is where it gets approved.

`scripts/apply_identities.py` is the first of these and is the reference
implementation. The distinction to hold on to: a **generator** derives facts
and owns its output file, so it may rewrite it wholesale at any time. An
**applier** transcribes reviewed decisions into a file it does not own, and
must therefore be conservative about everything already there.

What is still forbidden, and is the actual failure this rule exists to
prevent: a build step that regenerates curated data as a side effect of
running. That would make the curated layer reproducible-looking while
silently discarding the human judgement in it, and the loss would not show up
until someone needed a fact that no longer existed.

---

## Layout

```
data/
  matches/                        raw API cache (exists)
  artifacts/                      immutable artifacts (exists)
  assets/
    heroes-2026-07-27.json.gz     dated snapshot, see "Hero snapshots"
  curated/                        HAND EDITED, IRREPLACEABLE
    teams.json
    players.json
    nights/
      2026-07-08-ns046-na.json
      2026-07-09-ns046-eu.json
      2026-07-15-ns047-na.json
      2026-07-20-ns048-eu.json
      2026-07-22-ns048-na.json
    schema/
      teams.schema.json
      players.schema.json
      night.schema.json
  derived/
    dataset.json                  generated, safe to delete
```

Filenames sort chronologically and carry edition and region. **There is no
index file listing the nights.** The builder globs the directory. An index
would be a second source of truth that drifts out of sync, which is the exact
bug class that already bit this project once.

---

## `curated/teams.json`

```json
{
  "schema_version": 1,
  "teams": {
    "six-gate": {
      "name": "Six Gate",
      "tag": "6G",
      "region": "na",
      "active": true,
      "notes": ""
    },
    "aftermath": {
      "name": "Aftermath",
      "tag": "AFT",
      "region": "na",
      "active": true,
      "notes": "Rebranded from Late Shift after edition 44."
    }
  }
}
```

The key (`six-gate`) is the permanent identity and never changes, including
through a rebrand. Only `name` and `tag` change. That way a team's history
stays continuous instead of splitting into two teams when they rename.

**No team object contains a team index, and none ever will.** See the
separation rules below.

---

## `curated/players.json`

```json
{
  "schema_version": 1,
  "players": {
    "244109796": {
      "handle": "JonJon69",
      "aka": ["JonJon"],
      "identified": "confirmed",
      "notes": "Confirmed via team roster post, edition 47."
    },
    "1285605078": {
      "handle": "reyache",
      "aka": [],
      "identified": "probable",
      "notes": "Steam persona matches bracket name, not otherwise confirmed."
    }
  }
}
```

Keys are `account_id` as a string, because JSON object keys must be strings.

`identified` is one of `confirmed`, `probable`, `guess`. This exists because
the identity mapping is genuinely uncertain in places, and a page that renders
a guessed name identically to a confirmed one is quietly lying. The site can
mark anything below `confirmed`, or omit it.

**A player record contains no team.** Team membership changes between weeks
and is recorded per night, below.

---

## `curated/nights/2026-07-22-ns048-na.json`

This is the file that does the real work.

```json
{
  "schema_version": 1,
  "night_id": "ns048-na",
  "series": "night-shift",
  "edition": 48,
  "region": "na",
  "date": "2026-07-22",
  "date_note": "Local broadcast date. Match start_time is UTC and rolls to 2026-07-23.",
  "source": "https://lockblaze.com/tournament/night-shift-48",
  "rosters": [
    {
      "team_id": "six-gate",
      "players": [
        { "account_id": "244109796", "status": "starter" },
        { "account_id": "1285605078", "status": "starter" },
        { "account_id": "924812291", "status": "starter" },
        { "account_id": "1871217631", "status": "starter" },
        { "account_id": "25821887", "status": "starter" },
        { "account_id": "1840902834", "status": "stand-in" }
      ]
    },
    {
      "team_id": "aftermath",
      "players": [
        { "account_id": "114943410", "status": "starter" },
        { "account_id": "1871021649", "status": "starter" },
        { "account_id": "1730032433", "status": "starter" },
        { "account_id": "1929248273", "status": "starter" },
        { "account_id": "1477660209", "status": "starter" },
        { "account_id": "399289886", "status": "starter" }
      ]
    }
  ],
  "matches": [
    {
      "match_id": "95172627",
      "stage": "final",
      "series_label": "Grand Final",
      "game_in_series": 1,
      "sides": [
        { "match_team_index": 0, "team_id": "six-gate" },
        { "match_team_index": 1, "team_id": "aftermath" }
      ]
    }
  ]
}
```

Account IDs and the `winning_team` above are real, taken from the cached
match. Team names are placeholders.

Notes on specific fields:

- **`rosters` is per night, not global.** This is what makes roster churn,
  stand-ins, and players switching orgs work without rewriting history. Next
  week you copy this file and adjust. The duplication is deliberate: each
  night records what was true that night.
- **`status`** is `starter` or `stand-in`. A stand-in's stats should probably
  not count toward a team's season aggregates, and that is impossible to
  reconstruct later if it is not recorded now.
- **`stage`** is `qualifier`, `challenger`, `final`, or `other`. This is the
  only honest handle on the format bias described in `CLAUDE.md`, since badge
  fields cannot separate these teams.
- **`game_in_series`** supports Bo3. Qualifier and final are Bo3, challenger
  is Bo1.
- **`date_note`** exists because of a real discrepancy already found: the
  matches currently labelled "#48 Europe (July 22)" in
  `data/match-ids/night-shift.txt` actually start on **2026-07-20**, and the
  NA matches labelled July 22 start on 2026-07-23 UTC. Local broadcast date
  and UTC match date are not the same thing, and the validator checks this
  rather than trusting a comment.

---

## How the three requirements are enforced structurally

### 1. Match-scoped team index never leaks into persistent identity

The integer 0/1 appears in exactly **one** place in the whole curated layer:
inside `matches[].sides[].match_team_index`, physically adjacent to the
`team_id` it maps to, inside a single match object.

- `teams.json` has no index field.
- `players.json` has no team field at all.
- `rosters[]` references `team_id` only.
- The field is named `match_team_index`, not `team`, so its scope is legible
  at every use site.

In `derived/dataset.json`, each `player_matches` row carries both
`match_team_index` and the resolved `team_id`. The index is retained only
because team-relative denominators (team net worth total, team kills) must be
computed within that match. It is **never** used as a join key, a grouping
key, or a sort key across matches.

Validator rules:

- `match_team_index` must be exactly `0` and `1`, once each, per match.
- No key named `team`, `team_index`, or `side` may exist outside a
  `sides[]` entry.
- Grouping any aggregate by `match_team_index` across more than one match is
  a build error.

### 2. `winning_team` is the only outcome stored

- `derived.matches[].winning_team_index` is copied verbatim from
  `match_info.winning_team`.
- **No win flag is persisted anywhere**, at match level or player level. No
  `won`, `is_win`, `result`, `outcome`.
- Win is computed at render time as
  `player_matches.match_team_index == matches.winning_team_index`.
- **The builder reads `/matches/{id}/metadata` only.** The match-history
  endpoint is never an input to the dataset, so `match_result` cannot enter
  even by accident. Given that `match_result` is the winning team index and
  not a win flag (verified 9/9, see `API-NOTES.md`), the safest guarantee is
  that the field is never read at all.

Validator rules:

- The string `match_result` must not appear anywhere in `dataset.json`.
- No boolean field whose name matches `won|win|victor|result` may exist.

### 3. The Steam `friends` array never enters, by allowlist

Steam ingestion applies an **allowlist before anything touches disk**, so the
social graph is discarded in memory and is never written, cached, or
committed.

Permitted into the dataset:

| Field | Why |
| --- | --- |
| `account_id` | Join key |
| `personaname` | Display-name fallback when no curated handle exists |
| `profileurl` | Source of the vanity slug fallback |
| `countrycode` | Self declared, public, conventional in esports |
| `avatarmedium` | Source URL only, the image is downloaded and stored locally |

Excluded by construction: **`friends`** (a full social graph),
`realname` (a real legal name, not a handle), `last_updated`,
`last_team_avg_badge` (useless at this level anyway),
`matches_played_last_30d`.

The allowlist was deliberately widened at review rather than kept minimal,
because raw Steam responses are not cached and narrowing it now would mean
re-fetching later.

**Avatars are not hotlinked.** Serving `avatarmedium` directly from Steam's
CDN on a public page would leak every visitor's IP to Valve and break if
Steam rotates URLs. The image is fetched once, stored under
`data/assets/avatars/<account_id>.jpg`, and the site references the local
copy. Only the source URL is retained in the dataset, for provenance.

Validator rule: a recursive scan of `dataset.json` must find no key named
`friends`, at any depth.

This has a cost worth naming: unlike match metadata, **raw Steam responses
are not cached**. Wanting another Steam field later means re-fetching. That
is the deliberate price of guaranteeing the social graph never lands on disk.

---

## `derived/dataset.json`

```json
{
  "schema_version": 1,
  "generated_utc": "2026-07-27T12:00:00Z",
  "source": {
    "generator": "scripts/build_dataset.py",
    "git_commit": "c2fda40",
    "matches_ingested": 12,
    "nights_ingested": 5,
    "heroes_snapshot": "data/assets/heroes-2026-07-27.json.gz"
  },
  "teams": [ { "team_id": "six-gate", "name": "Six Gate", "tag": "6G" } ],
  "players": [
    {
      "account_id": "244109796",
      "handle": "JonJon69",
      "identified": "confirmed",
      "steam": { "personaname": "JonJon69", "avatarmedium": "https://...", "profileurl": "https://..." }
    }
  ],
  "nights": [ { "night_id": "ns048-na", "edition": 48, "region": "na", "date": "2026-07-22" } ],
  "matches": [
    {
      "match_id": "95172627",
      "night_id": "ns048-na",
      "stage": "final",
      "game_in_series": 1,
      "start_time": 1784772175,
      "duration_s": 2075,
      "winning_team_index": 0,
      "sides": [
        { "match_team_index": 0, "team_id": "six-gate" },
        { "match_team_index": 1, "team_id": "aftermath" }
      ],
      "totals": {
        "0": { "net_worth": 245134, "kills": 41, "damage": 178420 },
        "1": { "net_worth": 198765, "kills": 22, "damage": 151203 }
      },
      "lobby": { "net_worth_avg": 36992 }
    }
  ],
  "player_matches": [
    {
      "match_id": "95172627",
      "account_id": "244109796",
      "match_team_index": 0,
      "team_id": "six-gate",
      "roster_status": "starter",
      "hero_id": 65,
      "kills": 9, "deaths": 2, "assists": 8,
      "net_worth": 52682,
      "damage": 29750
    }
  ]
}
```

### Design principle: store numerator and denominator, never just the ratio

Every percentage the site will show has both of its inputs present in the
data. "31% of team damage" is backed by `damage` on the player row and
`totals["0"].damage` on the match row. Nothing displayed is an opaque number
that cannot be traced back to two integers from the API.

This is deliberate given the "stats must be defensible" requirement, and it
means a reader who doubts a figure can check it, and a future bug in the
ratio maths cannot silently corrupt stored history.

---

## Hero snapshots

`hero_type` drives archetype comparisons and `/assets/heroes` changes across
patches. If a hero's `hero_type` is edited by Valve, every historical page
silently changes meaning.

Proposal: snapshot the hero assets to `data/assets/heroes-<date>.json.gz` on
each build where the content hash changes, and record which snapshot a build
used. Small, and it makes old pages reproducible.

---

## Validation, run on every build

Reported, never silently corrected:

| Check | Failure mode it catches |
| --- | --- |
| Match in a night file but not cached | Typo'd match ID, or forgot to fetch |
| Cached match in no night file | Orphan, possibly a scrim that got pasted in |
| `account_id` in a match but not in `players.json` | Unmapped player, page would show a bare number |
| Roster lists a player who did not play that match | Roster drift or a stand-in not recorded |
| **Side mapping disagrees with rosters** | **Swapped 0/1, see below** |
| Night `date` more than 2 days from its matches' `start_time` | Mislabelled edition, already observed |
| `team_id` or `account_id` referenced but undefined | Broken reference |
| Duplicate `match_id` across night files | A match assigned to two nights |

### The side-mapping check is the important one

A swapped `sides` mapping is invisible: the page renders, the numbers look
plausible, and every stat is attributed to the wrong team. Nothing about the
output would look wrong.

The check: for each side, compute the overlap between the curated roster of
the mapped team and the account IDs actually on that `match_team_index`.
Expect a strong majority. If swapping the two assignments would produce a
better overlap, fail the build and say so.

On match 95172627 the two sides are
`[244109796, 1285605078, 924812291, 1871217631, 25821887, 1840902834]` and
`[114943410, 1871021649, 1730032433, 1929248273, 1477660209, 399289886]`, so
a correct mapping scores 6/6 and a swapped one scores 0/6. The check is
decisive in practice.

---

## Versioning and migration

- Every file carries `schema_version` as its first key.
- `curated/schema/*.schema.json` are JSON Schema (draft 2020-12) documents.
  They serve as the written spec and give editor autocomplete.
- **Validation is implemented in stdlib Python**, so no dependency is added.
  The `jsonschema` package would be tidier; I have not added it. Say the word
  if you want it.
- Curated files are migrated by an explicit, reviewed, committed change.
  Never auto-rewritten in place by a build.
- `derived/dataset.json` is regenerated wholesale and carries no history.

Unlike `data/artifacts/`, curated files are living documents and may be
edited. Their history lives in git.

---

## Decisions

Resolved at review. These are binding on the builder and the site generator.

1. **Regions are separate nights.** A night is one edition in one region.
   Editions may be grouped for display, but the underlying records are never
   merged, because the data shows the regions running on different days.
2. **Stand-ins count toward individual player stats, and are excluded from
   team aggregates.** They must be marked visibly wherever their games appear.
   This is why `roster_status` is recorded per night rather than inferred.
3. **`countrycode` is in the allowlist.** Self declared, public, conventional
   in esports, and not a social graph.
4. **Avatars are stored locally, never hotlinked.** See the Steam section.
5. **`identified: "guess"` gets no player page.** Such an account appears in
   match rows as an unnamed account ID and nothing more. A guessed identity is
   never published as a name. Pages exist only for `confirmed` and `probable`.

Both the numerator/denominator storage rule and the side-mapping validator
are retained as proposed.
