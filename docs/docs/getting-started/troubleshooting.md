---
title: "Troubleshooting"
description: "Exit codes, common errors, and AI provider issues"
---
# Troubleshooting

This guide explains how undatum handles errors and provides troubleshooting tips for common issues.

## Overview

undatum provides user-friendly error messages instead of raw Python tracebacks. All errors are categorized and include actionable guidance to help you resolve issues quickly.

## Error Categories

### Exit Code 1: User Errors
Errors caused by invalid input or user mistakes:
- File not found
- Invalid file format
- Missing required parameters
- Invalid field names
- Query syntax errors

### Exit Code 2: Configuration Errors
Errors related to configuration or dependencies:
- Missing optional dependencies
- Invalid configuration files
- Missing environment variables

### Exit Code 3: System Errors
Errors related to system resources or permissions:
- Permission denied
- Database connection errors
- Network errors

### Exit Code 4: Internal Errors
Unexpected errors that may indicate a bug:
- Unhandled exceptions
- Internal processing errors

### Exit Code 130: Interrupted
The command was stopped with Ctrl-C (SIGINT). Output files are written to a temporary
name and renamed only on success, so an interrupted command leaves no partial output.

### Summary

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | User error: missing file, invalid parameter, unsupported or non-writable format |
| 2 | Invalid command-line usage (unknown option, bad choice), configuration error, or missing optional dependency (install the named extra) |
| 3 | System error: permission denied, database or network failure |
| 4 | Internal error (please report it with the `--verbose` output) |
| 130 | Interrupted with Ctrl-C |

A command never exits with 0 after reporting an error, so scripts can rely on `$?`.

## Common Error Messages

### File Not Found

**Error:**
```
Error: File not found: '/path/to/data.csv'
Did you mean: '/path/to/data2.csv'?
Check that the file path is correct and the file exists.
```

**Solutions:**
1. Verify the file path is correct
2. Check for typos in the filename
3. Use absolute paths if relative paths don't work
4. Ensure the file exists in the specified location

**Example:**
```bash norun
# Wrong
undatum convert data.cvs output.jsonl

# Correct (if typo detected, undatum suggests the correct file)
undatum convert data.csv output.jsonl
```

### Permission Denied

**Error:**
```
Error: Permission denied: Cannot read '/path/to/data.csv'
Fix: chmod +r /path/to/data.csv
Or check file ownership and permissions.
```

**Solutions:**
1. Check file permissions: `ls -l /path/to/data.csv`
2. Add read permission: `chmod +r /path/to/data.csv`
3. Add write permission (for output files): `chmod +w /path/to/output.csv`
4. Check file ownership if you don't have permission to modify

**Example:**
```bash
# Fix read permission
chmod +r data.csv
undatum convert data.csv output.jsonl

# Fix write permission for output
chmod +w output.jsonl
```

### Unsupported File Format

**Error:**
```
Error: Unsupported file format: 'xyz'
Supported formats: csv, jsonl, parquet, avro, orc, xml, xls, xlsx, bson
Use 'undatum convert' to convert to a supported format.
```

**Solutions:**
1. Convert the file to a supported format first
2. Check the file extension matches the actual format
3. Use `--format-in` to explicitly specify the format

**Example:**
```bash norun
# Convert unsupported format to CSV first
undatum convert input.xyz output.csv --format-in csv
```

### Missing Required Parameter

**Error:**
```
Error: Invalid input: Missing required parameter 'fields'
The 'fields' option is required for this operation.
```

**Solutions:**
1. Check command documentation: `undatum <command> --help`
2. Provide all required parameters
3. Verify parameter names are correct

**Example:**
```bash norun
# Wrong - missing --fields
undatum select data.csv

# Correct
undatum select data.csv --fields name,email
```

### Invalid Field Name

**Error:**
```
Error: Invalid parameter 'field_name': Field does not exist
Did you mean: 'field_name2'?
Valid options: field1, field2, field3
```

**Solutions:**
1. Check available fields: `undatum headers data.csv`
2. Use the suggested field name if a typo is detected
3. Verify field names match exactly (case-sensitive)

**Example:**
```bash
# Check available fields first
undatum headers data.csv

# Use correct field name
undatum select data.csv --fields email,phone
```

### Missing Dependency

**Error:**
```
Error: Missing dependency: 'package_name'
This feature requires 'package_name'. Install it with:
  pip install package_name
```

**Solutions:**
1. Install the required dependency
2. Use the suggested installation command
3. For optional features, install extras: `pip install undatum[api]`

**Example:**
```bash
# Install missing dependency
pip install pyyaml

# Or install with extras
pip install "undatum[api]"
```

### Database Connection Error

**Error:**
```
Error: Database error: Connection failed
postgresql error: Could not connect to database
Check connection URI and database server status.
```

**Solutions:**
1. Verify the database server is running
2. Check connection URI format
3. Verify credentials are correct
4. Check network connectivity
5. Ensure database exists

**Example:**
```bash norun
# Connection string format: scheme://user:password@host:port/database
undatum db load data.csv --db "postgresql://user:password@host:5432/dbname" --table users
```

## Verbose Mode

For detailed error information including full tracebacks, use the `--verbose` flag:

```bash
undatum convert data.csv output.jsonl --verbose
```

This is useful for:
- Debugging internal errors
- Reporting bugs
- Understanding the full error context

## Error Message Features

### Typo Detection

undatum automatically detects typos in file paths and field names:

```bash norun
# Typo in filename - undatum suggests corrections
undatum convert data.cvs output.jsonl
# Error: File not found: 'data.cvs'
# Did you mean: 'data.csv'?
```

### Actionable Guidance

All error messages include specific steps to resolve the issue:

- Permission errors include `chmod` commands
- Format errors list supported formats
- Dependency errors include installation commands
- Field errors suggest valid alternatives

### Consistent Formatting

All errors follow a consistent format:
```
Error: <Error type>: <Description>
<Actionable guidance>
```

## Troubleshooting Tips

### 1. Check File Paths
Always verify file paths are correct:
```bash
ls -la /path/to/file.csv
```

### 2. Verify Permissions
Check file permissions before running commands:
```bash
ls -l data.csv
chmod +r data.csv  # If needed
```

### 3. Use Verbose Mode
For detailed error information:
```bash
undatum <command> --verbose
```

### 4. Check Command Syntax
Review command help for correct usage:
```bash
undatum <command> --help
```

### 5. Verify Dependencies
Install required dependencies:
```bash
pip install undatum[api]  # For API features
pip install pyyaml         # For YAML support
```

## Reporting Errors

When reporting errors, include:
1. Full error message (use `--verbose` flag)
2. Command that caused the error
3. Input file format and size
4. Python version: `python --version`
5. undatum version: `undatum --version`

## Error Handling in Scripts

When using undatum in scripts, check exit codes:

```bash norun
#!/bin/bash
if undatum convert data.csv output.jsonl; then
    echo "Conversion successful"
else
    exit_code=$?
    case $exit_code in
        1) echo "User error - check input" ;;
        2) echo "Configuration error - check dependencies" ;;
        3) echo "System error - check permissions" ;;
        4) echo "Internal error - report bug" ;;
    esac
    exit $exit_code
fi
```

## Best Practices

1. **Validate inputs early**: Check file existence and permissions before processing
2. **Use absolute paths**: Avoid path resolution issues
3. **Check dependencies**: Install required packages before use
4. **Read error messages**: They contain actionable guidance
5. **Use verbose mode**: For debugging and bug reports

## Related Documentation

- [Installation](/getting-started/installation) - Install and extras
- [Quick start](/getting-started/quick-start) - First commands
- [Developer Error Handling Patterns](/development/error-handling) - For contributors


## AI provider troubleshooting

### Common Issues

**Provider not found:**
```bash
# Error: No AI provider specified
# Solution: Set environment variable or use --ai-provider
export UNDATUM_AI_PROVIDER=openai
# or
undatum analyze data.csv --autodoc --ai-provider openai
```

**API key not found:**
```bash
# Error: API key is required
# Solution: Set provider-specific API key
export OPENAI_API_KEY=sk-...
export OPENROUTER_API_KEY=sk-or-...
export PERPLEXITY_API_KEY=pplx-...
# ai doc / ai filter (iterabledata) may also use:
export ANTHROPIC_API_KEY=sk-ant-...
export GEMINI_API_KEY=...
export AZURE_OPENAI_API_KEY=...
```

**Ollama connection failed:**
```bash norun
# Error: Connection refused
# Solution: Ensure Ollama is running and model is pulled
ollama serve
ollama pull llama3.2
# Or specify custom URL
export OLLAMA_BASE_URL=http://localhost:11434
```

**LM Studio connection failed:**
```bash norun
# Error: Connection refused
# Solution: Start LM Studio server and load a model
# In LM Studio: Start Server, then:
export LMSTUDIO_BASE_URL=http://localhost:1234/v1
```

**Structured output errors:**
- `--autodoc` asks the model for JSON and reads the first JSON object in the answer (code fences are fine)
- If a model answers with prose only, the dataset description uses the raw text, and field descriptions or metadata are skipped with a warning
- Small local models follow JSON instructions less reliably; try a larger model if this happens often

### Provider-Specific Notes

**`--autodoc`** (`analyze`, `schema`, `schema-bulk`, `doc`, `package create`) and `ai *` use the same providers.

**`ai *` subcommands** (iterabledata):

- **OpenAI**: Requires API key; models include `gpt-4o-mini`, `gpt-4o`, `gpt-3.5-turbo`
- **Anthropic**: Requires `ANTHROPIC_API_KEY`; models include Claude 3.5/3 Haiku and Sonnet families
- **Gemini**: Requires `GEMINI_API_KEY`; models include `gemini-2.0-flash` and Pro variants
- **Azure OpenAI**: Requires `AZURE_OPENAI_API_KEY` and `AZURE_OPENAI_ENDPOINT`
- **OpenRouter**: Unified API for hosted models from OpenAI, Anthropic, Google, Meta, and others
- **Ollama**: Local models, no API key; requires Ollama installed and running
- **LM Studio**: Local models via OpenAI-compatible API; requires LM Studio server running
- **Perplexity**: Requires API key; uses `sonar` model by default
