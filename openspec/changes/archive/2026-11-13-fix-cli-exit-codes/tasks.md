## 1. Implementation
- [x] 1.1 `sampler.py`: raise `ValidationError` when neither `--n` nor `--percent` is given
- [x] 1.2 Audit all `logging.error` call sites in `undatum/cmds/` and convert terminal ones into
      raised `UndatumError` subclasses
- [x] 1.3 Add `validate_engine()` in `undatum/common/engine_selector.py`; call it from
      `detect_engine` and reject unknown values with the list of accepted values
- [x] 1.4 `__main__.py`: exit 130 on `KeyboardInterrupt`
- [x] 1.5 Review the 12 `except Exception: pass` blocks; narrow or log at debug with rationale
- [x] 1.6 Audit the remaining broad `except Exception` blocks (182 in total) in command paths;
      convert to specific exceptions or wrap in `UndatumError` with the original as cause
      (audit 2026-10-07: 47 re-raise, 101 log a DuckDB→Python fallback or cleanup, 18 return a
      tool error or a capability-probe default, 21 are cleanup/probe helpers; no command path
      hides a failure any more)

## 2. Documentation
- [x] 2.1 Add the exit-code table to the troubleshooting page and regenerate `man/undatum.1`

## 3. Tests
- [x] 3.1 CliRunner tests: missing required option → 1; unknown engine → 1; missing extra → 2;
      permission denied → 3; simulated KeyboardInterrupt → 130
