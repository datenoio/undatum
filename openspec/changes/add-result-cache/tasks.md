## 1. Cache
- [x] 1.1 `undatum/common/cache.py`: keys, lookup, atomic store, listing, clearing
- [x] 1.2 `cache` config key (`UNDATUM_CACHE`, `defaults: cache`) and `--cache/--no-cache`

## 2. Commands
- [x] 2.1 `stats`, `schema`, `sniff`, `analyze`, `headers`, `count` read and store results
- [x] 2.2 `undatum cache list [--json]` (`undatum.cache/1`) and `undatum cache clear [--stale]`

## 3. Tests and documentation
- [x] 3.1 Cached output equals uncached output in every format; changed files and options miss
- [x] 3.2 Cache page, command pages, configuration, CHANGELOG
