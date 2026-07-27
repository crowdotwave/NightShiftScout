#!/usr/bin/env python3
"""Copy hand-produced files into data/artifacts/ as permanent historical records.

This is for CSV exports and localStorage dumps out of the console app: things
that exist nowhere else and cannot be regenerated from the API. They are
copied byte for byte and are never rewritten, reformatted, or migrated, even
after a later schema supersedes them. If a future format replaces one, the
old file still stands as the record of what was true at the time.

Every import is recorded in data/artifacts/MANIFEST.json with a SHA-256 of
the contents, so later corruption or accidental edits are detectable. The
manifest is metadata about the files; it never changes the files themselves.

Standard library only, so there is nothing to install.

Usage:
    python scripts/import_artifact.py exports/leaderboard.csv
    python scripts/import_artifact.py --label night-shift-49 dump.json notes.csv
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_ROOT = Path("data/artifacts")
MANIFEST_NAME = "MANIFEST.json"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(root: Path) -> dict:
    manifest_path = root / MANIFEST_NAME
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    return {"description": "Hand-produced artifacts. Files here are immutable once imported.", "artifacts": []}


def save_manifest(root: Path, manifest: dict) -> None:
    (root / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def unique_destination(folder: Path, name: str) -> Path:
    """Never overwrite. If the name is taken, add a numeric suffix."""
    candidate = folder / name
    if not candidate.exists():
        return candidate
    stem, suffix = Path(name).stem, Path(name).suffix
    counter = 2
    while True:
        candidate = folder / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="+", type=Path, help="Files to preserve")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help=f"Artifact root (default: {DEFAULT_ROOT})")
    parser.add_argument("--label", help="Subfolder name (default: today's date, UTC)")
    parser.add_argument("--note", help="Free text recorded in the manifest, e.g. what this export covers")
    args = parser.parse_args()

    missing = [str(f) for f in args.files if not f.is_file()]
    if missing:
        parser.error("not a file: " + ", ".join(missing))

    label = args.label or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    folder = args.root / label
    folder.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest(args.root)
    known = {entry["sha256"] for entry in manifest["artifacts"]}
    imported, duplicates = [], []

    for source in args.files:
        checksum = sha256_of(source)
        if checksum in known:
            existing = next(e for e in manifest["artifacts"] if e["sha256"] == checksum)
            print(f"  {source.name}: identical content already stored as {existing['path']}, skipping")
            duplicates.append(source.name)
            continue

        destination = unique_destination(folder, source.name)
        shutil.copy2(source, destination)

        # Confirm the copy is byte identical before recording it as preserved.
        if sha256_of(destination) != checksum:
            print(f"  {source.name}: ERROR, copy does not match source, removing")
            destination.unlink()
            return 1

        entry = {
            "path": str(destination.relative_to(args.root)).replace("\\", "/"),
            "original_name": source.name,
            "original_path": str(source.resolve()),
            "bytes": source.stat().st_size,
            "sha256": checksum,
            "imported_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        if args.note:
            entry["note"] = args.note
        manifest["artifacts"].append(entry)
        known.add(checksum)
        imported.append(entry)
        print(f"  {source.name}: preserved as {entry['path']} ({entry['bytes']:,} bytes)")

    if imported:
        save_manifest(args.root, manifest)

    print()
    print(f"Done. {len(imported)} imported, {len(duplicates)} skipped as already present.")
    print(f"Manifest now tracks {len(manifest['artifacts'])} artifact(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
