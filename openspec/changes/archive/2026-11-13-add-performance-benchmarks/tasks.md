## 1. Harness
- [x] 1.1 Dataset generator script with fixed seeds (100k and 1M rows; CSV, JSONL, Parquet)
      (values derived from the row number instead of a seed: same bytes on every run)
- [x] 1.2 Subprocess runner that records wall time and peak RSS
- [x] 1.3 `budgets.toml` with per-command budgets

## 2. CI
- [x] 2.1 PR job (100k tier) comparing against the `master` baseline (fail on > 20%)
      (`.github/workflows/benchmarks.yml`; first run happens on the next pull request)
- [x] 2.2 Nightly job (1M tier) publishing JSON results and a history chart
      (artifact + `benchmark-history` branch; `deploy-docs.yml` redraws the chart)

## 3. Findings
- [x] 3.1 Make `count` use DuckDB or format totals; add a budget so it stays faster than `sort`
- [x] 3.2 Other findings: `stats` date detection (6x faster), output-format lookup without
      iterabledata, `sort` DuckDB quoting; open: `sort`/`convert` peak memory on 1M rows
