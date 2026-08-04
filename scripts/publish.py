#!/usr/bin/env python3
"""One command: refresh the data, rebuild the site, and publish it.

    python scripts/publish.py --dry-run    # report only, no network, no push
    python scripts/publish.py              # do it

Safe to run when nothing has changed. Every step is idempotent: already cached
matches are not refetched, an unchanged site produces no commit, and a run with
nothing new ends by saying so rather than pushing an empty change.

**It fails loudly rather than publishing something broken.** Three gates:

1. `build_dataset.py --strict` must pass. Any error there means the curated
   layer and the match cache disagree, and publishing that would put a wrong
   number on a public page.
2. The site must not lose pages. If fewer players are published than last run,
   the run stops. That catches an identity retraction taken too far, a curated
   file truncated by a bad edit, or a dataset that silently lost matches.
3. Any step exiting non-zero stops the run before the push.

**What it will not do automatically: name anybody.** `resolve_identities.py`
runs and reports, but applying an identity stays a reviewed step through
`apply_identities.py`. Auto-applying would have published the AVG mapping,
which three converging signals later showed was wrong. New accounts appear as
plain numbers until a human looks.

**Cold matches are reported and skipped, never waited on.** A match the API
does not hold costs a 3 per hour Steam pull, so the run publishes without it
and says which IDs are outstanding. They usually warm up within a day.

State lives in `data/derived/publish-state.json`, which is how the run knows
what changed since last time. Delete it and the next run simply has nothing to
compare against.

Standard library only.
"""

from __future__ import annotations

import argparse
import glob
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_BASE = "https://api.deadlock-api.com/v1"
USER_AGENT = "night-shift-scout-cache/1.0 (+local research tool)"
# Night Shift games are private lobbies. The bulk endpoint defaults to
# ranked,unranked, which excludes every tournament match and returns an empty
# list that looks exactly like "we do not have these".
BULK_MODES = "unranked,private_lobby,coop_bot,ranked,server_test,tutorial,hero_labs"

STATE_PATH = Path("data/derived/publish-state.json")
PAGES_BRANCH = "gh-pages"


class Failed(Exception):
    """A gate tripped. The message is what the operator needs to read."""


def run(cmd: list[str], step: str, dry: bool = False) -> str:
    """Run a pipeline step, or describe it under --dry-run."""
    printable = " ".join(str(c) for c in cmd)
    if dry:
        print(f"  would run: {printable}")
        return ""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        tail = (result.stdout or "")[-1500:] + (result.stderr or "")[-1500:]
        raise Failed(f"{step} failed (exit {result.returncode})\n{printable}\n{tail}")
    return result.stdout


def git(*args: str, cwd: Path | None = None, check: bool = True) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd)
    if check and result.returncode != 0:
        raise Failed(f"git {' '.join(args)} failed\n{result.stderr.strip()}")
    return result.stdout.strip()


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except ValueError:
            print("  note: publish-state.json is unreadable, treating this as a first run")
    return {}


def cached_match_ids(matches_dir: Path) -> set[str]:
    return {Path(p).name.split(".")[0] for p in glob.glob(str(matches_dir / "*.json.gz"))}


def wiki_match_ids(games_path: Path) -> set[str]:
    if not games_path.exists():
        return set()
    doc = json.loads(games_path.read_text(encoding="utf-8"))
    return {str(g["match_id"]) for g in doc.get("games", []) if g.get("match_id")}


def newest_editions(pages_dir: Path, count: int = 2) -> list[str]:
    editions = set()
    for path in pages_dir.glob("Deadlock_Night_Shift__*.wiki.gz"):
        parts = path.name.split("__")
        if len(parts) >= 2 and parts[1].isdigit():
            editions.add(int(parts[1]))
    return [str(e) for e in sorted(editions)[-count:]]


def bulk_held(match_ids: list[str], dry: bool) -> set[str]:
    """Which of these the API already holds. One request, no Steam pulls."""
    if not match_ids:
        return set()
    if dry:
        print(f"  would ask the bulk endpoint which of {len(match_ids)} missing match(es) are held")
        return set()
    url = (f"{API_BASE}/matches/metadata?match_ids={','.join(match_ids)}"
           f"&match_mode={BULK_MODES}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                   "Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            raw = response.read()
            if response.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
        return {str(entry["match_id"]) for entry in json.loads(raw)}
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            # Measured: the endpoint 404s when it holds NONE of the requested
            # ids, and returns 200 with a partial list when it holds some. So a
            # 404 is the answer, not a failure. Reading it as an error is what
            # made the first end to end run try to fetch three cold matches and
            # then die on their 404s.
            return set()
        print(f"  warning: bulk check returned HTTP {exc.code}, treating every missing id as cold")
        return set()
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        # Cannot tell warm from cold, so assume cold. Skipping a fetchable match
        # costs a week; hammering cold ones costs the whole run.
        print(f"  warning: bulk check failed ({exc}), treating every missing id as cold")
        return set()


def site_player_count(site_dir: Path) -> int:
    players = site_dir / "players"
    if not players.is_dir():
        return 0
    return sum(1 for p in players.iterdir() if p.is_dir() and p.name.isdigit())


def deploy(site_dir: Path, dry: bool) -> tuple[bool, str]:
    """Copy the built site onto the pages branch and push. Returns (pushed, note).

    Uses a worktree so the main working tree is never switched. The branch is an
    orphan with no connection to main's history, which is what keeps a clone of
    it small rather than dragging the match cache along.
    """
    if dry:
        print(f"  would copy {site_dir} onto {PAGES_BRANCH} and push")
        return False, "dry run"

    # The main working tree must never end up on the pages branch. It happened
    # once: the repository was found checked out on gh-pages with every file
    # tracked on main deleted from disk, which is alarming even though nothing
    # was lost because it was all committed and pushed. The exact mechanism was
    # not reproducible from the reflog, so this guards the outcome rather than
    # the suspected cause: refuse to start from the pages branch, and put HEAD
    # back afterwards whatever happens in between.
    starting_branch = git("rev-parse", "--abbrev-ref", "HEAD")
    if starting_branch == PAGES_BRANCH:
        raise Failed(
            f"the working tree is on {PAGES_BRANCH}, which is the published output and not "
            f"source.\nSwitch back to your working branch first, for example:\n"
            f"  git checkout main\nNothing has been published.")

    worktree = Path(tempfile.mkdtemp(prefix="ns-pages-"))
    # mkdtemp creates it; git worktree add needs it absent or empty.
    shutil.rmtree(worktree, ignore_errors=True)
    try:
        git("worktree", "add", str(worktree), PAGES_BRANCH)
        for entry in worktree.iterdir():
            if entry.name == ".git":
                continue
            shutil.rmtree(entry) if entry.is_dir() else entry.unlink()
        shutil.copytree(site_dir, worktree, dirs_exist_ok=True)
        # Stops Pages running the output through Jekyll, which would drop
        # anything it treats as a special path.
        (worktree / ".nojekyll").touch()

        git("add", "-A", cwd=worktree)
        if not git("status", "--porcelain", cwd=worktree):
            return False, "site is byte for byte identical to what is already published"

        # Every page carries a "Generated <timestamp>" line, so a rebuild with
        # no new data still differs from what is published. Without this the
        # "nothing changed" path could never be reached and every run would add
        # a commit. If the only changed lines are that timestamp, there is
        # nothing worth publishing and the live page keeps the date it was
        # actually built from, which is the more honest of the two.
        diff = git("diff", "--cached", "-U0", cwd=worktree)
        changed = [line for line in diff.splitlines()
                   if line.startswith(("+", "-"))
                   and not line.startswith(("+++", "---"))]
        if changed and all("Generated " in line for line in changed):
            return False, "no change beyond the build timestamp, nothing worth publishing"

        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        git("commit", "-q", "-m",
            f"Publish site, {stamp}\n\n"
            f"Generated by scripts/build_site.py on main. Do not edit here: this\n"
            f"branch is overwritten by the next publish run.",
            cwd=worktree)
        git("push", "-q", "origin", PAGES_BRANCH, cwd=worktree)
        return True, git("rev-parse", "--short", "HEAD", cwd=worktree)
    finally:
        subprocess.run(["git", "worktree", "remove", str(worktree), "--force"],
                       capture_output=True, text=True)
        shutil.rmtree(worktree, ignore_errors=True)
        subprocess.run(["git", "worktree", "prune"], capture_output=True, text=True)
        # Belt and braces. If anything moved HEAD, put it back and say so
        # loudly rather than leaving the checkout somewhere surprising.
        ended_on = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                  capture_output=True, text=True).stdout.strip()
        if ended_on and ended_on != starting_branch:
            print(f"  WARNING: HEAD moved to {ended_on} during deploy, restoring "
                  f"{starting_branch}")
            subprocess.run(["git", "checkout", starting_branch],
                           capture_output=True, text=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would happen, touch no network and push nothing")
    parser.add_argument("--skip-deploy", action="store_true",
                        help="build everything but do not push")
    parser.add_argument("--site", type=Path, default=Path("site"))
    parser.add_argument("--matches", type=Path, default=Path("data/matches"))
    parser.add_argument("--pages", type=Path, default=Path("data/liquipedia/pages"))
    args = parser.parse_args()

    dry = args.dry_run
    python = sys.executable
    started = time.time()
    state = load_state()
    report: dict = {"cold_skipped": [], "new_matches": []}

    print("Night Shift Scout publish" + ("  [DRY RUN, no network, no push]" if dry else ""))
    print("=" * 64)
    if state.get("finished_utc"):
        print(f"last run {state['finished_utc']}")

    before_matches = cached_match_ids(args.matches)

    # ---- 1. the wiki --------------------------------------------------------
    print("\n1. Liquipedia")
    editions = newest_editions(args.pages)
    run([python, "scripts/fetch_liquipedia.py"], "liquipedia page discovery", dry)
    if editions:
        # The newest pages get match IDs filled in days after the games are
        # played, so they must be refetched rather than trusted as cached.
        run([python, "scripts/fetch_liquipedia.py", *editions, "--force"],
            f"liquipedia refresh of editions {', '.join(editions)}", dry)
    run([python, "scripts/parse_liquipedia.py"], "bracket parse", dry)
    run([python, "scripts/parse_rosters.py"], "roster parse", dry)

    # ---- 2. matches ---------------------------------------------------------
    print("\n2. Matches")
    wanted = wiki_match_ids(Path("data/derived/liquipedia-games.json"))
    missing = sorted(wanted - before_matches)
    print(f"  {len(wanted)} match id(s) on the wiki, {len(before_matches)} cached, "
          f"{len(missing)} missing")
    if missing and dry:
        # Which of these are cold cannot be known without asking, and asking is
        # a network call. Report the question rather than inventing the answer.
        print(f"  would ask the bulk endpoint which of the {len(missing)} are held, then fetch those")
        report["missing_unchecked"] = missing
    elif missing:
        held = bulk_held(missing, dry)
        cold = [m for m in missing if m not in held]
        warm = [m for m in missing if m in held]
        report["cold_skipped"] = cold
        if cold:
            print(f"  {len(cold)} cold at the API, skipped: {', '.join(cold[:8])}"
                  + (" ..." if len(cold) > 8 else ""))
        if warm:
            print(f"  {len(warm)} available, fetching")
            listing = Path(tempfile.gettempdir()) / "ns-warm-ids.txt"
            listing.write_text("\n".join(warm) + "\n", encoding="utf-8")
            # Best effort, deliberately not a gate. A match that fails to fetch
            # writes nothing and is retried next week, so it must not stop a
            # publish that is otherwise fine. The fatal checks are further down.
            try:
                run([python, "scripts/fetch_matches.py", str(listing), "--max-wait", "30"],
                    "match fetch", dry)
            except Failed as exc:
                print(f"  warning: some matches did not fetch, continuing without them")
                print(f"    {str(exc).splitlines()[0]}")
                report["fetch_warning"] = True
    else:
        print("  nothing to fetch")

    # ---- 3. derive ----------------------------------------------------------
    print("\n3. Rebuild")
    run([python, "scripts/generate_nights.py"], "night generation", dry)
    if not dry:
        run([python, "scripts/fetch_steam.py"], "steam profiles", dry)
    else:
        print("  would run: scripts/fetch_steam.py")
    # Gate 1. --strict turns any validation error into a non-zero exit.
    run([python, "scripts/build_dataset.py", "--strict"], "dataset build", dry)
    identities = run([python, "scripts/resolve_identities.py"], "identity measurement", dry)
    build_output = run([python, "scripts/build_site.py"], "site build", dry)

    # ---- 4. gates -----------------------------------------------------------
    print("\n4. Checks")
    published = site_player_count(args.site)
    previous = state.get("players_published")
    if previous is not None and published < previous and not dry:
        raise Failed(
            f"the site would publish {published} player pages, down from {previous} last run.\n"
            f"Losing pages usually means a curated file was truncated or an identity was\n"
            f"retracted by accident. Nothing has been pushed. Check data/curated/players.json.")
    print(f"  player pages: {published}"
          + (f" (was {previous})" if previous is not None else " (no previous run to compare)"))
    run([python, "scripts/check_retractions.py"], "retraction check", dry)

    # ---- 5. publish ---------------------------------------------------------
    print("\n5. Publish")
    pushed, note = (False, "skipped") if args.skip_deploy else deploy(args.site, dry)
    print(f"  {'pushed ' + note if pushed else 'not pushed: ' + note}")

    # ---- 6. report ----------------------------------------------------------
    after_matches = cached_match_ids(args.matches)
    report["new_matches"] = sorted(after_matches - before_matches)
    dataset = {}
    dataset_path = Path("data/derived/dataset.json")
    if dataset_path.exists():
        doc = json.loads(dataset_path.read_text(encoding="utf-8"))
        dataset = {
            "matches": len(doc.get("matches", [])),
            "player_matches": len(doc.get("player_matches", [])),
            "accounts": len(doc.get("players", [])),
            "publishable": sum(1 for p in doc.get("players", []) if p.get("publishable")),
        }
    awaiting = dataset.get("accounts", 0) - dataset.get("publishable", 0)

    def delta(key, value):
        old = state.get(key)
        if old is None or old == value:
            return ""
        return f"  ({value - old:+d})"

    print("\n" + "=" * 64)
    print("REPORT")
    print(f"  new matches ingested      {len(report['new_matches'])}"
          + (f"  {', '.join(report['new_matches'][:6])}" if report["new_matches"] else ""))
    if dry and report.get("missing_unchecked"):
        print(f"  missing, cold unchecked   {len(report['missing_unchecked'])}"
              f"  {', '.join(report['missing_unchecked'][:6])}")
    else:
        print(f"  cold matches skipped      {len(report['cold_skipped'])}"
              + (f"  {', '.join(report['cold_skipped'][:6])}" if report["cold_skipped"] else ""))
    print(f"  matches in dataset        {dataset.get('matches', 0)}{delta('matches', dataset.get('matches', 0))}")
    print(f"  player-match rows         {dataset.get('player_matches', 0)}{delta('player_matches', dataset.get('player_matches', 0))}")
    print(f"  accounts seen             {dataset.get('accounts', 0)}{delta('accounts', dataset.get('accounts', 0))}")
    print(f"  pages published           {published}{delta('players_published', published)}")
    print(f"  accounts awaiting review  {awaiting}{delta('awaiting_review', awaiting)}")
    if awaiting:
        print("     these render as plain numbers. To name any of them, review")
        print("     data/derived/identity-candidates.json then run:")
        print("       python scripts/apply_identities.py            # report")
        print("       python scripts/apply_identities.py --write    # apply")
    for line in (identities or "").splitlines():
        if "would get a name from this join" in line or "would be newly named" in line:
            print(f"     {line.strip()}")
    print(f"  elapsed                   {time.time() - started:.0f}s")

    if dry:
        print("\nDry run. Nothing was fetched, built or pushed.")
        return 0

    state.update({
        "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "players_published": published,
        "awaiting_review": awaiting,
        "pushed": pushed,
        **dataset,
    })
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    print(f"\nstate written to {STATE_PATH}")
    if pushed:
        print("live at https://crowdotwave.github.io/NightShiftScout/ within a minute or two")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Failed as exc:
        print(f"\nSTOPPED: {exc}", file=sys.stderr)
        print("\nNothing was published.", file=sys.stderr)
        raise SystemExit(1)
