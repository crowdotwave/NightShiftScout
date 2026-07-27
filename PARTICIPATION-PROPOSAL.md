# Observed participation, curated identity

Status: **proposal, nothing implemented.** Written 2026-07-27.

The principle being proposed: **curate only what play data cannot tell us,
and derive everything else.** Curation is expensive, goes stale weekly, and
is the only place a claim about a real person can be wrong. Play data is
free, exact, and never disagrees with itself.

Under that principle, exactly two things are curated:

1. **Which person an account belongs to.** Not observable, ever.
2. **Which lineup a set of accounts constitutes.** A judgement about
   identity, not a fact about a server.

Everything else about a night, in particular **who played which game**, is
read from the match data.

## Why the current model is wrong

`rosters` in a night file is a night-level list of accounts per team. That
asserts one squad for a whole night, which the format does not guarantee.
A Bo3 where someone substitutes in for game 2 only is currently
unrepresentable: the roster says six people played the night, and the
per-game truth is lost.

The Braeden case already showed the two layers disagreeing. Liquipedia
listed him as a Melee Creeps starter for #48 NA; he played none of the
three games. We handled it with a prose `roster_note`, which is an
admission that the field could not express the fact.

**Worth being precise about the current evidence, though.** Of the six
nights we hold, three have a full Bo3 cached, and in all three the same six
accounts played every game:

| Night | Games | Result |
| --- | --- | --- |
| ns047-na | 3 | stable, same six per side throughout |
| ns048-eu | 3 | stable, same six per side throughout |
| ns048-na | 3 | stable, same six per side throughout |

So mid-series substitution is a **real mechanism that our data has not yet
caught**. The Braeden substitution was between matches, not mid-series:
snakes played all three games. This proposal is therefore about removing a
latent modelling error before it produces a wrong number, not about fixing
an observed one. That is a weaker case than "this is broken today", and it
should be weighed as such.

## What this means for the existing #48 NA curation

Field by field, what the night file asserts today and where it should come
from:

| Field | Verdict |
| --- | --- |
| `night_id`, `series` | curated, a grouping decision |
| `edition`, `region` | external, from Liquipedia |
| `region_confirmed`, `region_note` | curated, a judgement about the external label |
| `date` | **derivable** from `start_time` plus a region offset, already documented in `date_note` |
| `source`, `attribution` | curated, provenance and licence obligation |
| `rosters` | **redundant**, see below |
| `roster_note` | **disappears**, it exists only to patch what `rosters` cannot say |
| `matches[].match_id` | curated, which games belong to this night |
| `matches[].stage` | external, not derivable from play data |
| `matches[].series_label` | external, not derivable |
| `matches[].game_in_series` | **derivable** by ordering matches within a series |
| `sides[].match_team_index` | observed |
| `sides[].team_id` | **derivable** from lineup membership |
| `sides[]._observed_account_ids` | already just a copy of the match data |

**`rosters` becomes redundant, and I tested that rather than asserting it.**
Defining each lineup as a set of accounts and deriving each side by overlap
reproduces the hand curation exactly on all three #48 NA matches, at 6 of 6
with the next best lineup at 0 of 6.

So `teams.json` gains a membership set and the night file loses `rosters`,
`roster_note`, and every `_observed_account_ids` block. The night file
shrinks to: which games, what the bracket called them, and the provenance.

## What breaks

### 1. The side mapping validator goes circular. This is the real cost.

Today the curated roster is an **independent statement**, so comparing it
against the observed accounts detects a swapped side mapping. That check is
not theoretical: it was proven by deliberately swapping the sides, which
gave 0 of 12 overlap as mapped versus 12 of 12 swapped, and exited non-zero
under `--strict`.

If the roster is derived from the observed accounts, the comparison becomes
a tautology. Straight and swapped both agree with the data by construction,
the check can never fail, and `side-mapping-swapped` becomes dead code.

**This must be replaced, not dropped.** The independent anchor already
exists and is stronger: Liquipedia's `team1side` (amber means index 0) plus
the per-game hero picks, which were verified 13 of 13 against our own match
metadata. That check is genuinely external, works on all 286 games carrying
a match ID, and needs no rosters. The proposal is only safe if that
validator lands **before** `rosters` is removed.

### 2. Lineup matching is fragile exactly where identity is contested

Deriving a side by overlap is decisive when lineups are distinct, and
marginal when they are not. Poppers' Pupils (#48) and FPS Lounge (#46)
share five of six accounts:

```
#48 side scored against both lineups:  poppers-pupils 6/6, fps-lounge 5/6
#46 side scored against both lineups:  fps-lounge     6/6, poppers-pupils 5/6
```

A margin of one. **A single stand-in would flip the attribution**, silently,
to a team the players were not representing. The current 6 versus 0 margin
is an artifact of only one of the two lineups being defined.

This is the same problem as the rename question and cannot be solved
independently of it. See [TEAM-IDENTITY-PROPOSAL.md](TEAM-IDENTITY-PROPOSAL.md).
Mitigations, none free:

- Require a minimum margin and refuse to attribute below it, which turns a
  silent error into an explicit `unmapped-side` warning. Cheapest and most
  in keeping with the rest of the project.
- Scope lineups by edition range, so #46 and #48 cannot both be candidates
  for the same night.
- Keep a hand override for contested matches, which reintroduces curation
  precisely where it is most needed.

I prefer the first plus the second.

### 3. Losing "rostered but did not play"

Braeden is currently recorded as absent in prose. Under the proposal the
curated layer has no place for him at all, because he never touched a
server. That is arguably correct: the claim "Braeden was on the roster"
belongs to the external Liquipedia layer, not to our curated identity
layer. But it means the answer to "was a team missing a starter" would have
to come from a source we do not currently store.

### 4. Smaller consequences

- **`game_in_series` by ordering** assumes cached games are complete for a
  series. With a game missing, ordering yields 1, 2 for what was really
  games 1 and 3. Deriving it needs the external game count as a check.
- **Stand-ins still need a decision.** Your earlier rule was that a
  stand-in's games count individually but not toward team aggregates.
  Derived participation makes stand-ins *detectable* (a player in some
  games of a series but not others, or not in any lineup) which is progress,
  but the rule still has to be written.

## Migration, if you want it

1. Add membership sets to `teams.json`. Curated, since it is an identity
   claim.
2. Build the Liquipedia side validator, and confirm it reproduces the
   existing mapping on all 12 cached matches.
3. Only then derive `team_id`, participation and `game_in_series`, and
   delete `rosters`, `roster_note` and `_observed_account_ids`.
4. Add the minimum-margin rule with an explicit warning below threshold.

Step 2 before step 3 is the load-bearing ordering. Doing them in the other
order leaves a window with no side-mapping check at all.

## What I would not do

Do not derive `stage` or `series_label`. They are bracket facts and are not
present in match data.

Do not remove `region_confirmed`. It records a judgement about an external
label, which is exactly the kind of thing this proposal says should stay
curated.
