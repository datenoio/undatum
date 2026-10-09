# Contributing to undatum

Thank you for your interest in contributing to undatum! This document provides guidelines and instructions for contributing.

## Development Setup

### Prerequisites

- Python 3.10 or higher (we support CPython versions that have not reached end of life)
- Git
- pip

### Installation

1. Clone the repository:
```bash
git clone https://github.com/datenoio/undatum.git
cd undatum
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install development dependencies:

```bash
make install-dev
# or
pip install -e ".[dev]"
```

The `dev` extra pins the tool versions used by CI (ruff, mypy) and installs pytest and
pre-commit. Python 3.10 is the minimum supported version; use it for type checking.

## Code Style

All checks run with `make check-all` (format check, lint, type check, tests).

### Formatting

`ruff format` formats the code (line length 100):

```bash
make format          # ruff format undatum/ tests/ scripts/
make format-check    # what CI runs
```

### Linting

`ruff check` is the only linter. Besides pycodestyle, pyflakes, isort, bugbear,
comprehensions and pyupgrade, it applies a selection of pylint rules (`PL`) and Google-style
docstring rules (`D`) for `undatum/cmds/` and `undatum/sdk/`:

```bash
make lint            # ruff check + dependency bound check
```

Every runtime dependency and extra in `pyproject.toml` needs a lower and an upper version
bound (`scripts/check_dependency_bounds.py`); the "lowest direct dependencies" CI job tests
the lower bounds.

### Type Checking

mypy runs as a ratchet: `mypy-baseline.json` records the number of errors per file, and CI
fails when a file gets more errors than recorded. `undatum/common/` is fully annotated and
checked with `disallow_untyped_defs`.

```bash
make type-check      # python scripts/mypy_ratchet.py
make type-baseline   # after fixing errors: lock in the lower counts
```

### Pre-commit Hooks

Install pre-commit hooks to run ruff before every commit:

```bash
pre-commit install
```

## Documentation

### Docstring Style

We use Google-style docstrings for consistency. Example:

```python
def example_function(param1: str, param2: int = 10) -> bool:
    """Brief description of the function.

    Longer description explaining what the function does, any important
    details about its behavior, and any relevant context.

    Args:
        param1: Description of param1.
        param2: Description of param2 (default: 10).

    Returns:
        Description of return value.

    Raises:
        ValueError: When param1 is invalid.

    Example:
        >>> result = example_function("test", 20)
        >>> print(result)
        True
    """
    pass
```

### Documentation site

User-facing docs are a Docusaurus site in `docs/` (content in `docs/docs/`).

```bash
cd docs
npm install
npm start          # local preview
npm run build      # production build (also `make docs`)
```

See `docs/README.md` and `docs/GITHUB_PAGES_SETUP.md`. The published site is
https://datenoio.github.io/undatum/.

## Testing

### Running Tests

Run all tests:
```bash
pytest
```

Run with coverage:
```bash
pytest --cov=undatum --cov-report=html
```

### Writing Tests

- Place tests in the `tests/` directory
- Test files should be named `test_*.py`
- Use descriptive test function names: `test_function_name_scenario`

## Pull Request Process

1. **Create a branch**: Create a feature branch from `master`
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make changes**: Make your changes following the code style guidelines

3. **Run checks**: Ensure all checks pass:
   ```bash
   make check-all   # ruff format check, ruff lint, mypy ratchet, pytest
   ```

4. **Commit**: Write clear commit messages following conventional commits:
   ```
   feat: add new feature
   fix: fix bug in converter
   docs: update README
   refactor: improve performance
   ```

5. **Push**: Push your branch and create a pull request

6. **Review**: Address any feedback from reviewers

## Code Review Guidelines

- All code must be reviewed before merging
- Ensure tests pass and coverage is maintained
- Follow the existing code style
- Add documentation for new features
- Update CHANGELOG.md for user-facing changes

## Reporting Issues

When reporting issues, please include:

- Description of the issue
- Steps to reproduce
- Expected behavior
- Actual behavior
- Python version
- undatum version
- Relevant error messages or logs

## Questions?

Feel free to open an issue for questions or reach out to the maintainers.

## Community

- Prefer **GitHub Discussions** for Q&A and ideas; use Issues for bugs and
  actionable feature requests. See `docs/docs/development/community.md`.
- Look for the `good first issue` label when getting started.
- External contributors are welcome — undatum has persistent usage but historically few PRs;
  small focused patches (tests, docs, install fixes) are especially helpful.
- Dependency-bot PRs should be auto-merged for patch-level security bumps or closed promptly
  rather than left unattended.

## Release discipline (CLI stability)

- Follow semver for user-facing CLI changes.
- Call out breaking command/flag changes loudly in `CHANGELOG.md`.
- Prefer deprecation warnings before removing flags that agents or scripts may depend on.
- Keep a stable-command guarantee for core verbs (`convert`, `stats`, `validate`, `select`)
  whenever possible.
