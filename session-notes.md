# Session notes, 2026-07-27

Decisions and findings from the session that added Liquipedia as a source
and curated the first night. Kept because several of these were expensive
to establish and are easy to get wrong a second time.

For the full source documentation see [LIQUIPEDIA-NOTES.md](LIQUIPEDIA-NOTES.md).
For the unresolved team identity question see
[TEAM-IDENTITY-PROPOSAL.md](TEAM-IDENTITY-PROPOSAL.md).

## What changed in the project's direction

LockBlaze already publishes Deadlock esports results: tournaments, brackets,
rosters, transfers, prize money, back to Night Shift #9. Verified directly:
it carries **no per-game stats** and **no Steam account IDs**, so it cannot
join roster data to match data at all.

The consequence: **identity data is not our moat.** Team names, rosters,
bracket stages and night groupings are all available externally and should
be treated as cheap. Our moat is the join nobody else has, match ID to
account ID to in-game performance, attributed per player and separated from
the team's result.

## Rules adopted

1. **Match data wins on any conflict with an outside source.** Same rule
   already applied to `average_badge_team0`.
2. **Read substitution records before flagging a roster mismatch.** A
   rostered player missing from a game is usually explained by the source
   itself. Braeden at #48 NA was flagged as a wiki error before this rule
   existed; he was simply substituted out.
3. **Reject any `steam64ID` that appears on more than one player page.** It
   corroborates neither mapping. `Zeno` and `Rocaine` carry the same ID
   despite being different people.
4. **Attribution is a build requirement.** Rendering a name owned by an
   outside source creates the obligation, so the credit block is built from
   what the page actually rendered and the build fails if a page owes a
   credit it does not carry.
5. **Uncertain identity stays uncertain.** `guess` costs nothing. An
   identity error is the one mistake that lands on a real person.

## Verified facts worth not re-deriving

- **Side mapping.** In Liquipedia bracket markup, `team1side=amber` means
  `match_team_index` 0 and `sapphire` means 1. This is the opposite of the
  intuitive guess. Verified 13 of 13 by joining hero picks against our own
  match metadata, and separately by roster overlap.
- **Coverage.** All 49 editions exist for both regions, no gaps. 286 of 404
  games carry a Deadlock match ID, back to #1. Rosters start at #16.
- **Freshness.** Rosters and schedule are published before an edition is
  played; match IDs are filled in within days after. The recurring cost is
  refetching two pages per week.
- **Batching.** `prop=revisions` accepts 50 titles per request. All 98
  edition pages come back in 2 requests, so a full backfill is single digit
  requests rather than hundreds.
- **Region labels.** The #46 and #47 Europe finals run past local midnight
  because the series starts 21:30 UTC and game 3 lands about two hours
  later. A 01:23 CEST start is a late European broadcast, not a North
  American evening.
- **Cross-region play** happens but is rare: two handles in the whole
  series, one same-edition case. Recorded, no constraint built around it.

## Open questions

- **Team identity across renames.** Proposed, not implemented. Three
  decisions outstanding, see the proposal.
- **Per-match participation.** Night-level rosters are too coarse, since a
  player can substitute in for one game of a Bo3. Under discussion.
- **Opposition strength.** Still unmitigated. Bracket stage is now
  available for every game we can join, which is the input that was missing.
- **Sampling bias.** 20 of the 32 game IDs for #46 to #48 are still not
  cached, including every qualifier for #46 and #47, so the dataset skews
  toward finals.
