#!/usr/bin/env python3
"""Fail if a retracted claim has reappeared in any tracked document.

Reads `RETRACTIONS.md`, which is the single home for claims this project
stated and later found wrong. Each entry there carries a fenced ```forbidden
block of regexes. This script matches them against every line of every tracked
text file and exits non-zero on a hit.

The problem it solves: a claim gets corrected in one document and left standing
in another. That has happened twice, and it is silent, because a stale claim
reads exactly like a live one.

**To quote a retracted claim on purpose**, put its retraction id in square
brackets on the same line:

    This bullet previously read "verified 13 of 13" [R1].

A line carrying the id of the retraction it would otherwise trip is skipped.
Correction history stays readable and the guard stays on.

No network requests. Reads only files already in the repository.

Standard library only.

Usage:
    python scripts/check_retractions.py
    python scripts/check_retractions.py --list
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

LEDGER = Path("RETRACTIONS.md")
# Entry headings look like "## R2: match_mode ...". R0 is allowed, so the id is
# not assumed to be sequential or to start at 1.
HEADING = re.compile(r"^##\s+(R\d+)\s*:\s*(.+?)\s*$")
FENCE_OPEN = re.compile(r"^```forbidden\s*$")
FENCE_CLOSE = re.compile(r"^```\s*$")

TEXT_SUFFIXES = {".md", ".py", ".html", ".json", ".txt"}
# The ledger quotes every retracted claim by construction, and the cache is a
# raw record of what an API returned, which we do not edit for wording.
SKIP_PATHS = {Path("RETRACTIONS.md")}
SKIP_DIRS = {"data/matches", "data/liquipedia", "data/assets/avatars"}


def parse_ledger(path: Path) -> list[tuple[str, str, list[str]]]:
    """Return [(retraction_id, title, [pattern, ...])] in file order."""
    entries: list[tuple[str, str, list[str]]] = []
    current_id = current_title = None
    patterns: list[str] = []
    in_block = False

    for line in path.read_text(encoding="utf-8").splitlines():
        heading = HEADING.match(line)
        if heading and not in_block:
            if current_id:
                entries.append((current_id, current_title, patterns))
            current_id, current_title, patterns = heading.group(1), heading.group(2), []
            continue
        if FENCE_OPEN.match(line):
            in_block = True
            continue
        if in_block and FENCE_CLOSE.match(line):
            in_block = False
            continue
        if in_block and line.strip():
            patterns.append(line.strip())

    if current_id:
        entries.append((current_id, current_title, patterns))
    return entries


def tracked_files() -> list[Path]:
    """Every tracked text file. Falls back to a walk outside a git checkout."""
    try:
        out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout
        paths = [Path(line) for line in out.splitlines() if line]
    except (subprocess.CalledProcessError, FileNotFoundError):
        paths = [p for p in Path(".").rglob("*") if p.is_file()]

    keep = []
    for path in paths:
        if path in SKIP_PATHS or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        posix = path.as_posix()
        if any(posix.startswith(d) for d in SKIP_DIRS):
            continue
        keep.append(path)
    return keep


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    parser.add_argument("--list", action="store_true", help="print the ledger and exit")
    args = parser.parse_args()

    if not args.ledger.exists():
        print(f"ERROR: {args.ledger} not found")
        return 1

    entries = parse_ledger(args.ledger)
    if args.list:
        for rid, title, patterns in entries:
            print(f"{rid}: {title}")
            for pattern in patterns:
                print(f"    {pattern}")
        return 0

    compiled = []
    for rid, title, patterns in entries:
        for pattern in patterns:
            try:
                compiled.append((rid, title, re.compile(pattern)))
            except re.error as exc:
                print(f"ERROR: {rid} has an invalid pattern {pattern!r}: {exc}")
                return 1

    if not compiled:
        print("ERROR: the ledger defines no forbidden patterns, so this check is a no-op")
        return 1

    files = tracked_files()
    hits = []
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(lines, 1):
            for rid, title, pattern in compiled:
                if pattern.search(line) and f"[{rid}]" not in line:
                    hits.append((path, number, rid, title, line.strip()))

    print(f"{len(entries)} retraction(s), {len(compiled)} pattern(s), {len(files)} file(s) scanned")
    if not hits:
        print("No retracted claim found. Clean.")
        return 0

    print(f"\n{len(hits)} retracted claim(s) still present:\n")
    for path, number, rid, title, line in hits:
        print(f"  {path.as_posix()}:{number}  [{rid}] {title}")
        print(f"      {line[:110]}")
    print("\nEither correct the line, or mark it as a deliberate historical")
    print("reference by adding the retraction id in brackets, for example [R1].")
    return 1


if __name__ == "__main__":
    sys.exit(main())
