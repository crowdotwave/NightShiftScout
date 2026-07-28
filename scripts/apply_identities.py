#!/usr/bin/env python3
"""Apply reviewed identity candidates into data/curated/players.json.

**This is not a build step and must never become one.** `players.json` is
curated data: if it is lost it is gone, whereas everything in `data/derived/`
rebuilds in seconds. The rule in SCHEMA-PROPOSAL.md is that no generator
writes to the curated layer, and this script is the deliberate exception a
human runs once after reviewing `identity-candidates.json`, not something the
pipeline calls. It refuses to write without `--write`, and the diff is meant
to be read in git before committing.

What it applies:

- **tier 1**, a unique Liquipedia `steam64ID` whose account is observed playing
  on that handle's own team, becomes `confirmed`.
- **tier 2**, a Steam persona or vanity match that ALSO passes the same side
  check, becomes `probable` and never `confirmed`. The candidate came from a
  mutable display name, so the ceiling is lower however well it checks out.

What it will not do:

- **Never overwrite an existing handle with a different one.** A disagreement
  between curated data and the join is reported and skipped. The curated entry
  wins, because a human put it there on evidence this script cannot see.
- **Never downgrade.** An existing `confirmed` is not lowered to `probable`.
- **Never apply an excluded account.** See EXCLUDE below.

Standard library only. Makes no network requests.

Usage:
    python scripts/apply_identities.py            # report only
    python scripts/apply_identities.py --write
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

RANK = {"guess": 0, "probable": 1, "confirmed": 2}

# Accounts the join proposes that we refuse to name, with the reason. Kept in
# code rather than as a silent omission so the decision is reviewable.
EXCLUDE = {
    "271562520": (
        "Proposed as AVG by Liquipedia steam64ID, and left unnamed on purpose. "
        "The account appears on AVG's rostered teams in only 5 of 20 testable "
        "rosterings, and its most frequent team is Hydra Nation, which AVG is "
        "never rostered on. A different account, 399289886, appears on 12 of 20 "
        "and follows AVG's exact roster lineage across floormen, FPS Lounge and "
        "Poppers' Pupils. The two never appear on the same side in 55 sides. "
        "Naming 399289886 as AVG would be elimination, which is not evidence, "
        "so both stay unnamed. This identity has already been asserted and "
        "retracted once; unnamed beats wrong."
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--candidates", type=Path,
                        default=Path("data/derived/identity-candidates.json"))
    parser.add_argument("--players", type=Path, default=Path("data/curated/players.json"))
    parser.add_argument("--write", action="store_true", help="actually write players.json")
    args = parser.parse_args()

    candidates = json.loads(args.candidates.read_text(encoding="utf-8"))
    document = json.loads(args.players.read_text(encoding="utf-8"))
    players = document.get("players", {})

    proposals: dict[str, dict] = {}
    for account_id, record in candidates["account_candidates"].items():
        proposals[account_id] = {
            "handle": record["handle"],
            "identified": record["status"],
            "notes": f"Liquipedia player page {record['page_title']} carries this steam64ID, and the "
                     f"account is observed playing on that handle's own team. See "
                     f"scripts/resolve_identities.py.",
        }
    for record in candidates.get("persona_candidates", []):
        if not record.get("side_confirmed"):
            continue
        account_id = record["account_id"]
        if account_id in proposals:
            continue
        proposals[account_id] = {
            "handle": record["handle"],
            # Never confirmed. The candidate came from a display name that can
            # change, even though it then passed the same side check.
            "identified": "probable",
            "notes": f"Steam persona {record['personaname']!r} matches the Liquipedia handle "
                     f"{record['handle']!r} ({record['wiki_status']} on the wiki), and the account is "
                     f"observed on that handle's own team in {record['confirming_rosterings']} of "
                     f"{record['testable_rosterings']} testable rostering(s). Persona evidence caps "
                     f"at probable.",
        }

    counts = Counter()
    conflicts, skipped = [], []
    for account_id, proposal in sorted(proposals.items(), key=lambda kv: int(kv[0])):
        if account_id in EXCLUDE:
            skipped.append((account_id, proposal["handle"], EXCLUDE[account_id]))
            counts["excluded"] += 1
            continue
        existing = players.get(account_id)
        if existing and existing.get("handle"):
            if existing["handle"].lower() != proposal["handle"].lower():
                conflicts.append((account_id, existing["handle"], proposal["handle"]))
                counts["conflict, kept curated"] += 1
                continue
            if RANK.get(existing.get("identified"), 0) >= RANK[proposal["identified"]]:
                counts["already at this level or better"] += 1
                continue
            counts["upgraded"] += 1
        elif existing:
            counts["named an existing guess"] += 1
        else:
            counts["new entry"] += 1

        entry = players.setdefault(account_id, {})
        entry["handle"] = proposal["handle"]
        entry.setdefault("aka", [])
        entry["identified"] = proposal["identified"]
        entry["notes"] = proposal["notes"]

    document["players"] = dict(sorted(players.items(), key=lambda kv: int(kv[0])))

    print(f"{len(proposals)} proposal(s) from {args.candidates}")
    for key, value in sorted(counts.items()):
        print(f"  {value:>4}  {key}")
    if conflicts:
        print(f"\n{len(conflicts)} conflict(s), curated value kept:")
        for account_id, curated, proposed in conflicts:
            print(f"  {account_id}: curated {curated!r} vs proposed {proposed!r}")
    if skipped:
        print(f"\n{len(skipped)} excluded:")
        for account_id, handle, reason in skipped:
            print(f"  {account_id} ({handle}): {reason[:100]}...")

    final = Counter(v.get("identified") for v in document["players"].values())
    named = sum(1 for v in document["players"].values()
                if v.get("handle") and v.get("identified") in ("confirmed", "probable"))
    print(f"\nplayers.json would hold {len(document['players'])} entries: "
          + ", ".join(f"{v} {k}" for k, v in sorted(final.items())))
    print(f"{named} would be publishable (confirmed or probable with a handle)")

    if args.write:
        args.players.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        print(f"\nwrote {args.players}")
    else:
        print("\nreport only, pass --write to apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
