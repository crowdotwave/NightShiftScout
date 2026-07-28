#!/usr/bin/env python3
"""Download the fonts and hero icons the public site needs, into the repository.

The site must fetch nothing at view time. Two things in `index.html` break that
rule if lifted as they are:

- **Three Google Fonts by `<link>`.** Every visitor would hit
  `fonts.googleapis.com` and `fonts.gstatic.com`, handing their IP to a third
  party on every page load. Same decision already taken for Steam avatars.
- **Hero icons on `assets-bucket.deadlock-api.com`.** Hotlinking a community
  run bucket puts our traffic on someone else's bill and breaks the day a URL
  rotates.

Both are downloaded once and served locally.

Licensing, checked before doing this:

- Chakra Petch, Barlow and JetBrains Mono are all under the SIL Open Font
  License 1.1, which explicitly permits redistribution and self-hosting. The
  licence text is written alongside the files.
- Hero icons are game assets served by the community API. They are downloaded
  for the same reason the avatars were, and the site credits deadlock-api.

Standard library only.

Usage:
    python scripts/fetch_web_assets.py
    python scripts/fetch_web_assets.py --skip-fonts
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

# The exact families and weights index.html asks for.
FONT_CSS = ("https://fonts.googleapis.com/css2"
            "?family=Chakra+Petch:wght@500;600;700"
            "&family=Barlow:wght@400;500;600"
            "&family=JetBrains+Mono:wght@400;500;700&display=swap")

# Without a modern browser UA, Google serves ttf instead of woff2, which is
# roughly four times the bytes for the same glyphs.
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
PLAIN_UA = "night-shift-scout-cache/1.0 (+local research tool)"

FONT_LICENCE = """These fonts are redistributed under the SIL Open Font License 1.1.

  Chakra Petch    Copyright (c) Cadson Demak
  Barlow          Copyright (c) Jeremy Tribby
  JetBrains Mono  Copyright (c) JetBrains

The OFL permits bundling and self-hosting. Full text:
https://scripts.sil.org/OFL

Downloaded by scripts/fetch_web_assets.py so the public site makes no request
to a third party when someone views a page.
"""


def get(url: str, ua: str = PLAIN_UA, timeout: int = 60) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_fonts(out_dir: Path) -> tuple[int, str]:
    """Download woff2 files and return (count, rewritten CSS)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    css = get(FONT_CSS, ua=BROWSER_UA).decode("utf-8")

    saved = 0
    seen: dict[str, str] = {}

    def replace(match: re.Match) -> str:
        url = match.group(1)
        if url in seen:
            return f"url({seen[url]})"
        # Name the file from the family and weight in the surrounding block, so
        # the directory is readable rather than a list of hashes.
        block_start = css.rfind("@font-face", 0, match.start())
        block = css[block_start:match.start()]
        family = re.search(r"font-family:\s*'([^']+)'", block)
        weight = re.search(r"font-weight:\s*(\d+)", block)
        subset = re.search(r"/\*\s*([a-z0-9-]+)\s*\*/", css[:block_start][-200:])
        name = "-".join(filter(None, [
            (family.group(1) if family else "font").replace(" ", ""),
            weight.group(1) if weight else None,
            subset.group(1) if subset else None,
        ])) + ".woff2"
        try:
            (out_dir / name).write_bytes(get(url, ua=BROWSER_UA, timeout=30))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"    FAILED {name}: {exc}")
            return match.group(0)
        nonlocal saved
        saved += 1
        seen[url] = f"fonts/{name}"
        return f"url(fonts/{name})"

    rewritten = re.sub(r"url\((https://fonts\.gstatic\.com/[^)]+)\)", replace, css)
    (out_dir / "OFL.txt").write_text(FONT_LICENCE, encoding="utf-8")
    return saved, rewritten


def fetch_hero_icons(assets_dir: Path, out_dir: Path, delay: float) -> tuple[int, int, list[str]]:
    snapshots = sorted(assets_dir.glob("heroes-*.json.gz"))
    if not snapshots:
        return 0, 0, ["no hero snapshot found"]
    heroes = json.loads(gzip.decompress(snapshots[-1].read_bytes()))
    out_dir.mkdir(parents=True, exist_ok=True)

    saved = skipped = 0
    failed: list[str] = []
    for hero in heroes:
        url = (hero.get("images") or {}).get("icon_image_small")
        if not url:
            continue
        destination = out_dir / f"{hero['id']}{Path(url).suffix or '.png'}"
        if destination.exists():
            skipped += 1
            continue
        try:
            destination.write_bytes(get(url, timeout=30))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            failed.append(f"hero {hero['id']} ({hero.get('name')}): {exc}")
            continue
        saved += 1
        time.sleep(delay)
    return saved, skipped, failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--assets", type=Path, default=Path("data/assets"))
    parser.add_argument("--delay", type=float, default=0.1)
    parser.add_argument("--skip-fonts", action="store_true")
    parser.add_argument("--skip-icons", action="store_true")
    args = parser.parse_args()

    if not args.skip_fonts:
        print("fonts ...")
        count, css = fetch_fonts(args.assets / "fonts")
        (args.assets / "fonts.css").write_text(css, encoding="utf-8")
        print(f"  {count} font file(s), rewritten CSS in {args.assets / 'fonts.css'}")

    if not args.skip_icons:
        print("hero icons ...")
        saved, skipped, failed = fetch_hero_icons(args.assets, args.assets / "hero-icons", args.delay)
        print(f"  {saved} downloaded, {skipped} already present, {len(failed)} failed")
        for line in failed[:10]:
            print(f"    {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
