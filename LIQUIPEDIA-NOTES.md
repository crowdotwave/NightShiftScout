# Liquipedia as a source for Night Shift

Findings from probing the Liquipedia Deadlock wiki API on July 27 2026.
Everything below was checked against live responses. Where something was
read but not verified against our own match data, it says so.

Same confidence convention as `CLAUDE.md`:

- **Confirmed** means checked against a live API response, and where the
  claim touches our data, cross-checked against the 12 matches in
  `data/matches/`.
- **Read, not verified** means observed in a response but never tested
  against a second source.

Probe cost: 23 HTTP requests, all HTTP 200, no `action=parse` used, no
rate limiting encountered. Responses are cached so a re-run makes zero
requests.

## Headline

Liquipedia publishes the **Deadlock match ID** for individual games inside
its bracket markup, and publishes **`steam64ID` on player pages**. Those
two facts together mean the identity curation we were treating as
expensive hand work is mostly a machine join.

The important caveat, and it is a real one: `steam64ID` is right most of
the time but **not always the account that actually played**. It has to be
validated against match data, never trusted blind. Details below.

## Access rules we have to honour

From `https://liquipedia.net/api-terms-of-use`, read live:

- **Rate limit 1 request per 2 seconds** on `api.php`.
- **`action=parse` is limited to 1 request per 30 seconds**, being more
  expensive. We do not need it: `action=query&prop=revisions` returns raw
  wikitext under the normal 2 second limit.
- **A descriptive User-Agent is required**, identifying the project and
  including contact information. Their example is
  `LiveScoresBot/1.0 (http://www.example.com/; email@example.com)`.
  Generic agents such as `Python-requests` or `node-fetch` are stated as
  likely to be blocked.
- **The client must accept `Content-Encoding: gzip`.**
- **Re-use the HTTP connection** across requests.
- Only make authenticated calls when actually necessary, so their caching
  stays effective.
- **Automated access to generated HTML pages is explicitly not permitted.**
  Only the API. This rules out the HTML scraping that returned HTTP 429
  before, and it is a terms issue, not just a rate issue.

Licensing: content is **CC-BY-SA 3.0** and attribution to Liquipedia is
required. `meta=siteinfo&siprop=rightsinfo` returns `CC-BY-SA` pointing at
`https://liquipedia.net/deadlock/Liquipedia:Copyrights`. Anything we
publish that carries their team names, rosters or bracket structure needs
a visible credit and a link back to the source page, and share-alike
applies to that derived text.

The User-Agent used for these probes identifies the project and gives the
GitHub account as the contact route. It does not include your email
address, since sending that to a third party was not mine to decide. If
you want to match their example exactly, add it.

### LiquipediaDB, the other API

There is a separate structured API (`LiquipediaDB`) which is **access on
approved request only**, with its own key and a limit of **60 requests per
hour**. We have not requested access and did not touch it. The wiki also
has **no Cargo and no Semantic MediaWiki**: `siprop=extensions` lists 52
extensions with neither, and `action=cargoquery` / `action=ask` are absent
from the 83 actions `paraminfo` reports. So on the free path, **wikitext
is the structured data**. That is fine, because the templates are regular.

## Endpoints and exact query shape

Base: `https://liquipedia.net/deadlock/api.php`

Page content, which is the only one we actually need:

```
?action=query&prop=revisions&titles=<A|B|C>&rvslots=main&rvprop=content
 &redirects=1&format=json&formatversion=2
```

**Up to 50 titles per request.** This matters a lot: all 98 edition pages
came back in 2 requests, and 129 player pages in 3. A full backfill is
single digit requests, not hundreds.

Set `redirects=1` and read `query.normalized` / `query.redirects` to map
the title you asked for back from the title you got. Liquipedia capitalises
first letters, so `oses` resolves to `Oses` and `recon` to `Recon`.

Enumerating the series:

```
?action=query&list=allpages&apprefix=Deadlock Night Shift&aplimit=500
```

Page titles are `Deadlock Night Shift/<edition>/<EU|NA>`. There are 102
pages: 98 edition pages, plus `Deadlock Night Shift`,
`Deadlock Night Shift/Open`, and two `Trolli Open` pages.

## Coverage, measured across all 49 editions

**Confirmed.** All 98 edition pages exist. Editions #1 to #49, both regions,
**no gaps**. That is deeper than LockBlaze, which you found starts at #9.

| Editions | Games listed | With a Deadlock match ID | Teams with rosters |
| --- | --- | --- | --- |
| #1 to #7 | 50 | 41 (82%) | 0 |
| #8 to #14 | 53 | 43 (81%) | 0 |
| #15 to #21 | 55 | 36 (65%) | 33 |
| #22 to #28 | 55 | 20 (36%) | 42 |
| #29 to #35 | 58 | 41 (71%) | 43 |
| #36 to #42 | 55 | 45 (82%) | 40 |
| #43 to #49 | 78 | 60 (77%) | 49 |
| **Total** | **404** | **286 (71%)** | **213** |

Two separate coverage stories, and they matter differently:

- **Match IDs go back to #1** and sit around 71% overall. The dip at
  #22 to #28 is real, not a parsing artifact: those pages list games with
  scores but leave `matchid=` empty. Coverage is patchy but never
  systematically absent.
- **Rosters start at #16.** Editions #1 to #15 (and #16/NA) name no
  players at all, so 31 pages have zero rosters. From #17 on, rosters are
  present on essentially every page: 213 rostered teams naming 1284 player
  slots.

So: **for #17 onward this is a one time backfill.** For #1 to #16 there
are match IDs but no roster to attribute them to, and Liquipedia will not
solve identity there.

**The weekly chore is small but real.** Edition #49 is already published
with dates (EU July 29 20:30 UTC, NA July 30 00:30 UTC) and full rosters,
but **zero match IDs**, because it has not been played yet. Match IDs are
filled in after the fact. #48, played July 22 and 23, has all 11 of its
game IDs. So the pattern is: rosters and schedule ahead of time, match IDs
within days after. Re-fetching the two newest edition pages weekly is
2 requests.

## `steam64ID`, and exactly how far to trust it

**Confirmed.** Player pages carry `|steam64ID=` in their infobox. Convert
with the same offset the app already uses:

```
account_id = steam64ID - 76561197960265728
```

Across the 129 handles named in all 49 editions:

| | Count |
| --- | --- |
| Handle has a wiki page | 91 |
| No page at all | 38 |
| Page exists, `steam64ID` blank | 15 |
| **Page exists with a usable ID** | **76** |

Narrowed to the 56 handles in editions #46 to #48, which is where we hold
match data: 45 have pages, 40 have IDs.

### The reliability test, and its failure cases

I tested those 40 IDs against the 12 matches we actually hold:

| Outcome | Count |
| --- | --- |
| ID matches an account we saw play | 30 |
| ID never appears, though the player was rostered in a game we hold | 3 |
| Not testable, no cached match for that player | 7 |

I then looked up all three on Steam, which changed the picture. Only one
is an actual problem:

| Handle | Wiki ID resolves to | Verdict |
| --- | --- | --- |
| `Braeden` | persona `braeden`, vanity `braedenow` | **Not a failure.** Liquipedia records `{{Substitution|out=Braeden|in=snakes}}` for the #48 NA final, so his absence from the three games we hold is exactly what the wiki itself predicts. |
| `Lomein` | persona `Lomein` | **An alt, not an error.** The wiki lists a genuine account named `Lomein` that did not play. He competes on `1871021649`, persona `fpsl lomein`. Both accounts are plainly his. |
| `AVG` | persona `mrbob40` | **Genuinely unexplained.** No resemblance to the handle, and the account appears in none of our matches. |

So the corrected reading of 33 testable IDs: **31 are consistent with the
match data once substitutions are accounted for, and 2 point at an account
that did not play.** Of those 2, one is a player using a second account
and one is unexplained.

That is better than the raw number suggested, but it does not change the
rule, because the failure mode is unchanged: the wiki ID is a **strong
lead, not proof**, and when it disagrees it disagrees silently. Note in
particular that a substitution is the *common* reason a rostered player is
absent, so any check has to read the substitution records before calling a
mismatch. So the rule for step 7 should be:

- Wiki ID **that appears on exactly one player page**, and the account
  appears on the right side of the right match, gives `confirmed`. An ID
  found on two pages is discarded, see the collision rule below.
- Wiki ID that contradicts the match data must **not** overwrite the match
  data. Fall back to persona evidence and mark `probable` at best.
- A persona match with no wiki ID is `probable`, never `confirmed`.

Measured hit rate on this sample is **31 of 33 testable** once substitutions
are read, so roughly **19 in 20 usable, 1 in 20 pointing at an account that
did not play**. That is the failure mode `CLAUDE.md` already warns about
with `average_badge_team0`, so it gets the same treatment: verify, do not
assume.

### A steam64ID on two player pages corroborates neither

**Confirmed, and it cost a wrong mapping before it was caught.** The pages
for `Zeno` and `Rocaine` carry the *same* `steam64ID`, `76561199690298161`:

```
Zeno     |name=Alex Isakayev   |country=United States |birth_date=2002-09-14
Rocaine  |name=Matthew Snyder  |country=Canada        |birth_date=2002-01-20
```

Different people by the wiki's own account, and they appear on opposing
rosters in seven editions. One page simply has the wrong number.

**Rule: before a wiki ID is used as evidence for anything, check whether
that ID appears on more than one player page. If it does, it corroborates
neither mapping and must be discarded for both.** This sits alongside the
substitution rule: read the substitution records before flagging a
mismatch, and check for ID collisions before trusting a match. Both checks
are cheap, both are non-obvious, and both have already caught a real error.

The check itself is a one-liner over the handle to account map: invert it
and look for any account with more than one distinct page behind it. When
running it, note that requesting both `Foo` and `foo` returns the *same*
page twice, since MediaWiki capitalises the first letter. Those are an
artifact of how you keyed the request, not a collision. Compare page
content, not the key you asked under. Of 13 apparent duplicate groups in
the #1 to #49 sweep, 12 were this artifact and exactly one, `Zeno` and
`Rocaine`, was real.

Resolving a collision needs match data, not more wiki reading. Because the
two men played on opposing teams, one cached game settled it: in match
`74191976` (#33 NA challenger, Floormen versus FPS Lounge) the disputed
account sits on the side that also holds `rocker`, `Dimov`, `DMB` and
`League`, all Floormen and none FPS Lounge. So the account is **Zeno**, and
the `Rocaine` page is the one at fault. Rocaine's real account is
`279125228`, the only remaining unidentified player on the FPS Lounge side.

### Players do change region, but rarely

**Observed, and deliberately not turned into a constraint.** Across all 67
edition-pages that carry rosters, covering roughly 1,284 player slots and
110 distinct handles:

- **Two handles ever appear in both regions**, `oses` and `dimov`.
- **One same-edition case exists in the whole series.** `oses` played the
  #48 Europe qualifier for `Silence` on July 20 and the #48 North America
  final for `Melee Creeps` on July 22. Verified independently of handle
  strings: account `1840902834` is present in our cached match data on both
  sides, so this is one person, not a name collision.
- `dimov` switched regions twice (EU through #32, NA #33 to #41, EU again
  from #42) and **never appears in both regions in one edition**.
- Every cross-region appearance is as a **starter**, and none of them shows
  up in a substitution record, so these are not emergency stand-ins.
- Both cases originate from the same European roster, `Leviathan`, and both
  later appear on the same North American roster, `Melee Creeps`.

The `oses` case reads as a transition week rather than a standing
arrangement: Europe only through #46, both at #48, North America only at
#49.

**Treat this as incidental.** One same-edition case in the entire series is
not a pattern, and no schema constraint should be built around it. It is
recorded here only so that a future reader who trips over it knows it is
real and already investigated.

**Caveat.** Only 6 of the 67 rostered pages have match data behind them, so
outside #46 to #48 this rests on Liquipedia rosters alone. A player who
quietly guested in another region without being added to a roster would be
invisible to this method. The true rate is a floor, not a measurement.

## Bracket data, and what it gives us

**Confirmed.** Inside `{{Bracket|...}}`, each `{{Match}}` holds `{{Map}}`
blocks, one per game, carrying:

- `matchid=` the Deadlock match ID, joining straight to our cache
- `winner=` 1 or 2, referring to opponent1 / opponent2
- `team1side=` / `team2side=`, values `sapphire` and `amber`
- `t1h1..t1h6` and `t2h1..t2h6`, the heroes each side picked
- `t1b1..t1b2`, bans
- `length=` game duration as mm:ss
- `date=` on the parent match, in UTC via `{{Abbr/UTC}}`
- `{{Substitution|out=X|in=Y}}` with a free text reason, when a stand-in
  played

### Side mapping: use hero picks. `team1side` is 95% and must not be trusted

**This section previously said "solved, 12 of 12, zero exceptions". That was
wrong, and the way it was wrong is worth keeping.** Re-tested on 261 games
across all 49 editions with `scripts/check_side_mapping.py`:

```
team1side = amber     ->  opponent1 is match_team_index 0
team1side = sapphire  ->  opponent1 is match_team_index 1
```

| Editions | Games tested | Rule correct |
| --- | --- | --- |
| #1 to #39 | 200 | 187 (93.5%) |
| **#40 to #49** | **60** | **60 (100%)** |
| **All** | **261** | **248 (95.02%)** |

The original 12 match sample was editions #46 to #48. It sat entirely inside
the range where the rule happens to hold perfectly, so it read as a law when
it is a tendency. A clean 12 of 12 across three consecutive editions was not
evidence about editions #1 to #39, and treating it as such is the mistake to
avoid repeating.

The 13 failures are not noise or weak evidence. Twelve of them are complete
6 to 0 inversions, meaning `team1side` is simply recorded backwards on those
pages. Whatever the cause, editor convention drift is the obvious candidate,
it cannot be detected from the wiki alone.

**So do not use `team1side` as the side of record.** Use the hero pick join,
which is not a second opinion but the actual answer:

- **It decides 261 of 261 comparable games**, with a **median margin of 6 of
  6** and 259 of 261 decided by a margin of 4 or more. There were no ties.
- It needs **no rosters and no player identity**, so it works on editions #1
  to #16 where the wiki names no players, and it does not inherit the
  `steam64ID` reliability problem.
- It is a multiset comparison, so a mirror pick of the same hero on both
  sides still counts correctly.

`team1side` remains useful as a **cross check**: a disagreement is a good
signal that a page needs a human look. It should never silently win.

Coverage of the join, out of 284 wiki games carrying a match ID: 270 are in
our cache, 8 list no hero picks at all, and 1 has no `team1side`. That leaves
261 comparable, and all 261 resolved.

Two hero names need folding beyond lowercasing: `Mo & Krill` against `mo and
krill`, and `The Doorman` against `doorman`. Both are handled generically.
One game (#21 EU) writes `mo` alone, which is an explicit alias.

### Bracket stages

Stage names come from three places, in this order of reliability:

1. `|R<n>header=` or `|R<n>M<m>header=`, present on newer pages (#43 on,
   inconsistently).
2. The bracket template name, which is structural and covers nearly
   everything: `Bracket/2L2D` means round 1 Qualifier, 2 Challenger,
   3 Finals. `Bracket/2L1D` means 1 Challenger, 2 Finals. `Bracket/2` is a
   single match.
3. HTML comments such as `<!-- Qualifier -->` immediately above the match,
   which is the only marker on some pages, for example #47/NA where a lone
   `Bracket/2` match sits under `<!-- Finals -->`.

Using template name plus header, stages resolve on 96 of 98 pages. The two
`Bracket/2` pages need the comment fallback.

This directly addresses the **unmitigated format bias** noted in
`CLAUDE.md`: bracket stage is now available for every game we can join,
which is exactly the "computed from data the app already trusts" fix that
section asks for, and it does not touch a badge field.

## The region question, now settled

**Confirmed.** The two matches carrying `region_confirmed: false` are both
genuinely **Europe**:

| Match | Liquipedia page | Stage | Start (UTC) | Local EU (+2) |
| --- | --- | --- | --- | --- |
| 92902607 | Night Shift/46/EU | Finals, game 3 | Jul 8 23:23 | Jul 9 01:23 |
| 94021619 | Night Shift/47/EU | Finals, game 3 | Jul 15 23:30 | Jul 16 01:30 |

The explanation is mundane. Both EU finals are scheduled at 21:30 UTC, and
game 3 of a Bo3 lands about two hours later, so it crosses local midnight.
A 01:23 CEST start looks like a North American evening but is simply a
late running European broadcast. Our night grouping already put both in
the correct EU files, so **only the `region_confirmed` flags need
flipping**, and the note removing.

## What this changes

1. **Match ID discovery is solved.** `CLAUDE.md` lists "no automatic match
   ID discovery, IDs pasted by hand" as a known gap. Liquipedia yields 286
   game IDs across 49 editions in a handful of API calls. We currently
   hold 12.
2. **Steam to handle mapping is mostly solved**, with the 1 in 10 caveat
   above. `CLAUDE.md` says "no such data source exists". That is now out
   of date.
3. **Rosters and team names are free** for #17 onward, confirming your
   read that identity is not our moat.
4. **Bracket stage is free**, which unlocks the opponent quality work.
5. Our moat is unchanged and now sharper: **per player in game performance
   separated from team result.** Liquipedia has scores, placements and
   prize money. It has no damage, souls, kills or assists, exactly like
   LockBlaze.

## Risks and open items

- **`steam64ID` is wrong roughly 1 time in 10** in a plausible looking way.
  Never write it without match validation.
- **15 handles have a page but a blank ID**, and **38 have no page**,
  including `Birdee` and `recon` who both appear in our data. Those still
  need persona based curation.
- Team names change: `FPS Lounge` in #46 fields the same five players who
  appear as `Poppers' Pupils` in #47 and #48. `teams.json` needs to handle
  a roster continuing under a new name, or team level history will
  fragment. Not yet designed.
- **20 of the 32 game IDs for #46 to #48 are not in our cache**, including
  every qualifier for #46 and #47. Our current dataset is skewed toward
  finals, which is a sampling bias on top of the format bias already
  documented.
- Attribution is a **build requirement**, not a nicety, once any generated
  page shows a team name or roster taken from Liquipedia.
- Parsing is regex against wikitext. Templates are regular today, but this
  is scraping in the sense that it will break when editors change format.
  It needs to fail loudly rather than silently drop matches.

## Reproducing

Probe scripts are in the session scratchpad, not committed, since they
were exploratory. The reusable parts worth keeping if we proceed are the
rate limited fetch helper and the wikitext parser for
`{{Bracket}}`, `{{Match}}`, `{{Map}}` and `{{Persons}}`. Note that rosters
appear under both `{{TeamOpponent|...}}` and `{{Opponent|...}}`, and both
forms are in current use.
