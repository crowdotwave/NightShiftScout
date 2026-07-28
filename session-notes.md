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

- **Side mapping.** The side of record is the **per-game hero pick join**,
  not `team1side`. Joining the wiki's `t1h1..t1h6` against the hero IDs in
  our own match metadata decides which `match_team_index` the wiki's
  opponent1 is. It resolves **273 of the 281 games we hold**, median margin
  6 of 6, no ties; the 8 it cannot decide list no hero picks at all. It
  needs no rosters and no player identity.
  `team1side=amber` meaning index 0 is a **tendency, not a rule**: right on
  **248 of 261** games carrying both, 95.02%, and 12 of the 13 failures are
  complete 6 to 0 inversions. Keep it as a cross check that flags a page for
  human review. It must never win.
  **This bullet previously read "verified 13 of 13" [R1].** That sample was three
  consecutive recent editions, it sat entirely inside the range where the
  rule happens to hold, and it did not survive contact with all 49. Numbers
  above are reproducible with `python scripts/check_side_mapping.py`, which
  makes no network requests. See [LIQUIPEDIA-NOTES.md](LIQUIPEDIA-NOTES.md).
- **Coverage.** All 49 editions exist for both regions, no gaps. **284** of
  404 games carry a usable Deadlock match ID, back to #1. Rosters start at
  #16. An earlier figure of 286 came from an uncommitted probe that counted
  two of the three malformed `matchid` values (`27:28` at #4 EU,
  `479818572` at #16 EU, `8014968` at #37 NA). The committed parser rejects
  all three and reports them. Prefer 284.
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
- **Sampling bias, largely closed.** The cache now holds **281 of the 284**
  wiki game IDs. Only 3 remain, all genuinely cold: `38766744`, `92586699`,
  `92592573`. The last two are #46 NA qualifier games, so a small skew toward
  finals survives in that one edition, but the series-wide skew is gone.
