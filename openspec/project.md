# Project Context

## Purpose
**undatum** is a powerful command-line tool for data processing and analysis. It provides a unified interface for converting, analyzing, validating, and transforming data across multiple formats (CSV, JSON Lines, BSON, XML, XLS, XLSX, Parquet, AVRO, ORC) with support for compression, automatic encoding detection, data validation, schema generation, and AI-powered documentation.

**Key Goals:**
- Low memory footprint through streaming data processing
- Support for large datasets with efficient format conversions
- Automatic detection of encoding, delimiters, and file types
- Built-in validation rules and custom validators
- AI-powered field and dataset documentation
- Comprehensive statistics and analysis capabilities

## Tech Stack

### Core Technologies
- **Python 3.10+** - Primary programming language
- **Typer** - CLI framework for command definitions
- **Rich** - Terminal output formatting and progress bars
- **Pydantic** - Data validation and settings management

### Data Processing
- **Pandas** - Data manipulation and analysis
- **DuckDB** - In-memory analytics database for statistics
- **iterabledata** - Streaming multi-format engine (140+ formats; lakehouse/open-data packs in 1.0.18+; prefer ≥1.0.18 on Python 3.10+)
- **orjson** - Fast JSON parsing

### Format Support
- **jsonlines** - JSON Lines format
- **xmltodict** - XML parsing
- **openpyxl/xlrd** - Excel file support
- **pymongo** - BSON format
- **pyorc** - ORC format
- **avro** - AVRO format
- **pandas** - Parquet support

### Compression
- **pyzstd** - ZSTD compression
- **py7zr** - 7Z/ZIP archives
- **lz4** - LZ4 compression
- Standard library: gzip, bz2, xz

### AI Integration
- **OpenAI API** - GPT models for documentation
- **OpenRouter** - Unified API for multiple LLM providers
- **Ollama** - Local model support
- **LM Studio** - Local OpenAI-compatible API
- **Perplexity** - Perplexity API support
- **requests** - HTTP client for API calls

### Development Tools
- **pytest** - Testing framework
- **ruff** - Linter and formatter (100 char line length; replaces black, flake8, pylint)
- **mypy** - Static type checking, enforced as a per-file ratchet (`mypy-baseline.json`)

### Utilities
- **click** - Legacy CLI support (being phased out)
- Encoding detection comes from iterabledata (`detect_encoding_raw`)
- **qddate** - Date field detection
- **validators** - Common validation rules
- **tabulate** - Table formatting
- **tqdm** - Progress bars

## Project Conventions

### Code Style

**Formatting:**
- **Line length**: 100 characters (configured in `pyproject.toml`)
- **Indentation**: 4 spaces (no tabs, except Makefile)
- **Encoding**: UTF-8 with `# -*- coding: utf8 -*-` header in all Python files
- **Line endings**: LF (Unix-style)
- **Trailing whitespace**: Trimmed
- **Final newline**: Required (except LICENSE file)

**Naming Conventions:**
- **Modules**: lowercase with underscores (e.g., `analyzer.py`, `textproc.py`)
- **Classes**: PascalCase (e.g., `Analyzer`, `Converter`, `StatProcessor`)
- **Functions**: snake_case (e.g., `convert_file`, `get_fields_info`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `DEFAULT_BATCH_SIZE`, `OBJECTS_ANALYZE_LIMIT`)

**Type Hints:**
- Use type hints for function parameters and return values
- `mypy` is configured but allows untyped definitions (`disallow_untyped_defs = false`)
- Use `typing` module for complex types (e.g., `Optional`, `Annotated`)
- Typer uses `Annotated` for CLI parameter definitions

**Docstrings:**
- Module-level docstrings describing purpose
- Function docstrings using triple quotes
- Focus on "what" and "why" rather than "how" (code is self-documenting)

**Import Organization:**
- Standard library imports first
- Third-party imports second
- Local imports last
- Use `ruff` with `isort` for import sorting
- Known first-party: `["undatum"]`

**Linting Rules:**
- **ruff**: E, W, F, I, B, C4, UP and PL rules (complexity limits ignored); D (Google
  docstrings) for `undatum/cmds/` and `undatum/sdk/`
- **mypy**: ratchet — errors per file may only go down; `undatum/common/` is strict

### Architecture Patterns

**Command-Based Architecture:**
- Each CLI command is implemented as a class in `undatum/cmds/`
- Commands inherit common patterns but are self-contained
- Core module (`core.py`) defines Typer app and routes to command classes
- Commands handle their own options parsing and execution

**Streaming-First Design:**
- Process data in chunks/streams to minimize memory usage
- Use iterators and generators for large datasets
- Batch processing with configurable batch sizes (default: 1000)

**Format Abstraction:**
- Format detection via `iterable.helpers.detect`
- Format-specific handlers in `undatum/formats/`
- Common iterable interface for reading/writing different formats

**AI Service Abstraction:**
- Provider-agnostic AI interface in `undatum/ai/`
- Support for multiple providers with consistent API
- Structured JSON output for reliable parsing
- Configuration via environment variables, config files, or CLI args

**Modular Validation:**
- Validation rules in `undatum/validate/`
- Common rules (email, URL) and domain-specific (Russian INN, OGRN)
- Extensible rule system

**Error Handling:**
- Graceful handling of keyboard interrupts
- Logging via standard `logging` module
- Verbose mode for debugging

### Testing Strategy

**Framework:**
- **pytest** - Primary testing framework
- Test files: `test_*.py` or `*_test.py` in `tests/` directory
- Test classes: `Test*`
- Test functions: `test_*`

**Coverage:**
- Use `pytest-cov` for coverage reporting
- Target comprehensive coverage of core functionality
- Coverage config in `pyproject.toml` (`[tool.coverage.*]`)

**Test Organization:**
- Tests mirror source structure in `tests/` directory
- Fixtures in `tests/fixtures/` for sample data files
- Benchmarks in `tests/benchmarks/` for performance testing

**Running Tests:**
```bash
pytest                    # Run all tests
pytest --cov=undatum      # With coverage
make test                 # Via Makefile
```

### Git Workflow

**Branching:**
- Main branch: `main` (or `master`)
- Feature branches: `feature/description`
- Bug fixes: `fix/description`

**Commit Conventions:**
- Clear, descriptive commit messages
- Reference issues when applicable
- Follow conventional commit format when possible

**Pre-commit Hooks:**
- `pre-commit` support available via Makefile
- Run `make pre-commit-install` to set up hooks
- Hooks enforce formatting and linting before commits

## Domain Context

**Data Processing Domain:**
- **Formats**: CSV, JSON Lines (JSONL), BSON, XML, Excel (XLS/XLSX), Parquet, AVRO, ORC
- **Compression**: ZIP, GZ, BZ2, XZ, ZSTD, 7Z
- **Encoding**: Automatic detection with manual override (UTF-8, CP1251, etc.)
- **Delimiters**: Auto-detect comma, semicolon, tab for CSV

**Key Concepts:**
- **Streaming**: Process data line-by-line or chunk-by-chunk to handle large files
- **Schema Detection**: Automatic inference of field types and structures
- **Table Detection**: Identify tabular structures in nested JSON/XML
- **Date Detection**: Automatic identification of date/datetime fields using `qddate`
- **Validation Rules**: Built-in and custom validators for data quality
- **AI Documentation**: Generate field descriptions and dataset summaries using LLMs

**Command Categories:**
- **Conversion**: `convert` - Transform between formats
- **Analysis**: `analyze`, `stats`, `headers` - Data insights
- **Validation**: `validate` - Data quality checks
- **Querying**: `query`, `select`, `uniq`, `frequency` - Data extraction
- **Schema**: `schema` - Schema generation
- **Transformation**: `flatten`, `apply`, `split` - Data manipulation

## Important Constraints

**Technical Constraints:**
- **Python 3.10+** required; versions are dropped in the first minor release after their end of life
- **Memory efficiency**: Must handle large files without loading entire dataset into memory
- **Streaming**: All operations should support streaming for scalability
- **Format compatibility**: Support for legacy formats (XLS, older Excel) via xlrd
- **Encoding**: Must handle various encodings, especially for international data (CP1251, etc.)

**Performance Constraints:**
- **Batch processing**: Use configurable batch sizes for operations
- **AI calls**: Batch field descriptions per-table to minimize API calls
- **Compression**: Support reading from compressed files without full decompression

**API Constraints:**
- **AI Providers**: Must gracefully handle provider failures and fallbacks
- **Structured Output**: All AI providers should use JSON Schema for reliable parsing
- **Rate Limiting**: Consider API rate limits when making multiple AI calls

**Backward Compatibility:**
- Maintain CLI interface stability
- Support legacy command names (`convertold` exists for compatibility)
- Handle format detection edge cases gracefully

## External Dependencies

**External Services:**
- **OpenAI API** - Requires `OPENAI_API_KEY` environment variable
- **OpenRouter API** - Requires `OPENROUTER_API_KEY` environment variable
- **Perplexity API** - Requires `PERPLEXITY_API_KEY` environment variable
- **Ollama** - Local service, requires Ollama to be installed and running (default: `http://localhost:11434`)
- **LM Studio** - Local service, requires LM Studio server running (default: `http://localhost:1234/v1`)

**Configuration:**
- **Config files**: `undatum.yaml` in project root or `~/.undatum/config.yaml` for global settings
- **CLI defaults**: optional `defaults:` mapping (`engine`, `threads`, `progress`, `encoding`, `delimiter`, `format_out`)
- **Environment variables**: Provider-specific API keys and base URLs; `UNDATUM_ENGINE`, `UNDATUM_THREADS`, `UNDATUM_PROGRESS`, `UNDATUM_ENCODING`, `UNDATUM_DELIMITER`, `UNDATUM_FORMAT_OUT`
- **CLI arguments**: Highest precedence for configuration

**Data Sources:**
- File-based input/output (primary)
- Database connections for `ingest`, `db query`, and `db load` (MongoDB, PostgreSQL, DuckDB, MySQL, SQLite, Elasticsearch)
- Object storage via `s3://`, `gs://`/`gcs://`, and `az://`/`abfs://`/`abfss://` URIs (optional `s3`, `gcs`, `azure`, or `cloud` extras)
- Support for compressed archives (ZIP, 7Z)
- Network filesystems supported (no special handling required)

**Optional Dependencies:**
- Some format support may require additional packages (handled via conditional imports where possible)
- AI features are optional and gracefully degrade if providers unavailable
