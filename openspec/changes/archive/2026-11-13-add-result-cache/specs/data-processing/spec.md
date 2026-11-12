## ADDED Requirements

### Requirement: Cached Command Results
`stats`, `schema`, `sniff`, `analyze`, `headers` and `count` SHALL store their result for a local
file in `~/.undatum/cache` and reuse it on a later run with the same file and options.
- A result SHALL be reused only when the file's real path, size and modification time, the
  undatum version and the options that change the result are the same.
- The output of a run that reuses a result SHALL equal the output of a run that computes it.
- The CLI SHALL use the cache unless `--no-cache`, `UNDATUM_CACHE=0` or the config
  `defaults: cache: false` turns it off.
- Library calls SHALL use it only when asked.
- A cache that cannot be read or written SHALL NOT change a command's result or exit code.

#### Scenario: Second run reads the cached result
- **WHEN** a user runs `undatum stats data.csv --json` twice and the file is unchanged
- **THEN** the second run prints the same document without reading the data

#### Scenario: Changed file is read again
- **WHEN** `data.csv` changes between two runs of `undatum stats data.csv`
- **THEN** the second run reads the file and prints its new statistics

### Requirement: Cache Management
`undatum cache list` SHALL list the cached files with their results and sizes (`--json`:
`undatum.cache/1`). `undatum cache clear` SHALL remove all entries, and `--stale` only those whose
file is missing or changed.

#### Scenario: Clearing stale entries
- **WHEN** a cached file is deleted and the user runs `undatum cache clear --stale`
- **THEN** its entries are removed and the entries of unchanged files stay
