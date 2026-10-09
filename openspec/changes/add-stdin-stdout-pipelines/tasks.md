## 1. Input
- [x] 1.1 Resolve `-`/omitted input to a stdin source in the shared input helper
- [x] 1.2 Format sniffing for stdin with `--format-in` override; codec detection by magic bytes
- [x] 1.3 Stdin support in iterabledata or a spooled temp buffer for formats that need seeking

## 2. Output
- [x] 2.1 Stdout format follows input text format; `--format-out` override
- [x] 2.2 Refuse binary formats to a TTY; require explicit `--format-out` for binary stdout
- [x] 2.3 Disable progress output when stdout is not a TTY; handle `BrokenPipeError`

## 3. Tests and docs
- [x] 3.1 Pipeline tests: `cat x.csv | undatum sort - --by a | undatum head - -n 3`
- [x] 3.2 Document pipelines in basic usage and cookbook; CHANGELOG note on stdout format
