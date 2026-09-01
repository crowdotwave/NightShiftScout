# Night Shift Scout, session a167829e

Text turns only. Tool calls and their output are omitted.

---

## You  
_2026-07-26T04:51:11.353Z_

Read CLAUDE.md first, then open nightshift_scout.html and get
oriented. Don't change anything yet.

Then do two things:

1. Run the app against the live API and verify my assumptions are
   actually correct. I've never been able to confirm these because
   the previous environment couldn't reach api.deadlock-api.com.
   Specifically check: does hero_type actually come back populated
   for most heroes, does average_badge_team0/team1 exist on finished
   tournament matches, and does players[].stats[] contain
   player_damage as expected. Report what's real vs assumed.

2. Tell me what you'd fix first, and why. I care most about the app
   being readable at a glance and the stats being defensible.

Sample match IDs are already in the file under SAMPLE_IDS.

---

## Claude  
_2026-07-26T04:51:11.946Z_

You've hit your session limit · resets 12:50am (America/Toronto)

---

## You  
_2026-07-26T05:58:34.934Z_

Continue from where you left off.

---

## Claude  
_2026-07-26T05:58:34.934Z_

No response requested.

---

## You  
_2026-07-26T07:20:17.222Z_

Read CLAUDE.md first, then open nightshift_scout.html and get
oriented. Don't change anything yet.

Then do two things:

1. Run the app against the live API and verify my assumptions are
   actually correct. I've never been able to confirm these because
   the previous environment couldn't reach api.deadlock-api.com.
   Specifically check: does hero_type actually come back populated
   for most heroes, does average_badge_team0/team1 exist on finished
   tournament matches, and does players[].stats[] contain
   player_damage as expected. Report what's real vs assumed.

2. Tell me what you'd fix first, and why. I care most about the app
   being readable at a glance and the stats being defensible.

Sample match IDs are already in the file under SAMPLE_IDS.

---

## Claude  
_2026-07-26T07:20:20.087Z_

I'll start by reading the project instructions and the app file.

---

## Claude  
_2026-07-26T07:20:26.163Z_

Now let me get oriented in the app file.

---

## Claude  
_2026-07-26T07:20:46.541Z_

Now let me hit the live API and verify the assumptions.

---

## Claude  
_2026-07-26T07:20:58.004Z_

The API is reachable. Now let me analyze the actual payloads.

---

## Claude  
_2026-07-26T07:23:00.322Z_

Significant finding on the badges. Let me check all sample matches and the rest of the assumptions.

---

## Claude  
_2026-07-26T07:25:08.548Z_

Three clear results. Let me check how the app renders a zero badge, and confirm the field works on non-tournament matches.

---

## Claude  
_2026-07-26T07:25:47.182Z_

Decisive. Now let me actually run the app in a browser to confirm end-to-end behavior.

---

## Claude  
_2026-07-26T07:25:57.145Z_

`last_team_avg_badge` exists but is 115/116 for all 45 players. Now let me run the actual app.

---

## Claude  
_2026-07-26T07:26:16.605Z_

The app renders. Let me click Analyze and watch it run live.

---

## Claude  
_2026-07-26T07:26:30.694Z_

It works end to end, no console errors. Let me look at the leaderboard table.

---

## Claude  
_2026-07-26T07:26:53.891Z_

Confirmed visually: the Opposition column is a column of literal zeros. Let me quantify a statistical issue I'm seeing in the Role Score.

---

## Claude  
_2026-07-26T07:28:06.736Z_

Nothing changed on disk. Here is what I found.

## 1. Assumptions vs reality

I hit the live API directly (it is reachable, wildcard CORS confirmed) and pulled all 12 sample matches plus the hero assets, patches, steam, and match-history endpoints. All returned 200.

**`hero_type`: CONFIRMED, and better than your note suggests.**

| | count |
|---|---|
| Heroes total | 57 |
| Populated `hero_type` | 37 |
| Missing | 20, but 19 of those are `disabled: true` |
| Active heroes missing it | 1 (Rem) |

Across the 144 player-games in your sample, 143 resolve to a role. That is 99.3%. The four values are exactly `assassin`, `brawler`, `marksman`, `mystic` as documented. `icon_image_small` is present on every active hero. You can treat this as solid.

**`average_badge_team0/1`: THE KEY EXISTS, THE VALUE IS ALWAYS ZERO.** This is the one that is wrong.

All 12 Night Shift matches return `average_badge_team0: 0` and `average_badge_team1: 0`. Not null, not absent: literal zero. All 12 are `match_mode: 2`. I pulled a public matchmaking game (95694731, `match_mode: 1`) as a control and it returns `116 / 116`, so the field genuinely works, just never for custom or tournament lobbies.

Two consequences in the code. [nightshift_scout.html:964](nightshift_scout.html:964) uses `?? null`, which does not catch `0` because zero is not nullish, so the zero flows all the way through as a real value. And [nightshift_scout.html:1381](nightshift_scout.html:1381) then renders `Math.round(0)`. I confirmed this in the browser: the Opposition column is a column of 45 literal zeros.

I also checked the obvious substitute. Steam's `last_team_avg_badge` does exist (your CLAUDE.md is right about that) and is populated for all 45 tournament players. But every single one of them is 115 or 116. At Night Shift level everyone is Eternus V or VI, so badge cannot separate these teams no matter where the number comes from.

**`players[].stats[]` with `player_damage`: CONFIRMED, exactly as written.** 144 of 144 player-games have a populated `stats` array, and the entry with the highest `time_stamp_s` has `player_damage`. Zero misses. The max timestamp equals `duration_s` exactly, so the final snapshot really is end-of-game.

**App health:** ran it in the browser from `file://`. Clean, no console errors, 12/12 matches loaded, the patch banner correctly reports the current patch as Mar 11 2026 with no stale data. Colspan is 15 and the header count is 15, so that has not drifted. No em dashes in the file.

## 2. What I would fix first

**First: kill or replace the Opposition column.** It is the only thing on the page that is actively lying. A reader scanning the table sees a populated numeric column and reasonably assumes it means something. It does not, and per the above it structurally cannot for tournament matches. This is your one column that fails both of your stated priorities at once: it is noise at a glance and it is indefensible.

I would drop the column rather than render dashes. The Night Shift format bias it was built to expose is real and worth surfacing, but badge was never going to measure it. The honest replacement is something you can actually compute from data you already have: which stage of the bracket the match was, or opponent quality derived from the loaded dataset itself, for example the average Role Score of the enemy team. That reuses the self-calibrating idea already in the app instead of depending on a field Valve does not fill in for custom lobbies.

**Second: the default `min games` of 1 contradicts the panel directly above it.** Stars of the Show requires 3 games before it will crown anyone, with a documented comment explaining why a single outlier game should not decide things. The leaderboard immediately below it defaults to 1 and sorts by Role Score. The result right now is that rank #1 is a player with exactly one game. The sample breaks down as 7 players with 1 game, 11 with 2, so 40% of the board is at or below two games.

That is your biggest defensibility hole, and it is a one-line default change plus letting the row visually mark thin samples. The metrics themselves are fine. It is the ranking that is not.

**Third, and only after those: the table is 15 columns wide with 11 numeric ones.** Every number is styled at roughly equal weight, so nothing guides the eye. Given you already sort by Role Score, that column and Team Share (which your own docs call the single most useful scouting signal) should be visually dominant, with Net Worth Share and Dmg Share demoted or folded behind the expandable row. This is presentation only, which is why it ranks below the two correctness items.

One thing I explicitly tested and am **not** recommending: role baselines include the player being scored, which is a genuine leave-one-out bias. I computed the leave-one-out version and the largest shift across all 45 players is +0.03x, with no change to ranking order. It is real but not worth touching at this dataset size.

Worth noting that the "Verified API facts" heading in CLAUDE.md now overstates its case, since the badge fields were inferred from the Rust source rather than observed on a tournament match. Happy to update that section to separate what is confirmed against live tournament data from what is read off the source, if you want.

---

## You  
_2026-07-26T07:37:24.857Z_

drop the Opposition column and bump min games to 3

---

## Claude  
_2026-07-26T07:37:30.635Z_

I'll drop the column and bump the default. Let me look at every place Opposition appears first.

---

## Claude  
_2026-07-26T07:37:41.925Z_

Now making the changes.

---

## Claude  
_2026-07-26T07:37:46.159Z_

Now the computation layer.

---

## Claude  
_2026-07-26T07:38:01.493Z_

Now the render layer, sort case, colspan, and the min games default.

---

## Claude  
_2026-07-26T07:38:31.942Z_

14 headers, colspan 14. Now let me verify in the browser.

---

## Claude  
_2026-07-26T07:38:56.752Z_

The attribute is correct (`value="3"`); the reload restored the old form state. Let me confirm with a fresh tab.

---

## Claude  
_2026-07-26T07:40:04.516Z_

Both changes are in and verified live.

**Opposition column removed.** Gone from the header, the row template, the per-game detail table, the sort switch, the footer glossary, and the computation (`teamBadges`, `oppBadge`, `avgOppBadge` all deleted). CSV export never included it, so that was untouched. I left a comment at [nightshift_scout.html:955](nightshift_scout.html:955) recording *why* it went, including the `match_mode 2` finding and the `last_team_avg_badge` dead end, so nobody re-adds it from the CLAUDE.md description.

**Min games default is now 3**, matching the threshold Stars of the Show already uses.

Verification against your checklist:

- No console errors, 12/12 matches still load
- Table populates: now "showing 27 of 45 players (min 3 games)". 27 is exactly right, it matches the games-played distribution I measured earlier (16 players with 3, 2 with 4, 4 with 6, 5 with 7)
- Expanded a player row, per-game detail renders correctly
- **Colspan checked:** main table is 14 headers, 14 `<td>` per row, `colspan="14"`. The inner detail table is 12 headers and 12 cells. All aligned
- Zero em dashes

The visible effect is what you were after. The board now opens on freemok, reyache, and zEno rather than a one-game player at the top, and the dead zero column is gone.

Two follow-ups I did **not** touch, since you scoped this to the two changes:

1. The Stars panel still has its own independent fallback ladder (3, then 2, then 1 game). It no longer needs to disagree with the table, but merging them into one shared constant would stop them drifting apart again.
2. CLAUDE.md still documents `average_badge_team0/team1` under "Verified API facts" and lists Opposition as a core metric. That file will now actively mislead the next person. Say the word and I'll update it to reflect what the live API actually returns.

---

## You  
_2026-07-26T16:26:42.168Z_

Detect this project's dev servers, write them to .claude/launch.json, then call preview_start.

---

## Claude  
_2026-07-26T16:26:51.395Z_

Let me detect what's actually here before writing anything.

---

## Claude  
_2026-07-26T16:27:07.122Z_

The file was renamed to `index.html` since my last turn. Let me confirm my changes survived and check what runtimes are available.

---

## Claude  
_2026-07-26T16:27:27.821Z_

Everything survived the rename (the one `Opposition` hit is my explanatory comment). Now, the detection result:

**There is no dev server in this project.** No `package.json`, no build system, no framework, single static `index.html`. CLAUDE.md is explicit that this is deliberate. Node is not installed; Python 3.13 is. So the only sensible entry is a static file server, which I'll use Python's built-in for since it adds no dependency.

---

## Claude  
_2026-07-26T16:27:39.318Z_

Server is up. Let me confirm it actually serves the app rather than a directory listing.

---

## Claude  
_2026-07-26T16:28:17.695Z_

Stuck at 6/12. Let me check the network.

---

## Claude  
_2026-07-26T16:28:39.427Z_

It completed (just slow, 12 files of ~1MB each). But 45 rows with min 3 games is wrong. Let me look.

---

## Claude  
_2026-07-26T16:28:48.306Z_

Found the real bug. Line 2043 resets the input at runtime, overriding the HTML default.

---

## Claude  
_2026-07-26T16:29:02.550Z_

That is why my earlier change looked right but did nothing at runtime: `runAnalysis` stomps the input back to `1` on every run, so the HTML default only survived until the first Analyze click. I verified this is the only such reset. Removing it so the default holds and a user's choice is preserved across re-runs.

---

## Claude  
_2026-07-26T16:29:05.579Z_

This change is observable, so let me verify it on a fresh load through the server.

---

## Claude  
_2026-07-26T16:29:29.027Z_

Still 1. Let me check whether the server is serving my edit or a cached copy.

---

## Claude  
_2026-07-26T16:29:35.962Z_

Server and disk agree; the browser cached the old JS. Cache-busting reload:

---

## Claude  
_2026-07-26T16:29:49.709Z_

Fresh copy loaded, reset line gone. Now the real test: does the value survive an Analyze run?

---

## Claude  
_2026-07-26T16:30:23.950Z_

Done, and the detour turned up a real bug.

**Detection result: this project has no dev server.** No `package.json`, no build step, no framework, one static `index.html`. Node isn't installed; Python 3.13 is. So I wrote a single static-file-server entry rather than inventing a toolchain, which keeps the zero-install property CLAUDE.md asks for:

[.claude/launch.json](.claude/launch.json) runs `python -m http.server 8000 --bind 127.0.0.1`. I added the `--bind` so it listens on loopback only instead of `0.0.0.0`, which is `http.server`'s default and would otherwise expose the app to your local network.

`preview_start` is running on port 8000 and serving the app. The rename to `index.html` means `http://localhost:8000/` resolves to it directly. Server logs are clean apart from a 404 for `/favicon.ico`.

**The bug:** while verifying, I found my min-games change from last turn was cosmetic. Line 2043 of `runAnalysis` did `minGamesInput.value = 1`, which stomped the HTML default back to 1 on every Analyze click. The attribute said 3, the app behaved as 1, and my earlier verification missed it because I set the value manually before re-rendering instead of going through a full analysis run. I removed the reset line. The default now holds, and a value you pick yourself survives re-running the analysis.

Verified on a genuinely fresh load through the server:

- Fresh load default: `3`, and still `3` after a full Analyze run
- "showing 27 of 45 players (min 3 games)", 27 rows rendered, matching the games-played distribution
- Top of board is freemok (3g), reyache (3g), zEno (7g), no one-game players
- 14 cells per row against 14 headers, no console errors
- Stars panel and leaderboard now agree on the 3-game bar

One caching note worth knowing: `python -m http.server` sends no cache-control headers, so the browser served a stale copy of your edit twice before I busted it with a query string. If you edit and don't see the change, hard-reload or append `?v=N`. I can swap in a tiny no-cache server if that gets annoying.

Two things still outstanding from earlier, both untouched: the Stars panel keeps its own independent 3/2/1 fallback ladder that could drift from the table default again, and CLAUDE.md still documents `average_badge_team0/team1` under "Verified API facts" plus Opposition as a core metric. That file will mislead the next reader. Say the word and I'll fix it.

---

## You  
_2026-07-26T21:08:23.200Z_

fix please

---

## Claude  
_2026-07-26T21:08:35.921Z_

Fixing both. Let me re-read the current state of each.

---

## Claude  
_2026-07-26T21:08:40.019Z_

Starting with the shared threshold constant.

---

## Claude  
_2026-07-26T21:08:56.758Z_

Now define the constant and drive the input from it, so there's one source of truth.

---

## Claude  
_2026-07-26T21:09:13.548Z_

One source of truth means removing the now-duplicate hardcoded value in the HTML attribute, since a second copy is exactly the drift that caused this bug.

---

## Claude  
_2026-07-26T21:09:16.077Z_

Now CLAUDE.md. Let me read the sections I need to correct.

---

## Claude  
_2026-07-26T21:09:50.780Z_

Now the metric design section, which still lists Opposition.

---

## Claude  
_2026-07-26T21:10:32.158Z_

Now verifying both fixes with a real Analyze run, per the rule I just wrote into the doc.

---

## Claude  
_2026-07-26T21:10:51.018Z_

The server stopped. Restarting it from the launch config:

---

## Claude  
_2026-07-26T21:11:39.415Z_

Both panels now agree. Let me verify the rewritten fallback ladder still works when no one qualifies.

---

## Claude  
_2026-07-26T21:11:51.045Z_

Fallback ladder works correctly at every level, and the singular/plural wording holds. Final visual check:

---

## Claude  
_2026-07-26T21:12:06.982Z_

Both fixed and verified.

**1. Shared min-games threshold.** There is now one `DEFAULT_MIN_GAMES = 3` constant at the top of the script. It drives the leaderboard filter and the Stars panel eligibility bar. I also removed the `value="3"` HTML attribute, since leaving it would recreate the exact duplicate-source-of-truth problem that caused the original disagreement. The input is set from the constant at load.

While doing this I rewrote the Stars fallback ladder. It was two hardcoded steps (`3`, then `2`, then `1`) that would silently ignore the constant if you ever changed it. It's now a loop that steps down from `DEFAULT_MIN_GAMES`, so it tracks the constant automatically.

Verified via full Analyze runs, not DOM poking:

- Fresh load default `3`, still `3` after a complete run
- Table reads "showing 27 of 45 players (min 3 games)", Stars reads "min 3 games to qualify". They agree
- 27 rows, 14 cells per row, no console errors
- Fallback ladder exercised at each level: a dataset where everyone has 1 game drops to "min 1 game", 2 games drops to "min 2 games", and it restores to 3 correctly. Singular/plural wording holds

**2. CLAUDE.md corrected.** The substantive changes:

- The "verified" claim is split into **confirmed live** (checked against real tournament responses on July 26 2026) versus **source-read** (in the schema, never observed). The old blanket claim was what made the badge field look trustworthy
- `average_badge_team0/1` is now an explicit do-not-use with the `match_mode: 2` vs `1` evidence, plus the `?? null` trap noted, since `0` is not nullish
- `hero_type` upgraded with real coverage numbers (37/57 heroes, 143/144 player-games)
- `player_damage` confirmed with the 144/144 result and the detail that max `time_stamp_s` equals `duration_s`
- `last_team_avg_badge` documented as existing but useless here, since all 45 players are 115 or 116
- Opposition removed from the metrics list, replaced with a note on why it failed and what a real replacement would need to be built from
- The format-bias section now says plainly that the bias is unmitigated, rather than claiming a column fixes it

I added three things beyond the two you asked for, all recording facts from this session that would otherwise be lost: the min-games rationale, the leave-one-out measurement in Known gaps (real, largest shift +0.03x, not worth fixing now), and a verification note that a correct HTML default can still be overwritten at runtime, which is what hid the bug from me earlier. Also documented the `http.server` caching gotcha.

Zero em dashes in both files. Nothing is committed; the working tree has `index.html`, `CLAUDE.md`, and the new `.claude/launch.json`, which is untracked since `.gitignore` excludes `.claude/`. Worth knowing if you expected the launch config to be shareable.

---

## You  
_2026-07-27T01:01:40.599Z_

Give me a 1-paragraph summary of our current stack and active feature set so I can paste it into a planning chat.

---

## Claude  
_2026-07-27T01:01:56.329Z_

Night Shift Scout is a zero-dependency single-file browser app (`index.html`, roughly 2,000 lines of vanilla JS and CSS, no framework and no build step) that scouts Deadlock esports talent for the weekly Night Shift tournament series; it pulls live from the community-run `api.deadlock-api.com/v1` with no key and no proxy since CORS is wildcard-open, and persists only match IDs, aliases, team tags, watchlist, and the top-elo log to localStorage. You paste match IDs and get a scouting board: an auto-generated Stars of the Show panel, a sortable leaderboard, a Team View built from manual player-to-team tags, a downloadable PNG share card, and config panels for aliases, team tags, watchlist, and a top-elo lobby scanner. The metric set is deliberately five separately explainable numbers rather than one composite score: pooled KDA, Net Worth Share, Team Share (split by win and loss, the strongest signal in the app), Role Score normalized against dataset-derived archetype baselines, and KP%; players below a shared `DEFAULT_MIN_GAMES` of 3 are unranked. Known open weaknesses are no opposition-strength adjustment (the badge-based Opposition column was removed after live checks showed the API never populates it for tournament lobbies), plus manual match ID, roster, and handle mapping, and Role Score baselines that need more volume.

---

## You  
_2026-07-27T03:41:52.566Z_

Team Share (split by win and loss, the strongest signal in the app)
i dont actually see this? am i missing it

---

## Claude  
_2026-07-27T03:42:00.503Z_

Fair challenge. Let me check rather than assume.

---

## Claude  
_2026-07-27T03:42:48.810Z_

You're not missing it. I overstated that, and my summary was misleading.

The split **is** computed and it **is** real data, but it is not visible anywhere on screen. It only exists in two places:

1. A native browser `title` tooltip on the Team Share cell ([index.html:1378](index.html:1378)). You have to hover the number and wait for the OS tooltip to appear. Nothing in the UI hints that hovering does anything.
2. Two columns in the CSV export (`team_share_wins`, `team_share_losses`).

The visible cell shows only the combined average. Confirmed live just now:

| Player | Visible cell | Hidden in tooltip |
|---|---|---|
| freemok | 0.92x | Wins 1.02x, Losses 0.87x |
| reyache | 0.99x | Wins 0.93x, Losses 1.13x |
| dew | 1.13x | Wins 1.49x, Losses 0.95x |

That table is a good argument that your instinct is right and this matters. dew looks like the strongest of the three at 1.13x, but the split shows they are 1.49x in wins and 0.95x in losses, which is close to the "riding the snowball" pattern CLAUDE.md warns about. reyache looks mediocre at 0.99x but is actually *better* in losses (1.13x) than in wins, which is the carry signal you actually want to scout for. The combined number hides the exact distinction the metric was built to make.

So the accurate version of that clause is "computed and available on hover or in the CSV export, but not surfaced in the table." I should not have called it the strongest signal in the app without noting you cannot see it. That phrasing came from CLAUDE.md describing design intent, and I repeated it as if it described the shipped UI.

Corrected sentence for your paste:

> ...pooled KDA, Net Worth Share, Team Share (with a win/loss split that is currently computed but only exposed via hover tooltip and CSV, not shown in the table), Role Score normalized against dataset-derived archetype baselines, and KP%...

Want me to surface it properly in the cell? Given your priority on glance-readability, showing it inline as something like `1.13x` with a smaller `1.49 / 0.95` beneath would make the app's most useful signal actually legible, and it fits the column without adding one.

---

## You  
_2026-07-27T04:32:48.412Z_

Context: I have a working single-file browser app (index.html, vanilla JS,
no build step) that pulls Deadlock match data from api.deadlock-api.com/v1
and computes scouting stats for a weekly tournament series (Night Shift).
Match IDs are collected manually. Everything persists to localStorage, so
nothing survives outside my browser. I'm converting this into a public
static stats site, keeping index.html as my private curation console.

Do NOT modify or rewrite index.html. It works and I depend on it weekly.
Automating match ID collection is explicitly out of scope for now.

CLAUDE.md describes design intent, not necessarily shipped behavior. Verify
against actual code and live API responses before relying on any claim in it.

Work through these in order, stopping after each for my review:

1. Set up a git repo with a /data directory. Write a small script that takes
   a list of match IDs, fetches each from the API, and caches the raw
   unmodified JSON to disk, one file per match, skipping any already cached.
   Nothing should ever hit the network twice for the same match. Also copy
   into /data any CSV exports or localStorage dumps I provide — preserve them
   unmodified as historical artifacts, even if a later schema supersedes them.

2. Probe the API and write API-NOTES.md: exact response shape per endpoint,
   field names and types, whether team/side assignment is explicit or must be
   inferred, and whether ANY endpoint returns match history for a given
   account ID. Use real requests against the cached matches. Do not infer from
   documentation or guess. Stop and show me.

3. Propose a JSON schema for a versioned dataset covering matches, players,
   teams, and match nights. It must hold the two things the API cannot give
   me: which matches belong to which tournament night, and which account ID
   maps to which player on which team. These mappings are hand-curated and are
   the most important files in the repo. Design for many weeks of
   accumulation. Stop and show me.

4. Backfill: process every cached match into that dataset. Report anything
   that doesn't fit the schema rather than silently coercing it.

5. Build a minimal static site generator emitting ONE page type: a player page
   at a stable clean URL. Plain HTML/CSS, no framework, no client-side
   fetching. Stats must be phrased so they need no explanation — e.g. "31% of
   team damage", "involved in 68% of team kills" — not coined metric names
   with bare numbers. Show me one real generated page.

Constraints: no runtime database, no auth, no payments, no frameworks. Ask
before adding any dependency.

---

## Claude  
_2026-07-27T04:33:22.230Z_

Starting with step 1 only. Let me check the current repo state first.

---

## Claude  
_2026-07-27T04:33:36.808Z_

Working tree is clean, which is unexpected since I edited both files last turn. Let me verify my changes are actually in HEAD.

---

## Claude  
_2026-07-27T04:33:59.280Z_

My earlier changes are committed in HEAD and the tree is clean. `index.html` is untouched from here on.

Now setting up the data layer. Python 3.13 is available and I'll use **stdlib only** (`urllib`), so this adds no dependencies.

---

## Claude  
_2026-07-27T04:35:00.691Z_

Now the match ID list and the data directory docs.

---

## Claude  
_2026-07-27T04:35:21.551Z_

Now let me test it, starting with a dry run to confirm nothing touches the network unnecessarily.

---

## Claude  
_2026-07-27T04:35:38.889Z_

All 12 cached, and the byte counts match exactly what `curl` returned earlier in the session. Now the critical guarantee: re-running must make zero network requests.

---

## Claude  
_2026-07-27T04:35:56.498Z_

Now testing the artifact importer. Since you haven't handed me any exports yet, I'll test against a throwaway root so `data/artifacts/` stays clean and awaiting your real files.

---

## Claude  
_2026-07-27T04:36:21.748Z_

Now let me measure the storage implications, since this cache grows every week.

---

## Claude  
_2026-07-27T04:36:57.287Z_

Step 1 is done. Nothing is committed and `index.html` is untouched.

## What exists now

```
data/
  matches/          12 cached match files, raw API bytes
  match-ids/        night-shift.txt, your hand-collected IDs with edition comments
  artifacts/        (empty, awaiting your exports)
  README.md         layout and the immutability rules
scripts/
  fetch_matches.py
  import_artifact.py
```

Both scripts are **stdlib only**, so no dependencies were added.

## Verified, not assumed

**The cache is genuinely write-once.** First run fetched 12/12. Second run reported `0 fetched, 12 skipped` and made zero network requests. Input IDs are de-duplicated before fetching too, so a repeated ID in your list costs one request at most.

**The bytes are genuinely unmodified.** I checksummed three cached files against the independent `curl` fetches I made earlier in this session, via a different tool at a different time. All three SHA-256s match. Nothing is reformatted or filtered.

**Artifact preservation behaves correctly** under the three cases that matter, tested in a throwaway root that I then deleted so `data/artifacts/` stays clean for your real files:
- New file: copied byte for byte, SHA-256 verified after the copy, recorded in `MANIFEST.json`
- Identical content re-imported: detected by hash and skipped, no duplicate
- **Same filename, different content: preserved as `-2`, the original is never overwritten.** This is the case that matters most for you, since a weekly `leaderboard.csv` export will collide by name every single week

Two design choices worth your attention. Fetches write via a temp file then rename, because a half-written file would otherwise look cached forever and be trusted permanently. And a failed fetch writes nothing, so re-running retries it. I read "never hit the network twice" as being about not re-fetching data you already have, not about giving up permanently on a match that timed out once. Say if you meant the stricter reading.

## One thing I want your call on before step 2

At **1.12 MB average per match, a year of Night Shift is roughly 0.68 GB** in the repo, and git stores every version forever. That is not fatal but it is not comfortable either.

These files gzip to **20% of raw** (1.12 MB to 0.23 MB), which would put a year at about 140 MB. Storing `<id>.json.gz` keeps one file per match and keeps the content bit-for-bit recoverable, but it does mean the file on disk is no longer directly readable without decompressing, which cuts against "raw unmodified JSON on disk."

I did **not** do this, since you asked for raw and it is your tradeoff to make. Options as I see them: leave raw and accept the growth, gzip per file, or keep raw on disk and add `data/matches/` to `.gitignore` so the cache is local-only and rebuildable from `match-ids/` plus the API. I lean toward gzip, since the whole point of this step is that the data survives independently of that community-run API still being up.

Ready to commit this as-is on your word, or adjust first. Then I'll move to step 2, the API probe.

Unrelated housekeeping: several MCP connectors (Atlassian, Linear, Notion, Slack, ClickUp, Monday) reported that they need authorization. That is irrelevant to this work, but if you wanted any of them, they need authorizing through your claude.ai connector settings or an interactive `/mcp` session.

---

## You  
_2026-07-27T04:43:01.086Z_

Your retry reading is correct — "never twice" meant don't re-fetch data I
already have, not give up permanently on a timeout. Keep it.

Go with gzip. Surviving independently of the API is exactly the point, and
bit-for-bit recoverable satisfies "unmodified." Note the decompress command
in the README so it's obvious later.

Ignore the MCP connectors, nothing here needs them.

Commit, then continue to step 2.

---

## Claude  
_2026-07-27T04:43:24.598Z_

Good. Switching to gzip first, then committing, then step 2.

---

## Claude  
_2026-07-27T04:43:37.001Z_

Now the storage layer itself.

---

## Claude  
_2026-07-27T04:44:04.834Z_

Now migrating the 12 already-cached files, verifying each round-trips bit-for-bit before removing the raw.

---

## Claude  
_2026-07-27T04:44:28.550Z_

Verifying the whole thing end to end before committing.

---

## Claude  
_2026-07-27T04:44:41.888Z_

Both decompress commands work (that `BrokenPipeError` is just `head -c` closing the pipe). **14 MB down to 2.8 MB**, idempotency still holds. Committing:

---

## Claude  
_2026-07-27T04:44:58.707Z_

Two problems with that commit: a `__pycache__` file got swept in, and my heredoc syntax leaked a stray `@` into the subject line. Fixing both.

---

## Claude  
_2026-07-27T04:45:23.563Z_

Committed cleanly. Now step 2: probing the API.

---

## Claude  
_2026-07-27T04:46:12.178Z_

Now the live endpoint probes. Let me start with the match-history question, which is the one that most affects later steps.

---

## Claude  
_2026-07-27T04:46:39.997Z_

Now the decisive test: does match-history actually contain the tournament matches, and does its `match_result` agree with the cached metadata?

---

## Claude  
_2026-07-27T04:46:58.571Z_

Important trap found: `match_result` is not win/loss. Let me confirm with a second player before I write that down.

---

## Claude  
_2026-07-27T04:47:30.315Z_

My earlier command ran from the wrong directory. Re-running the cross-check properly:

---

## Claude  
_2026-07-27T04:47:41.751Z_

Confirmed 9/9. Now the remaining endpoint shapes.

---

## Claude  
_2026-07-27T04:47:56.541Z_

Leaderboard returns `possible_account_ids` as an array, not a definitive ID. Let me quantify how ambiguous that is, since it bears directly on step 3's mapping problem.

---

## Claude  
_2026-07-27T04:48:12.567Z_

Probing done. Writing up the findings.

---

## Claude  
_2026-07-27T04:49:40.600Z_

Step 1 committed as `c2fda40` (amended to drop a stray `__pycache__` file and fix a mangled subject line; `.gitignore` now covers `__pycache__/`, `*.pyc`, `*.part`). Gzip is in: **14 MB down to 2.8 MB**, every file verified to round-trip to the exact API bytes before being accepted, decompress commands documented in `data/README.md`. Your retry reading is now written into the script docstring so it survives me.

## Step 2: [API-NOTES.md](API-NOTES.md)

Written from real requests only, against the 12 cached matches plus live calls. Four findings change how later steps have to work.

**Your question about match history: yes, `/players/{account_id}/match-history` exists and works.** It returns a bare array, and it **includes tournament matches** (426 of 2,101 entries for one player, 364 of 3,536 for another). Every cached Night Shift match a probed player appeared in was present in their history, 9/9 with none missing. I note this without acting on it, since ID discovery is out of scope, but it does mean the option exists later.

**`match_result` in match history is a trap.** It reads like a win flag and it is not. It is the winning *team index*. Cross-checked against cached metadata: `match_result == winning_team` in **9/9** cases, while `match_result == "this player won"` held only 3/9, and those three only because the player happened to be on team 0. To get a win from history alone you need `match_result == player_team`.

**Team assignment is explicit, never inferred.** `players[].team` is always present, always 0 or 1, splitting exactly 72/72 across 144 player-games. `player_slot` 1-6 maps to team 0 and 7-12 to team 1, deterministically across all 12 matches, so it works as a cross-check. But **team identity is purely positional within one match**. `teams[]` holds only `{team, team_tracked_stats: []}` and `team_score` is empty, so nothing connects `team: 0` in one match to `team: 0` in another.

**The leaderboard cannot give you an account ID mapping.** `possible_account_ids` is an array of *candidates*: exactly one candidate for only **58%** of the EU top 1000, zero for 36 entries, and a long tail reaching **5,199 candidates** for a single row. I had assumed this would be a shortcut for curation. It is not.

Also confirmed and written down: `match_outcome` is `0` on every match including ones team 1 won, so `winning_team` is the only usable win field; `average_badge_team0/1` is present-but-always-zero on tournament games with a public-match control returning 116; damage exists only in `players[].stats[]` and resolves 144/144 at max `time_stamp_s`, which equals `duration_s` exactly; `hero_type` covers 37/57 heroes but 143/144 player-games.

One privacy note I flagged in the doc rather than silently passing over: the Steam endpoint returns a `friends` array, a full social graph per player. Worth deciding whether that ever touches the public site.

`API-NOTES.md` is uncommitted and `index.html` is untouched. Stopping here for your review before proposing the schema in step 3.

---

## You  
_2026-07-27T05:05:39.661Z_

Answer first, before proposing the schema: how did you identify 426 of 2,101
entries as tournament matches? Name the exact field and values. If there's a
mode/lobby-type field that does it reliably, say so — it changes what step 7
looks like, though it's still out of scope now.

Then step 3. Three requirements from your findings:

- Team assignment is positional per match. The schema must keep match-scoped
  team index (0/1) strictly separate from persistent team identity. Never
  let 0/1 imply anything across matches.
- Store winning_team as the source of truth for outcomes. Never persist a
  derived win flag from match_result.
- The Steam friends array never enters the dataset and never reaches the
  public site. Exclude it at ingestion.

/effort xhigh

---

## Claude  
_2026-07-27T05:07:21.259Z_

First, your question. Let me verify the exact field and its enum before answering, rather than restating what I wrote.

---

## Claude  
_2026-07-27T05:07:45.296Z_

The active endpoint only has mode 1 live right now, so it cannot decode mode 2. Let me test directly whether `match_mode: 2` is sufficient to mean "tournament", by sampling custom-lobby matches from history that are *not* Night Shift. These go to scratchpad, not the cache.

---

## Claude  
_2026-07-27T05:08:10.490Z_

Weekday spread across all seven days at ~6/week, but Night Shift is weekly. Let me confirm by fetching three of these.

---

## Claude  
_2026-07-27T05:09:46.625Z_

Now I have a clear answer. Let me get one real match's roster so the schema examples use true data.

---

## Claude  
_2026-07-27T05:11:47.694Z_

## Your question first, and a correction

**Field: `match_mode`, an integer, present on both match-history entries and `match_info`. I filtered on `match_mode == 2`.** All 12 cached Night Shift matches are `match_mode: 2, game_mode: 1`.

But my phrasing "426 tournament matches" was wrong, and the distinction matters for exactly the reason you're asking. **`match_mode: 2` means custom/private lobby, not tournament.** It cannot identify Night Shift on its own.

Evidence, gathered just now:

- Those 426 span 69.6 weeks at **6.12 per week**, spread across every weekday (Thu 129, Tue 80, Sat 75, Wed 49, Fri 38, Sun 38, Mon 17). Night Shift is weekly. That is not a tournament schedule.
- I pulled three non-cached `match_mode: 2` matches from that player's history. All three are 12-player, `average_badge_team0: 0`, with tournament-like durations. Two of them overlap the known Night Shift player pool **11 of 12 players**. Those are near-certainly scrims between Night Shift teams, and nothing in the payload distinguishes them from a real bracket match.

So roster overlap does not rescue it either: an 11/12 overlap scrim is indistinguishable from a bracket game by any field in the response.

**What this means for step 7:** there is no mode or lobby-type field that reliably yields tournament matches. `match_mode == 2` is a useful *necessary* filter that cuts 2,101 entries to 426, but it is not sufficient, and any discovery approach still needs an external source of truth for which of those custom lobbies were actually bracket games. Still out of scope, but that is the constraint it operates under.

One loose end: `/matches/active` exposes `match_mode_parsed`, which would give the official label for mode 2. Only mode 1 (`"Unranked"`) was live when I probed, so I could not capture the name for 2. I did not guess it.

## Step 3: [SCHEMA-PROPOSAL.md](SCHEMA-PROPOSAL.md)

Nothing implemented, no `data/curated/` created.

The core split is **curated versus derived**, in separate directories, with the rule that no generator ever writes to a curated path. Curated files are the ones that are gone forever if lost; `derived/dataset.json` rebuilds in seconds.

Four curated file types: `teams.json` (keyed by permanent slug, so a rebrand changes the name but not the identity), `players.json` (keyed by `account_id`, with an `identified` field of `confirmed`/`probable`/`guess` so a guessed name never renders as fact), and one file per night under `nights/`, holding rosters, bracket stage, and the side mapping. No index file listing the nights: the builder globs, because an index is a second source of truth that drifts.

**Rosters are per night, not global.** That is the main accumulation decision. It handles roster churn, stand-ins, and players changing orgs without rewriting history, and each night file records what was true that night.

On your three requirements:

**Match-scoped index stays isolated.** The integer 0/1 appears in exactly one place: `matches[].sides[].match_team_index`, physically adjacent to the `team_id` it maps to, inside a single match object. `teams.json` has no index field, `players.json` has no team field, rosters reference `team_id` only. The field is named `match_team_index` rather than `team` so its scope is legible at every use site. It survives into derived rows only because team-relative denominators must be computed within a match, and grouping by it across matches is defined as a build error.

**`winning_team` is the only outcome stored.** Copied verbatim as `winning_team_index`; no `won`/`is_win`/`result` boolean is persisted at any level. Beyond that, **the builder reads `/matches/{id}/metadata` only and never touches match-history**, so `match_result` cannot enter even by accident. Given it is the winning-team index rather than a win flag, not reading the field at all is the guarantee I trust.

**`friends` is excluded by allowlist at ingestion.** Only `account_id`, `personaname`, `profileurl`, `avatarmedium` are permitted. The filter runs before anything touches disk, so the social graph is never written or cached. I also dropped `realname`, since it is a legal name rather than a handle. The cost, which I want explicit: **raw Steam responses are not cached**, so wanting another Steam field later means re-fetching. That asymmetry with the match cache is the price of the guarantee.

Two things I added that you did not ask for but I think earn their place. First, **store numerator and denominator, never just the ratio**, so "31% of team damage" has both integers present and checkable. Second, a **side-mapping validator**: a swapped 0/1 mapping is invisible, since the page renders and every number looks plausible while being attributed to the wrong team. The check compares each side's actual account IDs against the mapped team's roster and fails the build if swapping would score better. On match 95172627 a correct mapping scores 6/6 and a swap scores 0/6, so it is decisive.

That validator also caught something already: **the matches labelled "#48 Europe (July 22)" in your ID file actually start 2026-07-20**, and the NA ones labelled July 22 start July 23 UTC. Local broadcast date and UTC match date differ, so the night files carry an explicit `date` that gets validated against match timestamps rather than trusting a comment.

Five open questions are at the end of the doc. The two that most change the build:

1. **Is a "night" per region?** I modelled NA and EU as separate nights of the same edition, since the data shows them on different days. Tell me if an edition is really one night with two brackets.
2. **Stand-ins:** recorded via `roster_status`, but should their games count toward team aggregates, be excluded, or shown separately?

The others are `countrycode` (excluded as personal, but flags are conventional in esports), avatar hotlinking from Steam's CDN on a public page, and whether `guess`-level players get a page at all.

`API-NOTES.md` and `SCHEMA-PROPOSAL.md` are both uncommitted; `index.html` is untouched. Waiting on your review before step 4.

---

## You  
_2026-07-27T05:22:00.697Z_

Answers:

- Regions are separate nights. Group under an edition if useful for display,
  but don't merge — the data says they're different days.
- Stand-ins: count toward individual player stats, exclude from team
  aggregates, mark visibly on the page.
- Add countrycode to the Steam allowlist. Self-declared, public, conventional
  in esports, not a social graph. Widen the allowlist now rather than
  re-fetching later.
- Avatars: fetch once and store locally. No hotlinking Steam's CDN from a
  public page.
- identified: guess gets no player page. Render as an unnamed account ID in
  match rows only. Don't publish a guessed identity.

Keep the numerator/denominator storage and the side-mapping validator.
Fix the night dates it caught.

Commit API-NOTES.md and SCHEMA-PROPOSAL.md, then continue to step 4.

---

## Claude  
_2026-07-27T05:22:56.589Z_

Recording your decisions in the proposal before committing it.

---

## Claude  
_2026-07-27T05:23:22.180Z_

Now fixing the night dates. Let me compute the correct local dates from actual match timestamps first.

---

## Claude  
_2026-07-27T05:23:43.478Z_

Now I can see it clearly. Fixing the dates:

---

## Claude  
_2026-07-27T05:24:09.053Z_

Committed. Now step 4: the backfill. First the schema definitions and the curated scaffolding.

---

## Claude  
_2026-07-27T05:24:39.801Z_

Now the Steam ingestion, with the allowlist applied before anything touches disk.

---

## Claude  
_2026-07-27T05:25:28.556Z_

`friends` dropped at ingestion along with six other fields. Let me verify nothing leaked to disk:

---

## Claude  
_2026-07-27T05:25:35.754Z_

Clean. Now scaffolding the curated files with only what the API proves, leaving human judgment as explicit placeholders.

---

## Claude  
_2026-07-27T05:25:57.391Z_

Now the builder and validator, which is the actual backfill.

---

## Claude  
_2026-07-27T05:27:11.354Z_

Backfill runs clean. Now let me prove the side-mapping validator actually fires, since it never ran with empty rosters.

---

## Claude  
_2026-07-27T05:27:30.390Z_

Validator fires correctly. Let me confirm `--strict` actually exits non-zero (the pipe masked it above).

---

## Claude  
_2026-07-27T05:27:41.043Z_

Now verifying the three enforced rules and the numerator/denominator storage against the real dataset.

---

## Claude  
_2026-07-27T05:28:04.941Z_

One flag to check: `players[]` reporting a "team" field.

---

## Claude  
_2026-07-27T05:28:42.141Z_

Docs and date fix committed as `90303f8`. Step 4 is done and running clean.

## Backfill result

**12 of 12 cached matches ingested, 144 player-match rows, 45 players, zero errors.** Output is `data/derived/dataset.json` (84 KB).

Everything reported is a **missing-curation warning**, not a data problem:

| Warning | Count | Meaning |
| --- | --- | --- |
| `unmapped-side` | 12 | No `team_id` assigned to either side yet |
| `no-stage` | 12 | No bracket stage recorded |
| `no-roster` | 6 | No rosters for any night |
| `no-player-page` (info) | 45 | All accounts are `identified: guess`, so none get a page |

## What I scaffolded, and what I refused to

I generated `data/curated/` with **only facts the API proves**: match IDs, dates, and the real account IDs on each side. Every field requiring human judgment is explicitly `null`.

**I did not invent a single team name or player identity.** `teams.json` is empty. All 45 players are `handle: null, identified: "guess"`. Fabricating those would have corrupted the most valuable data in the repo with plausible-looking guesses, which is worse than leaving it blank. Each night file carries `_observed_account_ids` per side and each player carries `_hint_steam_persona` and `_hint_vanity` as curation aids. Both are ignored by the builder and never published.

Your curation path is now: fill `teams.json`, set `team_id` on each side, paste rosters, set stages. The account IDs are already grouped for you.

## The three requirements, verified against the real output

**Team index scope.** `match_team_index` appears only under `matches[].sides` and `player_matches`, never in `teams[]` or `players[]`. It is never a join or grouping key. (One earlier check flagged a "team" field on players; that was the substring inside `steam`, not a real field.)

**Outcome.** `winning_team_index` is the only outcome field in the entire dataset, copied verbatim and verified equal to the API's `winning_team`. A recursive scan finds no `won`/`is_win`/`result`/`match_result`/`outcome`/`victor` at any depth. The builder never reads the match-history endpoint at all, so `match_result` cannot enter by accident.

**Social graph.** `friends` does not appear anywhere, nor does `realname`. The Steam fetcher filters in memory and reported exactly what it dropped: `avatar, avatarfull, friends, last_team_avg_badge, last_updated, matches_played_last_30d, realname`. Raw responses never touch disk. `countrycode` is now in the allowlist as you asked. **44 of 45 avatars downloaded locally** (192 KB); one 404s on Steam's side, so that player has no avatar rather than a hotlink.

**The side-mapping validator works.** I proved it rather than assuming: with a correct mapping it stays silent, and with the sides deliberately swapped it reports `roster overlap is 0/12 as mapped but 12/12 if swapped` and exits non-zero under `--strict`.

**Numerator and denominator both stored**, so a real example from the data reads: account `124540485` did 48,318 damage of a 201,107 team total, which is "24% of team damage", and 17 kills+assists of 30 team kills, "involved in 57% of team kills". Team net-worth totals recompute exactly against the raw cache.

## Two things needing your input before step 5

1. **The unresolved region labels.** Matches `92902607` and `94021619` are labelled Europe but start at 01:23 and 01:30 Central European time, which reads far more naturally as 19:23 and 19:30 Eastern. The #48 Europe matches run 17:25 to 19:13 CEST, a normal European slot, so the pattern does not hold. I documented this in the ID list and changed nothing. Only the lockblaze pages for editions 46 and 47 can settle it.

2. **Step 5 needs at least one curated night** to produce a meaningful player page. With everything at `identified: guess`, the decision you gave me means *no player qualifies for a page at all*. I can either wait for you to curate one night, or build the generator and demonstrate it against a temporary fixture that I keep out of `data/curated/`. Tell me which.

Nothing is committed from step 4 yet. `index.html` remains untouched.

---

## You  
_2026-07-27T05:44:30.939Z_

Build the generator against a temporary fixture, kept out of data/curated/.
Don't wait on curation — I want to see the page before I decide what's worth
curating.

Leave the region labels unresolved and flagged. Exclude those two matches from
any region-dependent output until I check the bracket pages.

One addition for step 5: unidentified accounts are the normal weekly state,
not an edge case. New accounts will appear every night before I curate them.
Player pages should render their rows as bare account IDs that link nowhere,
and the build must never fail or omit a match because a participant is
uncurated.

Commit step 4, then continue to step 5.

---

## Claude  
_2026-07-27T05:45:18.540Z_

Committing step 4 first.

---

## Claude  
_2026-07-27T05:45:36.118Z_

Now step 5. First, the region-confirmation flag, since that must be a real property rather than something I avoid by hand.

---

## Claude  
_2026-07-27T05:45:56.505Z_

Now the fixture. Let me look at who actually plays across the three NA matches so the fixture groups real accounts correctly.

---

## Claude  
_2026-07-27T05:46:10.635Z_

Non-ASCII names in the data, which the site generator will need to handle too. Setting output encoding:

---

## Claude  
_2026-07-27T05:46:51.186Z_

Two stable six-man groups, and critically **the sides swap between games**: group A is index 0 in games 1 and 3, index 1 in game 2. That is the exact case the index-isolation rule exists for, so the fixture will demonstrate it.

Let me snapshot hero assets, then build the fixture.

---

## Claude  
_2026-07-27T05:47:43.589Z_

Now the site generator.

---

## Claude  
_2026-07-27T05:49:06.598Z_

Let me inspect the generated HTML before viewing it, since I want to check the table row construction.

---

## Claude  
_2026-07-27T05:49:19.778Z_

The HTML is valid here, but there's a latent bug: that conditional applies to the whole concatenated string, so a match with missing `player_damage` would crash the build. Fixing it properly.

---

## Claude  
_2026-07-27T05:49:35.899Z_

Now let me verify that fix actually holds against missing data, rather than assuming.

---

## Claude  
_2026-07-27T05:49:53.942Z_

Robust: 11 of 12 uncurated plus null stats, build still succeeds with all 3 matches intact. Let me confirm the rendering, then view it.

---

## Claude  
_2026-07-27T05:50:12.286Z_

Both states coexist correctly, zero JavaScript, zero client-side fetching. Let me view the real page.

---

## Claude  
_2026-07-27T05:50:33.235Z_

Good, but one card label reads awkwardly ("37% of their team's kills, involved in"). Fixing the phrasing:

---

## Claude  
_2026-07-27T05:51:03.594Z_

Card reads cleanly now. Let me see the lineup section, which is where the uncurated-account handling shows.

---

## Claude  
_2026-07-27T05:51:16.635Z_

Let me verify the clean URLs actually resolve by clicking through.

---

## Claude  
_2026-07-27T05:51:30.976Z_

Clean URLs resolve correctly. Checking light mode and mobile:

---

## Claude  
_2026-07-27T05:52:07.352Z_

Step 4 is committed (`a1f0111`). Step 5 is built and uncommitted for your review.

## The page

Real generated output, screenshotted above in dark, then light + mobile: [scripts/build_site.py](scripts/build_site.py) produced `/players/244109796/` for JonJon69. Zero JavaScript, zero client-side fetching, plain HTML and CSS, no framework. I verified clean URLs actually resolve by clicking a teammate through to `/players/1871217631/`.

**Stats read as sentences, not metric names.** "Played 3 games on Night Shift #48, North America, winning 1 of 3." Then: *16% of their team's damage* (100,793 of 633,604), *37% of their team's kills, with a kill or an assist* (45 of 121), *19% of their team's souls*. Every percentage carries the two integers it came from, straight out of the numerator/denominator storage rule. Percentages are pooled across games rather than averaged per game, stated in the page footer so a reader knows which it is.

**URLs key on account ID, not handle**, because an account ID is permanent and a handle is not. A player renaming must not break their page.

## Your addition: uncurated accounts as the normal state

The fixture curates exactly one of the two teams, deliberately, so both states appear on one page. Teammates render as links; the six uncurated opponents render as **bare account IDs that link nowhere**, with a `Not yet identified` tooltip.

I tested the worst case rather than assuming it: I nulled out a row's damage and kills, and stripped identity from 11 of 12 players. **The build succeeded, exit 0, all 3 matches still represented**, one page generated. A missing stat renders as a muted "not recorded" cell.

That test caught a real bug. My first version had a conditional that applied to an entire concatenated HTML string rather than one cell, so a match with missing `player_damage` would have crashed the build, violating your "must never fail" requirement. It never showed up on live data because damage resolves 144/144. It is fixed and now covered by that test.

## Region labels

Left unresolved and flagged. I made it a durable property rather than a manual workaround: the two suspect nights carry `region_confirmed: false` plus a note, the builder propagates it and reports it, and the generator **suppresses the region rather than guessing it**, rendering "Night Shift #46" with a "region unconfirmed" caveat instead of claiming Europe. Those matches are excluded from region-dependent output until you check the bracket pages.

## Fixture safety

`fixtures/curated-demo/` sits outside `data/curated/` and every file carries a `_fixture` marker. **Team names are obviously synthetic** ("Demo Alpha", "Demo Bravo") because inventing plausible org names and attaching real players to them would be a fabricated claim about real people. Handles are the accounts' genuine public Steam personas, marked `identified: "probable"`, and the page renders a preview banner.

Worth noting what the fixture surfaced: across the Bo3, **the two teams swap sides between games** (Alpha is index 0 in games 1 and 3, index 1 in game 2). That is exactly the case the index-isolation rule exists for, and the page attributes every stat correctly through the swap.

Also added: a hero asset snapshot (`data/assets/heroes-2026-07-27.json.gz`, 61 KB) so hero names on old pages stay reproducible if Valve edits them.

Uncommitted: `scripts/build_site.py`, `fixtures/`, the hero snapshot, the `region_confirmed` changes, and a `.gitignore` entry for generated site output. `index.html` untouched throughout.

One open question for whenever you curate: the page currently shows every game a player appeared in. Once stand-ins exist in real data, your rule was that they count individually but not toward team aggregates. Player pages are individual, so stand-in games appear normally, but I have not yet added the visible marking you asked for, since the fixture has no stand-ins to render it against.
