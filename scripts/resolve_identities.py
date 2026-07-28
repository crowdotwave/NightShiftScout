#!/usr/bin/env python3
"""Measure how far Liquipedia `steam64ID` gets us toward naming our accounts.

Writes `data/derived/identity-candidates.json`. **Curates nothing.** Nothing
here is written to `data/curated/`, and no name is published by running it.
The point is to answer "how many of our accounts can be named, and on what
evidence" before anyone hand edits a file.

The join, and every guardrail on it, comes straight from LIQUIPEDIA-NOTES.md:

1. `account_id = steam64ID - 76561197960265728`.
2. **A steam64ID on more than one player page corroborates neither mapping**
   and is discarded for both. `Zeno` and `Rocaine` carry the same ID despite
   being different people, and that cost a wrong mapping once already.
3. **Play data wins on conflict.** A wiki ID that contradicts the match data
   never overwrites it.
4. **Read substitution records before calling a mismatch.** A rostered player
   absent from a game is usually explained by the source itself.

Evidence levels, deliberately matching `identified` in players.json:

    confirmed   the ID is unique across player pages AND the account is
                observed playing on that handle's own team, in a match from an
                edition where the handle was rostered
    probable    the ID is unique but cannot be checked against play data,
                because we hold no match for that team and edition
    rejected    the account is observed, but never on the side its handle was
                rostered on, and no substitution record explains it
    collision   the ID appears on two or more player pages
    no-id       the handle has a page but no steam64ID
    no-page     the handle has no page at all

Side attribution comes from the hero pick join already recorded in the night
files, so this needs no team identity model and no lineup: `_wiki_team` on a
side is the bracket's own name for it.

Standard library only. Makes no network requests.

Usage:
    python scripts/resolve_identities.py
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

STEAM64_OFFSET = 76561197960265728
STEAM_ID = re.compile(r"\|\s*steam64ID\s*=\s*([0-9]{5,25})\s*", re.IGNORECASE)
SUBSTITUTION = re.compile(r"\{\{Substitution\s*\|([^{}]*)\}\}", re.IGNORECASE)
PAGE_FILE = re.compile(r"^(?!Deadlock_Night_Shift__).+\.wiki\.gz$")


def load_player_pages(pages_dir: Path) -> dict[str, str]:
    """title -> wikitext, for pages that are not edition pages."""
    out = {}
    for path in sorted(pages_dir.glob("*.wiki.gz")):
        if not PAGE_FILE.match(path.name):
            continue
        title = path.name[: -len(".wiki.gz")].replace("__", "/").replace("_", " ")
        out[title] = gzip.decompress(path.read_bytes()).decode("utf-8")
    return out


def load_substitutions(pages_dir: Path) -> set[str]:
    """Handles named in any {{Substitution|out=X|in=Y}}, lowercased.

    Coarse on purpose. It is used only to soften a mismatch into "explained",
    and being listed anywhere as a substitute is enough to stop this script
    accusing a page of being wrong.
    """
    names: set[str] = set()
    for path in sorted(pages_dir.glob("Deadlock_Night_Shift__*.wiki.gz")):
        text = gzip.decompress(path.read_bytes()).decode("utf-8")
        for body in SUBSTITUTION.findall(text):
            for part in body.split("|"):
                if "=" in part:
                    key, _, value = part.partition("=")
                    if key.strip().lower() in ("out", "in") and value.strip():
                        names.add(value.strip().lower())
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pages", type=Path, default=Path("data/liquipedia/pages"))
    parser.add_argument("--rosters", type=Path, default=Path("data/derived/liquipedia-rosters.json"))
    parser.add_argument("--nights", type=Path, default=Path("data/curated/nights"))
    parser.add_argument("--dataset", type=Path, default=Path("data/derived/dataset.json"))
    parser.add_argument("--curated", type=Path, default=Path("data/curated/players.json"))
    parser.add_argument("--profiles", type=Path, default=Path("data/assets/steam-profiles.json"))
    parser.add_argument("--out", type=Path, default=Path("data/derived/identity-candidates.json"))
    args = parser.parse_args()

    roster_rows = [r for r in json.loads(args.rosters.read_text(encoding="utf-8"))["rows"]
                   if r["role"] == "player"]
    pages = load_player_pages(args.pages)
    subs = load_substitutions(args.pages)

    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    our_accounts = {p["account_id"] for p in dataset["players"]}
    curated = json.loads(args.curated.read_text(encoding="utf-8")).get("players", {})

    # ---- observed sides, from the hero pick join in the night files --------
    # (edition, region, wiki_team) -> set of account ids seen playing for it
    observed: dict[tuple, set[str]] = defaultdict(set)
    for path in sorted(args.nights.glob("*.json")):
        night = json.loads(path.read_text(encoding="utf-8"))
        key_base = (night.get("edition"), night.get("region"))
        for entry in night.get("matches", []):
            for side in entry.get("sides", []):
                team = side.get("_wiki_team")
                if not team:
                    continue
                for account in side.get("_observed_account_ids", []):
                    observed[key_base + (team.strip().lower(),)].add(str(account))

    # ---- steam64ID per page, and the collision check -----------------------
    id_to_titles: dict[int, set[str]] = defaultdict(set)
    title_to_id: dict[str, int] = {}
    for title, text in pages.items():
        found = STEAM_ID.search(text)
        if found:
            steam64 = int(found.group(1))
            title_to_id[title] = steam64
            id_to_titles[steam64].add(title)
    collisions = {sid: titles for sid, titles in id_to_titles.items() if len(titles) > 1}

    # ---- classify every rostered handle ------------------------------------
    by_title: dict[str, list[dict]] = defaultdict(list)
    for row in roster_rows:
        by_title[row["page_title"]].append(row)

    results = []
    for title in sorted(by_title, key=str.lower):
        rows = by_title[title]
        handle = rows[0]["handle"]
        record = {
            "page_title": title,
            "handle": handle,
            "editions": sorted({f"{r['edition']}{r['region']}" for r in rows}),
            "teams": sorted({r["team"] for r in rows}),
            "roster_rows": len(rows),
        }

        if title not in pages:
            record["status"] = "no-page"
            results.append(record)
            continue
        steam64 = title_to_id.get(title)
        if steam64 is None:
            record["status"] = "no-id"
            results.append(record)
            continue
        if steam64 in collisions:
            record["status"] = "collision"
            record["collides_with"] = sorted(collisions[steam64] - {title})
            results.append(record)
            continue

        account_id = str(steam64 - STEAM64_OFFSET)
        record["account_id"] = account_id
        record["in_our_data"] = account_id in our_accounts

        # Did this account play for this handle's own team, in an edition the
        # handle was rostered for? Correct side comes from the hero pick join.
        hits, testable = 0, 0
        for row in rows:
            key = (row["edition"], row["region"], row["team"].strip().lower())
            if key not in observed:
                continue
            testable += 1
            if account_id in observed[key]:
                hits += 1
        record["testable_rosterings"] = testable
        record["confirming_rosterings"] = hits

        if testable == 0:
            record["status"] = "probable"
        elif hits > 0:
            record["status"] = "confirmed"
        elif handle.lower() in subs:
            record["status"] = "probable"
            record["note"] = "never observed on its own side, but the wiki records a substitution for this handle"
        else:
            record["status"] = "rejected"
            record["note"] = "observed rosterings exist but the account never appears on that side"
        results.append(record)

    # ---- tier 2: persona and vanity slug, for handles with no usable ID ----
    # The documented fallback chain, and it is weaker by construction: a Steam
    # persona is a current display name that changes freely, so on its own it
    # is `probable` at best and never `confirmed`.
    #
    # But the side check does not care where a candidate came from. A persona
    # match that ALSO puts the account on its own team's side, in an edition
    # that handle was rostered for, has passed exactly the test the wiki IDs
    # pass. That is recorded separately rather than merged, so the evidence
    # stays legible.
    profiles = {str(p["account_id"]): p
                for p in json.loads(args.profiles.read_text(encoding="utf-8"))["profiles"]}

    def normalise(value: str | None) -> str:
        return re.sub(r"[^a-z0-9]", "", (value or "").lower())

    def vanity_of(profile: dict) -> str:
        found = re.search(r"/id/([^/]+)/?$", profile.get("profileurl") or "")
        return normalise(found.group(1)) if found else ""

    unresolved = [r for r in results
                  if r["status"] in ("no-page", "no-id", "collision", "rejected")]
    claimed = {r["account_id"] for r in results
               if r.get("account_id") and r["status"] in ("confirmed", "probable")}

    persona_candidates = []
    for record in unresolved:
        key = normalise(record["handle"])
        if len(key) < 3:
            continue
        for account_id, profile in profiles.items():
            if account_id in claimed or account_id not in our_accounts:
                continue
            persona, vanity = normalise(profile.get("personaname")), vanity_of(profile)
            exact = key in (persona, vanity)
            contained = len(key) >= 5 and (key in persona or key in vanity)
            if not (exact or contained):
                continue
            hits, testable = 0, 0
            for row in by_title[record["page_title"]]:
                side_key = (row["edition"], row["region"], row["team"].strip().lower())
                if side_key not in observed:
                    continue
                testable += 1
                if account_id in observed[side_key]:
                    hits += 1
            persona_candidates.append({
                "page_title": record["page_title"],
                "handle": record["handle"],
                "account_id": account_id,
                "personaname": profile.get("personaname"),
                "match": "exact" if exact else "contained",
                "wiki_status": record["status"],
                "testable_rosterings": testable,
                "confirming_rosterings": hits,
                # Side confirmed means it passed the same test the wiki IDs
                # pass. It is still not `confirmed`, because the candidate was
                # generated from a mutable display name.
                "side_confirmed": hits > 0,
            })

    # One handle to one account, in both directions, or it is not a name.
    per_handle = Counter(c["page_title"] for c in persona_candidates)
    per_account = Counter(c["account_id"] for c in persona_candidates)
    persona_clean = [c for c in persona_candidates
                     if per_handle[c["page_title"]] == 1 and per_account[c["account_id"]] == 1]
    persona_ambiguous = [c for c in persona_candidates if c not in persona_clean]

    # ---- what this would give us over the accounts we actually hold --------
    named: dict[str, list[dict]] = defaultdict(list)
    for record in results:
        if record.get("status") in ("confirmed", "probable") and record.get("account_id"):
            named[record["account_id"]].append(record)

    # An account claimed by two different handles is not a name, it is a clash.
    clashes = {acc: recs for acc, recs in named.items() if len(recs) > 1}
    resolvable = {acc: recs[0] for acc, recs in named.items() if len(recs) == 1}
    covered = {acc: rec for acc, rec in resolvable.items() if acc in our_accounts}

    status_counts = Counter(r["status"] for r in results)
    already = {a for a, v in curated.items()
               if v.get("identified") in ("confirmed", "probable") and v.get("handle")}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({
        "schema_version": 1,
        "generator": "scripts/resolve_identities.py",
        "note": "Candidates only. Nothing here is curated or published. See "
                "LIQUIPEDIA-NOTES.md for the guardrails encoded in the status values.",
        "source": "https://liquipedia.net/deadlock/",
        "license": "CC-BY-SA 3.0",
        "handles": results,
        "account_candidates": {acc: {"handle": rec["handle"], "status": rec["status"],
                                     "page_title": rec["page_title"]}
                               for acc, rec in sorted(covered.items(), key=lambda kv: int(kv[0]))},
        "account_clashes": {acc: [r["handle"] for r in recs] for acc, recs in sorted(clashes.items())},
        "persona_candidates": sorted(persona_clean, key=lambda c: int(c["account_id"])),
        "persona_ambiguous": sorted(persona_ambiguous, key=lambda c: int(c["account_id"])),
    }, indent=2) + "\n", encoding="utf-8")

    print(f"Rostered handles: {len(results)} distinct page titles across {len(roster_rows)} roster rows")
    print()
    for status in ("confirmed", "probable", "rejected", "collision", "no-id", "no-page"):
        print(f"  {status_counts.get(status, 0):>4}  {status}")
    print()
    print(f"Accounts in our dataset: {len(our_accounts)}")
    print(f"  {len(covered):>4}  would get a name from this join")
    print(f"        of which confirmed: {sum(1 for r in covered.values() if r['status'] == 'confirmed')}")
    print(f"        of which probable:  {sum(1 for r in covered.values() if r['status'] == 'probable')}")
    print(f"  {len(our_accounts - set(covered)):>4}  would remain unnamed")
    print(f"  {len(already):>4}  already carry a curated name today")
    print(f"  {len(set(covered) - already):>4}  would be newly named")
    if clashes:
        print(f"\n{len(clashes)} account(s) claimed by more than one handle, excluded:")
        for acc, recs in sorted(clashes.items()):
            print(f"  {acc}: {', '.join(r['handle'] for r in recs)}")
    resolvable_not_ours = set(resolvable) - our_accounts
    print(f"\n{len(resolvable_not_ours)} resolvable account(s) never appear in our matches, "
          f"so they name nobody we hold")

    side_ok = [c for c in persona_clean if c["side_confirmed"]]
    print()
    print("Tier 2, persona or vanity match on a handle with no usable wiki ID:")
    print(f"  {len(persona_candidates):>4}  raw candidate pairings")
    print(f"  {len(persona_clean):>4}  unambiguous, one handle to one account both ways")
    print(f"  {len(side_ok):>4}  of those ALSO observed on their own team's side")
    print(f"  {len(persona_clean) - len(side_ok):>4}  persona evidence only, never side confirmed")
    print(f"  {len(persona_ambiguous):>4}  ambiguous, excluded")
    remaining = our_accounts - set(covered) - {c["account_id"] for c in persona_clean}
    print()
    print(f"Ceiling with both tiers: {len(covered) + len(persona_clean)} of {len(our_accounts)} named, "
          f"{len(remaining)} unreachable")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
