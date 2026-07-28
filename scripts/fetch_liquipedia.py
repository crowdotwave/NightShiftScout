#!/usr/bin/env python3
"""Fetch Night Shift wikitext from Liquipedia and cache it in the repository.

One file per page, under `data/liquipedia/pages/<title>.wiki.gz`, holding the
exact wikitext the API returned. A `manifest.json` alongside records, for each
page, the revision ID and timestamp it came from and when we fetched it. That
manifest is the provenance trail: CC-BY-SA attribution needs to point at a
source page, and a revision ID makes "this is what the page said" checkable
later.

**Why this script exists at all.** The first Liquipedia probe ran from a
scratch directory and only its *output* was kept, a list of match IDs. The
wikitext behind it was thrown away, so side mapping and bracket stage, both
of which were solved and written up, could not actually be computed. Anything
fetched belongs in the repository. That is the entire lesson here.

Terms honoured, all from `https://liquipedia.net/api-terms-of-use`:

- **1 request per 2 seconds.** Enforced below, and cheap to obey because up
  to 50 titles fit in one request: all 98 edition pages cost 2 requests.
- **`action=parse` is 1 per 30 seconds and we never use it.**
  `prop=revisions` returns raw wikitext under the normal limit.
- **A descriptive User-Agent identifying the project with a contact route.**
  Ours names the project and its GitHub repository. It deliberately carries
  no email address.
- **Accept gzip**, which we do, and decompress ourselves.
- **Re-use the connection**, so this holds one HTTPS connection open for the
  whole run rather than reconnecting per request.
- **No scraping of generated HTML.** API only. That is a terms issue, not
  merely a rate issue.

Content is CC-BY-SA 3.0. See LIQUIPEDIA-NOTES.md.

The cache is authoritative: a page already cached is never re-requested
unless `--force`. Since match IDs are filled in days after an edition is
played, `--force` on the two newest pages is the weekly refresh, at 2
requests.

Standard library only.

Usage:
    python scripts/fetch_liquipedia.py                    # all edition pages
    python scripts/fetch_liquipedia.py --force 48 49      # refresh two editions
    python scripts/fetch_liquipedia.py --dry-run
"""

from __future__ import annotations

import argparse
import gzip
import http.client
import json
import os
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

HOST = "liquipedia.net"
PATH = "/deadlock/api.php"
USER_AGENT = ("NightShiftScout/1.0 "
              "(https://github.com/crowdotwave/NightShiftScout; contact via GitHub issues)")
MIN_INTERVAL_S = 2.0
TITLES_PER_REQUEST = 50
SERIES_PREFIX = "Deadlock Night Shift"
DEFAULT_OUT = Path("data/liquipedia")


class Client:
    """One persistent HTTPS connection, spaced at the documented rate limit."""

    def __init__(self, interval: float = MIN_INTERVAL_S):
        self.interval = interval
        self.connection: http.client.HTTPSConnection | None = None
        self.last_request = 0.0
        self.requests = 0

    def _wait(self) -> None:
        elapsed = time.monotonic() - self.last_request
        if self.last_request and elapsed < self.interval:
            time.sleep(self.interval - elapsed)

    def get(self, params: dict[str, str]) -> dict:
        self._wait()
        if self.connection is None:
            self.connection = http.client.HTTPSConnection(HOST, timeout=60)
        url = f"{PATH}?{urllib.parse.urlencode(params)}"
        headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}
        for attempt in range(3):
            try:
                self.connection.request("GET", url, headers=headers)
                response = self.connection.getresponse()
                body = response.read()
                self.last_request = time.monotonic()
                self.requests += 1
                if response.getheader("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                if response.status == 429:
                    wait = float(response.getheader("Retry-After") or 30)
                    print(f"    rate limited, waiting {wait:.0f}s", flush=True)
                    time.sleep(wait)
                    continue
                if response.status != 200:
                    raise RuntimeError(f"HTTP {response.status} for {params.get('titles', url)}")
                return json.loads(body)
            except (http.client.HTTPException, OSError) as exc:
                # A dropped keep-alive is normal. Rebuild and retry, but do
                # not retry forever: a genuine outage should surface.
                print(f"    connection problem ({exc}), reconnecting", flush=True)
                self.close()
                self.connection = http.client.HTTPSConnection(HOST, timeout=60)
                time.sleep(2 ** attempt)
        raise RuntimeError("gave up after 3 attempts")

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None


def safe_name(title: str) -> str:
    """Filesystem safe, reversible enough to read at a glance.

    Slashes become double underscores rather than nested directories, so the
    cache stays one flat listing that is easy to diff and eyeball.
    """
    return title.replace("/", "__").replace(" ", "_")


def list_series_pages(client: Client) -> list[str]:
    """Every page under the Night Shift prefix, via allpages."""
    titles: list[str] = []
    params = {"action": "query", "list": "allpages", "apprefix": SERIES_PREFIX,
              "aplimit": "500", "format": "json", "formatversion": "2"}
    data = client.get(params)
    for page in data.get("query", {}).get("allpages", []):
        titles.append(page["title"])
    return titles


def edition_pages(titles: list[str]) -> list[str]:
    """Keep only `<prefix>/<edition>/<region>` pages, dropping the index pages.

    Anything that does not split into exactly three parts with a numeric
    edition is not an edition page. `Deadlock Night Shift/Open` and the two
    `Trolli Open` pages fall out here.
    """
    keep = []
    for title in titles:
        parts = title.split("/")
        if len(parts) == 3 and parts[0] == SERIES_PREFIX and parts[1].isdigit():
            keep.append(title)
    return sorted(keep, key=lambda t: (int(t.split("/")[1]), t.split("/")[2]))


def write_atomic(destination: Path, body: bytes) -> None:
    temp = destination.with_name(destination.name + ".part")
    temp.write_bytes(body)
    os.replace(temp, destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("editions", nargs="*",
                        help="Edition numbers to limit the fetch to. Default: every edition page.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--force", action="store_true", help="Re-fetch pages already cached")
    parser.add_argument("--dry-run", action="store_true", help="Report without fetching content")
    args = parser.parse_args()

    pages_dir = args.out / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out / "manifest.json"
    manifest = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")).get("pages", {})

    client = Client()
    try:
        print("Enumerating Night Shift pages ...", flush=True)
        all_titles = list_series_pages(client)
        titles = edition_pages(all_titles)
        print(f"  {len(all_titles)} page(s) under the prefix, {len(titles)} edition page(s)",
              flush=True)

        if args.editions:
            wanted = {str(int(e)) for e in args.editions}
            titles = [t for t in titles if t.split("/")[1] in wanted]
            print(f"  limited to editions {sorted(wanted, key=int)}: {len(titles)} page(s)",
                  flush=True)

        todo = [t for t in titles
                if args.force or not (pages_dir / f"{safe_name(t)}.wiki.gz").exists()]
        print(f"{len(titles)} page(s) wanted, {len(titles) - len(todo)} already cached, "
              f"{len(todo)} to fetch", flush=True)
        if args.dry_run:
            for title in todo:
                print(f"  would fetch {title}")
            print(f"\nWould cost {-(-len(todo) // TITLES_PER_REQUEST)} content request(s) "
                  f"at {TITLES_PER_REQUEST} titles each.", flush=True)
            return 0
        if not todo:
            print("Nothing to do.", flush=True)
            return 0

        fetched, missing = 0, []
        for start in range(0, len(todo), TITLES_PER_REQUEST):
            batch = todo[start:start + TITLES_PER_REQUEST]
            print(f"  requesting {len(batch)} page(s) "
                  f"[{start + 1}-{start + len(batch)} of {len(todo)}]", flush=True)
            data = client.get({
                "action": "query", "prop": "revisions", "titles": "|".join(batch),
                "rvslots": "main", "rvprop": "content|ids|timestamp",
                "redirects": "1", "format": "json", "formatversion": "2",
            })
            query = data.get("query", {})
            # redirects and normalized map what we asked for to what we got.
            # Liquipedia capitalises first letters, so this is not optional.
            for page in query.get("pages", []):
                title = page.get("title")
                if page.get("missing") or not page.get("revisions"):
                    missing.append(title)
                    print(f"    MISSING {title}", flush=True)
                    continue
                revision = page["revisions"][0]
                text = revision["slots"]["main"]["content"]
                destination = pages_dir / f"{safe_name(title)}.wiki.gz"
                body = text.encode("utf-8")
                write_atomic(destination, gzip.compress(body, compresslevel=9, mtime=0))
                manifest[title] = {
                    "file": destination.name,
                    "revision_id": revision.get("revid"),
                    "revision_timestamp": revision.get("timestamp"),
                    "fetched_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "source_url": f"https://liquipedia.net/deadlock/{urllib.parse.quote(title.replace(' ', '_'))}",
                    "bytes": len(body),
                }
                fetched += 1

        manifest_path.write_text(json.dumps({
            "schema_version": 1,
            "source": "https://liquipedia.net/deadlock/api.php",
            "license": "CC-BY-SA 3.0",
            "attribution": "Content from Liquipedia, https://liquipedia.net/deadlock/, CC-BY-SA 3.0",
            "user_agent": USER_AGENT,
            "pages": dict(sorted(manifest.items())),
        }, indent=2) + "\n", encoding="utf-8")

        print(f"\nDone. {fetched} page(s) cached, {len(missing)} missing, "
              f"{client.requests} HTTP request(s) total.", flush=True)
        for title in missing:
            print(f"  missing: {title}")
        return 1 if missing else 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
