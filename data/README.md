# data/

Everything the project knows that is not in the browser. The point of this
directory is that nothing important lives only in localStorage any more.

## Layout

| Path | What it holds | Who writes it |
| --- | --- | --- |
| `matches/` | Match metadata, one `<match_id>.json.gz` per match, decompressing to exactly what the API returned | `scripts/fetch_matches.py` |
| `match-ids/` | Hand-collected match ID lists, with edition names as comments | You, by hand |
| `artifacts/` | CSV exports and localStorage dumps that exist nowhere else | `scripts/import_artifact.py` |
| `artifacts/MANIFEST.json` | Provenance and SHA-256 for every artifact | `scripts/import_artifact.py` |

## Rules

**`matches/` is a write-once cache.** If a file exists, the fetch script will
never request that match again. This is deliberate: the API is community run
and unofficial, and a match that is fetched once should not depend on that
service still being up, or still returning the same shape, months later. Use
`--force` only if you have a specific reason to believe a response changed.

**Files here are raw.** No reformatting, no pretty printing, no key filtering.
Whatever transformation a later step needs happens downstream, into a separate
derived dataset. That keeps it possible to rebuild everything from source if a
processing bug is found later.

**Gzip is storage only, not a schema.** Each file decompresses to exactly the
bytes the API returned. Raw is about 1.12 MB per match, which is roughly
0.68 GB a year and grows forever in git history; gzipped it is about 20% of
that. The fetch script decompresses and compares against the response before
it accepts a write, so a file that does not round trip is never cached.

### Reading a cached match

Print one match to the terminal:

    python -c "import gzip,sys; sys.stdout.buffer.write(gzip.open('data/matches/95172627.json.gz','rb').read())"

Or with the gzip command line tool, which is on the PATH in Git Bash:

    gzip -dc data/matches/95172627.json.gz

Write one back out as a plain readable file:

    gzip -dc data/matches/95172627.json.gz > 95172627.json

Pretty print a match to skim its shape:

    python -c "import gzip,json; print(json.dumps(json.load(gzip.open('data/matches/95172627.json.gz')), indent=2)[:2000])"

In Python, the helper in the fetch script returns the original bytes for any
cached match, compressed or not:

    from scripts.fetch_matches import read_cached
    body = read_cached(Path("data/matches/95172627.json.gz"))

**`artifacts/` is immutable.** Files are copied byte for byte and are never
rewritten, reformatted, or migrated, even once a newer schema supersedes them.
A superseded export is still the record of what was true at the time, and in
several cases it is the only surviving copy of hand-curated work. The manifest
records a SHA-256 for each one so silent corruption is detectable.

## Usage

Fetch every match in a list, skipping anything already cached:

    python scripts/fetch_matches.py data/match-ids/night-shift.txt

Preview without touching the network:

    python scripts/fetch_matches.py --dry-run data/match-ids/night-shift.txt

Preserve an export or a localStorage dump:

    python scripts/import_artifact.py --label night-shift-49 --note "leaderboard CSV after edition 49" export.csv
