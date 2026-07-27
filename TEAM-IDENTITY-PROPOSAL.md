# Team identity across renames, a proposal

Status: **proposal, nothing implemented.** Written 2026-07-27 after the
Liquipedia probe. Evidence is from all 49 editions, both regions.

## The problem, stated precisely

`teams.json` currently keys a team by a `team_id` slug and stores one
`name`. That model cannot express a team whose name changes, so history
fragments at every rename. `FPS Lounge` becoming `Poppers' Pupils` with
five of six players unchanged is the case that prompted this.

Having looked at the whole series, the naive framing is wrong in two ways.
It is not one problem, it is three, and they pull in opposite directions.

## Evidence

### 1. Most apparent renames are just capitalisation

30 distinct team name strings appear across the 49 editions. Casefolded,
that collapses to **22**. Seven names are written inconsistently by
Liquipedia editors:

| Casefolded | Written as |
| --- | --- |
| bird with clock | `Bird With Clock`, `Bird with Clock`, `bird with clock` |
| floormen | `Floormen`, `floormen` |
| fps lounge | `FPS Lounge`, `fps lounge` |
| leviathan | `Leviathan`, `leviathan` |
| lowkey w | `Lowkey W`, `lowkey w` |
| no earnings | `No Earnings`, `no earnings` |
| work in progress | `Work In Progress`, `Work in Progress` |

These are not renames and must never be recorded as succession events.
Ten of the 15 rename candidates my detector found were pure case variants.
**Casefold on ingest** removes two thirds of the apparent problem for free.

### 2. Genuine renames are real but rare

After casefolding, five genuine rebrands remain in 49 editions, roughly
one every ten editions:

| Editions | From | To | Shared players |
| --- | --- | --- | --- |
| #18 to #20 | Sneaky Golem | floormen | 4 of 6 |
| #24 to #27 | Bunny With Clock | bird with clock | 5 of 6 |
| #38 to #42 | Floormen | FPS Lounge | 4 of 6 |
| #39 to #43 | Lowkey W | Buff Enjoyers | 6 of 6 |
| #43 to #47 | FPS Lounge | Poppers' Pupils | 5 of 6 |

Rare enough to curate by hand. Common enough that ignoring it will
fragment the three most active teams in the series.

### 3. The case that breaks the obvious fix

The obvious fix is "merge teams when rosters overlap heavily". The
`FPS Lounge` history shows why that is wrong:

```
#20 to #40   floormen      League, AVG, Zeno, DMB, rocker core
#31 to #40   FPS Lounge    Lefaa, Lomein, Hydration, snakes, rocaine, Erebus
#42 to #46   FPS Lounge    AVG, DMB, Lefaa, Lomein, Poppers, Zeno
#47 to #49   Poppers' Pupils  AVG, League, Lefaa, Lomein, Poppers, Zeno
```

**`floormen` and `FPS Lounge` are both present on the same night**, at
editions #31, #33, #34, #35, #36, #38, #39 and #40. They are two different
teams, playing each other's tournaments simultaneously. Then at #42 the
two rosters merge under the `FPS Lounge` name and `floormen` stops
appearing. Then at #47 that merged lineup rebrands to `Poppers' Pupils`.

So this single thread contains an **absorption** and a **rebrand**, and any
model that auto-merges on roster overlap would have collapsed two
concurrently competing teams into one entity. A correct model must be able
to say "these two names were the same team" and also "these two names were
different teams on the same night", and roster overlap alone cannot tell
them apart.

### 4. A stable name does not mean a stable team

The reverse failure is bigger than renames. Comparing each team's first and
last appearance:

| Team | Span | Players shared between first and last roster |
| --- | --- | --- |
| Melee Creeps | #17 to #49 | 2 |
| Leviathan | #16 to #49 | 2 |
| Lowkey W | #18 to #42 | 2 |
| floormen | #20 to #34 | 2 |
| FPS Lounge | #31 to #46 | 2 |

`Melee Creeps` has kept its name for 33 appearances across nine months
while replacing four of six players. Treating that as one team for stats
purposes is a bigger distortion than splitting `FPS Lounge` from
`Poppers' Pupils` ever was.

**This is the finding that should drive the design.** Merging names is the
small problem. The large problem is that team level aggregates over long
spans are not measuring a stable thing, whatever we call it.

## What I propose

### A. Separate the brand from the lineup, and only trust the lineup

Two concepts, stored separately, because the evidence shows they diverge:

- **Org.** The brand a team plays under. Owns names over time. Cheap,
  cosmetic, curated from Liquipedia. Good for display.
- **Lineup.** A specific roster playing continuously. This is the thing
  that actually has comparable performance. A lineup ends when the roster
  turns over past a threshold, or when it merges with another.

`FPS Lounge` is an org that fielded one lineup #31 to #40, absorbed the
`floormen` lineup at #42, and lost that lineup to the `Poppers' Pupils`
org at #47.

### B. Sketch of the shape

Deliberately a sketch, not a schema. `teams.json` becomes two files.

`orgs.json`:

```json
{
  "fps-lounge": {
    "names": [
      { "name": "FPS Lounge", "from_edition": 31, "to_edition": 46 }
    ],
    "attribution": { "provider": "liquipedia", "url": "..." }
  },
  "poppers-pupils": {
    "names": [
      { "name": "Poppers' Pupils", "from_edition": 47, "to_edition": null }
    ],
    "succeeds": { "org_id": "fps-lounge", "kind": "rebrand", "at_edition": 47,
                  "evidence": "5 of 6 players unchanged from #46",
                  "confirmed_by": "human" }
  }
}
```

`lineups.json`:

```json
{
  "lineup-fpsl-2": {
    "org_id": "fps-lounge",
    "from_edition": 42, "to_edition": null,
    "core": ["Lefaa", "Lomein", "AVG", "Zeno", "Poppers"],
    "formed_by": { "kind": "absorb",
                   "from": ["lineup-floormen-3", "lineup-fpsl-1"] }
  }
}
```

Key properties:

1. **`succeeds` and `formed_by` are hand curated and typed.** `rebrand`,
   `absorb`, `split`, `disband`. A type is required, because "rebrand" and
   "absorb" need different handling and the difference is not derivable
   from the data.
2. **Nothing is ever auto-merged.** Roster overlap generates *candidates*
   for review, exactly as the detector I wrote does. A human confirms.
   Same discipline as `identified: guess/probable/confirmed`.
3. **`org_id` is a display label. `lineup_id` is the stats key.** This is
   the load-bearing decision. It means "Melee Creeps career stats" is not
   a thing the app will offer, because it is not a real quantity.
4. **Casefold on ingest**, and record the name as written for display.

### C. What I would *not* do yet

**Do not aggregate stats by team at all until this lands.** Right now the
site has one page type, the player page, and it uses team names only as
labels next to teammates. That is safe, and it stays correct under any
model we pick later. Adding a team page before deciding this would bake in
the wrong aggregation and then need unpicking.

This is also why I think the proposal is not urgent to implement. Nothing
currently depends on it. What is urgent is not shipping a team page first.

## Cost

- Casefolding: trivial, do it whenever we touch ingest.
- Curating the five rebrands and one absorption: maybe an hour, one time,
  and the detector already produced the candidate list.
- Ongoing: one check per edition, when a name appears that has not been
  seen before. About one real event per ten editions.

## What I need you to decide

1. **Org and lineup as two entities, or one entity with a name history?**
   Two is more faithful to the evidence and is what I recommend. One is
   less machinery, but it cannot express the #42 absorption, and it will
   force a choice between fragmenting `Poppers' Pupils` and wrongly merging
   `floormen` with `FPS Lounge`.
2. **What ends a lineup?** I suggest a hand confirmed event only, never a
   threshold. An automatic "3 of 6 changed" rule would have cut
   `Melee Creeps` into pieces at moments no human would call a new team.
   But that means slow drift is never captured, and `Melee Creeps` stays
   one lineup for 33 editions despite sharing 2 players end to end. If that
   is unacceptable, the alternative is periodic hand declared eras, which
   is more curation work.
3. **Is "team career stats" a feature you want at all?** If the answer is
   no, most of this can stay unbuilt and orgs remain a display label
   forever, which is the cheapest correct outcome.

## Related

Detection script lives in the session scratchpad and is not committed. It
reads the Liquipedia sweep and prints rename candidates with shared player
counts. Worth keeping if we proceed. See [LIQUIPEDIA-NOTES.md](LIQUIPEDIA-NOTES.md)
for how the roster data is obtained and its licence obligations.
