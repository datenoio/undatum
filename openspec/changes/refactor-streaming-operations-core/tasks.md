## 1. Foundations
- [x] 1.1 Create `undatum/io/` with `open_source`/`open_sink` (files, stdin/stdout, cloud, atomic
      writes)
- [x] 1.2 Create `undatum/ops/` with the `Operation` base, registry and streaming classes
- [x] 1.3 Engine selection based on source capabilities and operation `to_sql`

## 2. Pilot operations
- [x] 2.1 Migrate `rename`, `fill`, `replace`, `search`, `head` (Python + SQL paths)
- [x] 2.2 Dual-engine contract tests comparing outputs

## 3. Full migration
- [x] 3.1 Migrate the remaining row operations (`enum`, `explode`, `exclude`, `fixlengths`, `fmt`,
      `cat`, `join`, `select`, `dedup`, `tail`, `sample`, `slice`) — `join`, `select` and `sample`
      keep their own engine code but stream their output (`write_query`/`write_rows`); `fmt`
      streams in two passes
- [x] 3.2 FULL operations with disk spill: `reverse`, `transpose`, Python `sort`
- [x] 3.3 Remove the collect-and-normalize blocks and `DataWriter`

## 4. Cloud and upstream
- [x] 4.1 Stream `s3://` reads through fsspec; keep region/profile options
- [ ] 4.2 Upstream file-object writers, `codecargs` in `iterable.convert` and stdin reading to
      iterabledata; remove the monkeypatch in `converter.py` (also upstream: keep the codec when
      an explicit `format` is passed; undatum works around it in `_codec_safe_source`)
- [x] 4.3 Bound `iterabledata>=1.0.21,<1.1`

## 5. Verification
- [x] 5.1 Memory budget tests: 1M-row CSV, row operations ≤ 300 MB peak RSS
- [x] 5.2 Update per-command capability metadata used by docs (`update-project-documentation`)
