---
title: "Error handling patterns"
description: "UndatumError hierarchy and patterns for contributors"
---
# Error handling patterns

This document describes error handling patterns used in undatum for contributors and maintainers.

## Overview

All commands should use the centralized error handling infrastructure in `undatum/common/errors.py` to provide consistent, user-friendly error messages.

## Error Handling Infrastructure

### Custom Exception Classes

All custom exceptions inherit from `UndatumError`:

```python
from undatum.common.errors import (
    FileNotFoundError,
    PermissionError,
    ValidationError,
    FormatError,
    DependencyError,
    DatabaseError,
    ConfigurationError,
)
```

### Exception Hierarchy

```
UndatumError (base)
├── FileNotFoundError
├── PermissionError
├── ValidationError
├── FormatError
├── ConfigurationError
├── DependencyError
└── DatabaseError
```

## Common Patterns

### 1. File Path Validation

Always validate file paths before processing:

```python
from undatum.common.path_utils import validate_file_path
from undatum.common.errors import FileNotFoundError, PermissionError, find_similar_files

def my_command(fromfile, options=None):
    # Validate input file exists and is readable
    try:
        validate_file_path(fromfile, check_read=True)
    except FileNotFoundError as e:
        suggestions = find_similar_files(fromfile)
        raise FileNotFoundError(fromfile, suggestions) from e
    except PermissionError as e:
        raise PermissionError(fromfile, operation="read") from e
```

### 2. Output File Validation

For output files, check write permissions:

```python
from undatum.common.path_utils import validate_file_path
from undatum.common.errors import PermissionError

def my_command(fromfile, tofile, options=None):
    # Validate output file can be written
    try:
        validate_file_path(tofile, check_write=True)
    except PermissionError as e:
        raise PermissionError(tofile, operation="write") from e
```

### 3. Field Validation

Validate field names with suggestions:

```python
from undatum.common.errors import ValidationError, find_similar_field_names

def my_command(fromfile, options=None):
    fields = options.get('fields')
    if not fields:
        raise ValidationError(
            "Missing required parameter 'fields'",
            field="fields"
        )
    
    available_fields = get_available_fields(fromfile)
    invalid_fields = [f for f in fields if f not in available_fields]
    
    if invalid_fields:
        for field in invalid_fields:
            suggestions = find_similar_field_names(field, available_fields)
            raise ValidationError(
                f"Field '{field}' does not exist",
                field=field,
                suggestions=suggestions
            )
```

### 4. Format Validation

Validate file formats with supported formats list:

```python
from undatum.common.errors import FormatError

SUPPORTED_FORMATS = ['csv', 'jsonl', 'parquet', 'avro']

def my_command(fromfile, options=None):
    file_type = detect_file_type(fromfile)
    if file_type not in SUPPORTED_FORMATS:
        raise FormatError(
            fromfile,
            file_type,
            supported_formats=SUPPORTED_FORMATS
        )
```

### 5. Dependency Checking

Check for optional dependencies:

```python
from undatum.common.errors import DependencyError

def my_command(fromfile, options=None):
    try:
        import yaml
    except ImportError:
        raise DependencyError(
            'pyyaml',
            feature='YAML template support'
        )
```

### 6. Database Error Handling

Handle database errors with masked connection URIs:

```python
from undatum.common.errors import DatabaseError

def my_command(connection_uri, options=None):
    try:
        conn = connect_to_database(connection_uri)
    except Exception as e:
        raise DatabaseError(
            f"Connection failed: {str(e)}",
            db_type="postgresql",
            connection_uri=connection_uri  # Will be masked automatically
        ) from e
```

### 7. Validation Error with Context

Provide context for validation errors:

```python
from undatum.common.errors import ValidationError

def my_command(fromfile, options=None):
    method = options.get('method')
    valid_methods = ['redact', 'hash', 'mask']
    
    if method not in valid_methods:
        raise ValidationError(
            f"Invalid method '{method}'",
            field="method",
            suggestions=valid_methods,
            context={
                "valid_options": valid_methods,
                "provided": method
            }
        )
```

## Error Message Guidelines

### 1. Be Clear and Actionable

**Bad:**
```python
raise ValueError("Error occurred")
```

**Good:**
```python
raise ValidationError(
    "Missing required parameter 'fields'",
    field="fields"
)
```

### 2. Provide Suggestions

**Bad:**
```python
raise FileNotFoundError("/path/to/file.csv")
```

**Good:**
```python
suggestions = find_similar_files("/path/to/file.csv")
raise FileNotFoundError("/path/to/file.csv", suggestions)
```

### 3. Include Context

**Bad:**
```python
raise ValidationError("Invalid value")
```

**Good:**
```python
raise ValidationError(
    f"Invalid method '{method}'",
    field="method",
    suggestions=['redact', 'hash', 'mask']
)
```

### 4. Mask Sensitive Information

**Bad:**
```python
raise DatabaseError(f"Connection failed: {connection_uri}")
```

**Good:**
```python
raise DatabaseError(
    "Connection failed",
    connection_uri=connection_uri  # Automatically masked
)
```

## Exit Codes

Use appropriate exit codes:

- **1**: User errors (invalid input, file not found)
- **2**: Usage and configuration errors (unknown option, missing dependencies, invalid config)
- **3**: System errors (permission denied, database errors)
- **4**: Internal errors (unexpected exceptions)
- **130**: Interrupted (Ctrl-C)

Exit codes are automatically set by exception classes. Don't manually set `sys.exit()`.
A command must never exit with 0 after an error, and a failing check (a `--fail-on` drift, a
`quality` threshold) exits with 1.

Each class also has a stable `code` (`file_not_found`, `validation_error`,
`dependency_missing`, ...). With `--json` or `--format-out json` the handler prints the error as
a JSON object on stderr (`{"error": {"code": ..., "message": ...}}`) instead of text; the codes
are listed on the [JSON output](/commands/json-output#errors) page. When you add an error
class, give it a `code` and document it there.

## Global Error Handling

The global error handler in `undatum/__main__.py` automatically:
- Catches all exceptions
- Formats error messages
- Sets appropriate exit codes
- Shows full tracebacks in verbose mode

You don't need to handle errors at the command level unless you want to add specific context.

## Testing Error Handling

Test error scenarios in your command tests:

```python
import pytest
from undatum.common.errors import FileNotFoundError, ValidationError

def test_command_file_not_found():
    """Test command with nonexistent file."""
    from undatum.cmds.my_command import MyCommand
    
    command = MyCommand()
    with pytest.raises(FileNotFoundError):
        command.process("/nonexistent/file.csv", {})

def test_command_validation_error():
    """Test command with invalid parameters."""
    from undatum.cmds.my_command import MyCommand
    
    command = MyCommand()
    with pytest.raises(ValidationError) as exc_info:
        command.process("data.csv", {})  # Missing required option
    assert "fields" in str(exc_info.value).lower()
```

## Best Practices

1. **Always validate inputs early**: Check file existence, permissions, and parameters at the start of command methods
2. **Use custom exceptions**: Never raise generic `ValueError` or `FileNotFoundError` (Python built-in)
3. **Provide suggestions**: Use `find_similar_files()` and `find_similar_field_names()` for typos
4. **Include context**: Add relevant information to error messages
5. **Mask sensitive data**: Never expose passwords or API keys in error messages
6. **Test error scenarios**: Write tests for all error paths
7. **Follow patterns**: Use existing commands as examples

## Example: Complete Command with Error Handling

```python
"""Example command with proper error handling."""
from undatum.common.path_utils import validate_file_path
from undatum.common.errors import (
    FileNotFoundError,
    PermissionError,
    ValidationError,
    find_similar_files,
    find_similar_field_names,
)

class ExampleCommand:
    """Example command handler."""
    
    def process(self, fromfile, tofile, options=None):
        """Process file with comprehensive error handling."""
        if options is None:
            options = {}
        
        # Validate input file
        try:
            validate_file_path(fromfile, check_read=True)
        except FileNotFoundError as e:
            suggestions = find_similar_files(fromfile)
            raise FileNotFoundError(fromfile, suggestions) from e
        except PermissionError as e:
            raise PermissionError(fromfile, operation="read") from e
        
        # Validate output file
        try:
            validate_file_path(tofile, check_write=True)
        except PermissionError as e:
            raise PermissionError(tofile, operation="write") from e
        
        # Validate required parameters
        fields = options.get('fields')
        if not fields:
            raise ValidationError(
                "Missing required parameter 'fields'",
                field="fields"
            )
        
        # Validate field names
        available_fields = self._get_fields(fromfile)
        fields_list = fields.split(',') if isinstance(fields, str) else fields
        
        for field in fields_list:
            if field not in available_fields:
                suggestions = find_similar_field_names(field, available_fields)
                raise ValidationError(
                    f"Field '{field}' does not exist",
                    field=field,
                    suggestions=suggestions
                )
        
        # Process file
        # ... actual processing logic ...
    
    def _get_fields(self, fromfile):
        """Get available fields from file."""
        # ... implementation ...
        return ['field1', 'field2', 'field3']
```

## Related Files

- `undatum/common/errors.py` - Error handling infrastructure
- `undatum/common/path_utils.py` - File path validation utilities
- `undatum/__main__.py` - Global error handler
- `tests/test_error_handling.py` - Error handling tests
