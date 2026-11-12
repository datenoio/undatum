# Change: Return Non-Zero Exit Codes for Every Failure

## Why
Several failures end with exit code 0, so scripts and CI treat them as success:
- `sample` without `--n`/`--percent` logs an ERROR and returns (`undatum/cmds/sampler.py:59,121`);
- an unknown `--engine` value (e.g. `duckbd`) silently falls back to the iterable engine
  (`undatum/common/engine_selector.py:52-58`); 23 commands accept free-text `--engine`;
- Ctrl-C exits with 0 (`undatum/__main__.py:27`) instead of the conventional 130;
- `undatum/cmds/` has 27 `logging.error(...)` call sites, several followed by a bare `return`.
This contradicts the `error-handling` spec (UndatumError hierarchy, categorized exit codes).

## What Changes
- Replace log-and-return error paths in `undatum/cmds/` with `UndatumError` subclasses.
- Validate `--engine` against `auto`, `duckdb`, `python` (accept `iterable` as an alias of
  `python`) in one shared helper used by all 23 commands.
- Exit with 130 on `KeyboardInterrupt`, printing "Interrupted" to stderr.
- Document the exit-code table (0, 1, 2, 3, 4, 130) in the man page and troubleshooting page;
  invalid command-line usage (unknown option, bad `--engine` value) exits with 2 as in Click.
- Add CLI tests that assert exit codes for each error category.

## Impact
- Affected specs: `error-handling`
- Affected code: `undatum/__main__.py`, `undatum/common/engine_selector.py`,
  `undatum/cmds/sampler.py` and other modules with log-and-return paths,
  `docs/docs/getting-started/troubleshooting.md`, `man/undatum.1`
- Related: review defects #3 and #7
