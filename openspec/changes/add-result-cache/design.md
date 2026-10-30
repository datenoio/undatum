## Context
Decided with the maintainer:
- the cache lives in `~/.undatum/cache`;
- it is on by default, with `--no-cache` to skip it;
- validity is size plus modification time;
- the first version caches command results.

The six commands compute one object and render it afterwards:

| Command | Object |
|---|---|
| `count` | `int` |
| `headers` | `list` |
| `sniff` | `dict` |
| `schema` | `TableSchema` |
| `analyze` | `ReportSchema` |
| `stats` | profile `dict` |

A cache at that boundary serves text, YAML and JSON output alike.

## Goals / Non-Goals
- Goals:
  - The same output with and without a cached result.
  - No result for a changed file.
  - No effect on reading the data, or on commands that cannot be cached.
- Non-Goals:
  - Content hashes.
  - A cache shared between users or machines, or kept beside the data.
  - Caching remote files.
  - Row-offset indexes.

## Decisions
- **Layout:**
  - `~/.undatum/cache/<file key>/source.json` records the path, size and mtime.
  - `~/.undatum/cache/<file key>/<command>-<options key>.json` holds one result.
  - The file key is SHA-256 of the real path, size and `st_mtime_ns`.
  - The options key is SHA-256 of the command, undatum version and options, minus those that
    only change presentation or speed (output, format, progress, threads, DuckDB limits, cache).
  - The engine stays in the key.
  - Writes are atomic (temporary file and `os.replace`); a race between two runs loses one entry
    at most.
- **Stored form:** results are stored as JSON (`normalize_for_json`), and each command loads them
  back into its object. Tests compare the output of a cached run with an uncached one for every
  format.
- **`stats` text output:** the engines print the text table while they compute. Under the cache,
  `stats` computes quietly and prints the table from the profile, on a hit or a miss.
- **Enabling:** the CLI passes `cache` from `--cache/--no-cache`. When the flag is not given,
  `UNDATUM_CACHE` or the config `defaults: cache` decide, and otherwise it is on. Library calls
  have no `cache` option, so they read the config and environment and are off by default.
- **Failure handling:** an unreadable or corrupt entry is ignored and recomputed. A cache that
  cannot be written (read-only home) logs at debug level. Neither changes the command's result
  or exit code.

## Risks / Trade-offs
- **An edit that keeps size and mtime is missed.** This happens only with tools that restore
  mtime; `--no-cache` and `cache clear` cover it.
- **Entries of changed files stay until `cache clear --stale`.** Results are small (KB, a few MB
  for wide `stats` profiles).
