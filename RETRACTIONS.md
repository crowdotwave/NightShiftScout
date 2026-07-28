# Retractions

The single home for claims this project stated, acted on, and later found
wrong. A claim is retracted **here first**, then the affected documents are
edited.

**Why this file exists.** Twice now a claim has been corrected in one file and
left standing in another. The `team1side` side mapping rule was retracted in
`LIQUIPEDIA-NOTES.md` while `session-notes.md` still presented it as a verified
fact and `PARTICIPATION-PROPOSAL.md` built a proposed validator on it. The
reference tables in `API-NOTES.md` kept 12 match figures while the summary at
the top of the same file carried the corrected ones. Correcting by hand does
not scale past two documents, and the failure is silent: a stale claim reads
exactly like a live one.

## How to use it

1. **Record the retraction here** with what was claimed, what is true, the
   evidence, and how the wrong claim came to be believed. The last part is the
   valuable bit, because the failure modes repeat.
2. **Add `forbidden` patterns** to the entry. These are regexes matched against
   every line of every tracked document by `scripts/check_retractions.py`,
   which exits non-zero if a retracted claim reappears anywhere.
3. **Then** edit the documents.

**To quote a retracted claim on purpose**, put its retraction id in square
brackets on the same line, for example `previously read "13 of 13" [R1]`. The
checker skips any line carrying the id of the retraction it would otherwise
trip. That keeps the correction history readable without disabling the guard.

Run it with `python scripts/check_retractions.py`, which makes no network
requests and reads only files already in the repository.

## The rule that follows from all of this

**No number in a document unless a committed script prints it.** Every count
below was wrong at some point because it was measured once, by hand, on a
convenient sample, and then copied. `scripts/verify_api_claims.py` writes
`data/derived/verified-facts.json` for exactly this reason: figures quoted in
prose should be traceable to a script anyone can re-run.

---

## R1: `team1side` is not the side of record

**Claimed:** in Liquipedia bracket markup, `team1side=amber` means
`match_team_index` 0 and `sapphire` means 1, "verified 13 of 13" against our
own match metadata, described as solved with zero exceptions.

**True:** it is a tendency, not a rule. Across 261 comparable games it is right
on 248, **95.02%**, and 12 of the 13 failures are complete 6 to 0 inversions.
The side of record is the **per-game hero pick join**, which resolves 273 of
the 281 games we hold with a median margin of 6 of 6 and needs no rosters.

**How it went wrong:** the 13 confirmations all came from editions #46 to #48,
three consecutive recent editions, which sit entirely inside the range where
the rule happens to hold perfectly. A clean 13 of 13 on a contiguous slice is
not evidence about the other 46 editions.

**Reproduce:** `python scripts/check_side_mapping.py`

```forbidden
verified 13 of 13
13 of 13 by joining
solved, 12 of 12, zero exceptions
```

---

## R2: `match_mode: 2` is universal for genuine Night Shift games

**Claimed:** "All Night Shift games are `match_mode: 2`" is false, 268 of 270
are and 2 are mode 1, therefore **do not filter on mode 2**.

**True:** every genuine Night Shift game in the cache is `match_mode: 2`. The
two apparent exceptions are not Night Shift games at all. They are wrong match
IDs typed on Liquipedia, pointing at unrelated public matches: `44465516`
(listed as #9 NA challenger) and `83756240` (#39 EU challenger, actually a 4v4
Street Brawl game, `game_mode: 4`). Mode 2 is now a **hard gate at ingest** in
`scripts/build_dataset.py`.

**How it went wrong:** this is the interesting one, because the observation was
correct and only the conclusion was wrong. Two cached matches really did carry
`match_mode: 1`. The unexamined assumption was that everything in the cache was
a Night Shift game, so an exception had to be a property of Night Shift rather
than a defect in the input. The rule that would have caught it is already
written down elsewhere in this project: **play data beats external metadata**.
The wiki said these were bracket games; the match data said otherwise; the
match data was right.

**A caution that survives the correction.** Mode is the gate because it is one
field with no join and no threshold, but it must never be the only check. Both
matches were found by **three converging signals**, and mode was the weakest:

| Signal | The two bad IDs | The corpus |
| --- | --- | --- |
| Hero picks vs the wiki | 2 of 6 | 265 of 273 score 6 of 6 |
| Duration vs the wiki | out by 218s and 630s | 269 of 276 agree within 2s |
| `match_mode` | 1 | 279 of 281 are 2 |

A wrong match ID that happened to point at another custom lobby would pass the
mode gate untouched and be caught only by the hero pick check. Duration is the
weakest of the three: match `85256685` is genuine, confirmed 6 of 6 on hero
picks, and still disagrees with the wiki by 112 seconds.

**The two matches stay in the cache.** The cache is a raw preservation record
of what the API returned, and those two are the evidence that the wiki can be
wrong. Filtering happens where raw data becomes a claim about Night Shift.

**Reproduce:** `python scripts/verify_api_claims.py` and
`python scripts/check_side_mapping.py`

```forbidden
do not filter on mode 2
Do not filter on mode 2
match_mode: 2. is not universal
2 coming back as mode 1 carrying a real badge
```

---

## R3: the data window is not the current balance patch

**Claimed:** since there are no seasons, the meaningful boundary is the balance
patch, and games predating the current patch should be dropped for a cleaner
read. Supporting figure: a patch window holds only about 20 games.

**True:** the window is **every game**, with cross-patch flagged on the page.
Almost every metric divides a player by their own five teammates in the same
match, so a patch moves both sides of the ratio and largely cancels. The
supporting figure was also stale: against the 2026-03-11 boundary the cache
splits **144 after and 137 before**, not 20.

**Role Score is the documented exception** and is bucketed per patch era, each
game scored against its own era.

**How it went wrong:** the "about 20 games" figure was measured when the cache
held 12 matches, all from one month, and was still being quoted after the cache
grew 23 times larger. A number with no script behind it does not get re-checked
when the thing it describes changes.

**Reproduce:** `python scripts/fetch_patches.py` for the boundaries.

```forbidden
Consider dropping them for a cleaner read
the meaningful boundary is the\s+balance patch
All cached Night Shift matches\s+postdate it
```

---

## R4: `last_team_avg_badge` is not 115 or 116 for everyone

**Claimed:** all 45 Night Shift players sampled came back as either 115 or 116,
so badge cannot separate teams at this level.

**True:** the **conclusion holds**, the wording did not. Across all 155
accounts in genuine tournament matches, 128 of the 131 returning a value
(97.7%) are 115 or 116. But three sit lower, one at **104**, and **24 accounts
return `null`**, a case the 45 profile sample never contained at all.

**How it went wrong:** same shape as R1, a small contiguous sample read as a
universal. The conclusion happened to survive, which is luck rather than
method: a claim of "every one of them" was being made from 26% of the accounts.

**Reproduce:** `python scripts/check_badge_spread.py`

```forbidden
either .115. or .116. for every one of them
All 45 players across the sample
```

---

## R5: Liquipedia carries 284 usable match IDs, not 286

**Claimed:** 286 of 404 games across 49 editions carry a Deadlock match ID.

**True:** **284**. The committed parser also reports 3 malformed `matchid`
values it refuses: `27:28` at #4 EU (a game length in the wrong field),
`479818572` at #16 EU, and `8014968` at #37 NA.

**How it went wrong:** the 286 came from an exploratory probe that was never
committed, and it counted 2 of the 3 malformed values, inconsistently. An
uncommitted script is a number nobody can re-derive.

**Reproduce:** `python scripts/parse_liquipedia.py`

```forbidden
286 of 404
286 game IDs
286 \(71%\)
```

---

## P1: validate a matcher against known answers before believing it

A **process note**, not a retracted claim, so it has no forbidden patterns.
It is here because this ledger is where methodological mistakes belong.

**What happened.** A first pass at matching Steam personas against unresolved
Liquipedia handles reported **0 matches out of 96 accounts**. That is a clean,
plausible, decision-shaped result: it says the persona fallback is worthless
and a whole line of work can be dropped. It was wrong. The real figure is 39.
`steam-profiles.json` keys `account_id` as an int, the lookup used a string,
and every profile fetch silently returned nothing.

**What caught it.** Running the same matcher against the accounts whose handle
was already known, where it returned 0% against an expected rate that turned
out to be 68%. The bug was invisible in the real run and obvious in the
control.

**The rule.** A **clean negative is the easiest wrong result to believe**,
because it agrees with the prior that the work is done and it demands nothing
further. Before trusting a matcher, a filter, or a join, run it against cases
whose answer is already known and check the hit rate is what it should be. A
zero that arrives without a control is not a finding, it is an untested claim.

This generalises past matchers. "No results" from a search, "no differences"
from a diff, and "no matches" from a filter all deserve the same treatment,
and all three have a failure mode that looks exactly like success.

---

## R0: `average_badge_team0` / `average_badge_team1` are unusable

Kept for completeness as the original instance, and still the clearest example
of the failure mode. The fields were **source-read** from the API's Rust source
and the Steam protobufs, never observed in a tournament response, and shipped a
leaderboard column of zeros. They are present, typed `int`, and hardcoded to
`0` on every custom lobby. Note that `?? null` does not catch this, because `0`
is not nullish.

This is where the **confirmed live** versus **source-read** distinction in
`CLAUDE.md` comes from. A field existing in a schema is not evidence that it
carries a usable value.

```forbidden
average_badge_team0 gives the enemy team
use average_badge for opposition
```
