# Change: Cache Command Results for Unchanged Files

## Why
Profiling a file is slow and is often repeated. On 1M rows (140 MB CSV), measured with `--json`:

| Command | CSV | JSON Lines | Parquet |
|---|---|---|---|
| `stats` | 11.1 s | 9.9 s | 4.2 s |
| `sniff` | 3.6 s | 3.3 s | 2.7 s |
| `schema` | 3.2 s | 1.7 s | 1.6 s |
| `analyze` | 3.4 s | 3.0 s | 3.2 s |

People rerun these commands while they explore a file, and agents call them again and again. Tools
like qsv keep statistics and indexes beside the data. Item 19 of the October 2026 engine review
(`analysis/2026-10-28-undatum-engines-and-competitors.md`, section 6.3) proposes a cache keyed by
the file.

## What Changes
- **Cached commands:** `stats`, `schema`, `sniff`, `analyze`, `headers` and `count` keep their
  result for a local file in `~/.undatum/cache`. A later run on the unchanged file with the same
  options reads the result instead of the data, and prints the same output in every format.
- **When a result is reused:** a result belongs to the file's real path, size and modification time
  (nanoseconds), the undatum version and the options that change it. A changed file gets new
  entries. A file that changes while it is read is not cached.
- **On by default in the CLI:** `--no-cache` skips the cache for one run, and `UNDATUM_CACHE=0` or
  `defaults: cache: false` in a config file turns it off. SDK and MCP calls use it only when
  they pass `cache=True`.
- **Commands:** `undatum cache list [--json]` shows the cached files, results and sizes;
  `undatum cache clear [--stale]` removes all entries, or those whose file is gone or changed.
- **Not cached:** stdin, URIs, directories and outputs other than these six commands. A row-offset
  index for `slice`/`tail` is a later step.

## Impact
- Affected specs: `data-processing`.
- Affected code: `undatum/common/cache.py` (new), `undatum/cli/cache_cli.py` (new), the six
  command handlers and their CLI options, `undatum/common/app_config.py`,
  `undatum/common/results.py`, tests and documentation.
