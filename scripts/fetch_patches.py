#!/usr/bin/env python3
"""Fetch the balance patch dates and cache them in the repository.

`GET /patches/big-days` returns a bare array of ISO 8601 timestamps, newest
first. The app calls it live to draw the cross-patch notice, but the analysis
side needs a fixed boundary that does not move under it, and the standing rule
is that anything fetched gets cached into the repository rather than read out
of a document.

The dated filename is deliberate, matching the hero snapshot convention: a
patch list is a point-in-time observation, and an old build should be able to
say which boundary it used.

Standard library only.

Usage:
    python scripts/fetch_patches.py
    python scripts/fetch_patches.py --out data/assets/patches-big-days-2026-07-27.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import urllib.request
from pathlib import Path

API_BASE = "https://api.deadlock-api.com/v1"
USER_AGENT = "night-shift-scout-cache/1.0 (+local research tool)"
DEFAULT_DIR = Path("data/assets")


def fetch(url: str, timeout: int = 60) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    out = args.out or DEFAULT_DIR / f"patches-big-days-{today}.json"

    days = json.loads(fetch(f"{API_BASE}/patches/big-days"))
    if not isinstance(days, list) or not days:
        print(f"ERROR: expected a non-empty array, got {type(days).__name__}")
        return 1

    # Newest first is what the endpoint documents. Sort defensively rather than
    # trusting it, since the boundary depends on which entry is actually latest.
    ordered = sorted(days, reverse=True)
    if ordered != days:
        print("NOTE: response was not in newest-first order, sorted it")

    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "source": f"{API_BASE}/patches/big-days",
        "fetched_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "note": "Balance patch dates, newest first. Cached so the patch boundary "
                "is a file rather than a number quoted in prose.",
        "big_days": ordered,
    }
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(f"{len(ordered)} patch date(s), newest {ordered[0]}")
    print(f"wrote {out}")

    # The gap between the two newest is the useful sanity check: it says whether
    # the newest date is a current patch or a stale one we should not lean on.
    if len(ordered) >= 2:
        newest = dt.datetime.fromisoformat(ordered[0].replace("Z", "+00:00"))
        previous = dt.datetime.fromisoformat(ordered[1].replace("Z", "+00:00"))
        age = (dt.datetime.now(dt.timezone.utc) - newest).days
        print(f"newest is {age} day(s) old; previous gap was {(newest - previous).days} day(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
