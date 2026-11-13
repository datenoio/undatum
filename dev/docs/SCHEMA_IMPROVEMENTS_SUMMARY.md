# Schema Command Improvement Proposals Summary

This document summarizes the three OpenSpec change proposals created based on the Schema Command Review (`dev/docs/SCHEMA_COMMAND_REVIEW.md`).

## Proposals Created

### 1. `improve-schema-command` (Priority: CRITICAL)

**Purpose**: Fix critical bugs and add missing features to make the schema command functional and feature-complete.

**Key Changes**:
- Implement output format support (text/json/yaml) - currently ignored
- Implement AI documentation support - currently broken
- Add record counting - currently missing
- Improve file format support (XLSX, XLS, XML, DOCX)
- Add compression detection
- Add engine selection (auto/duckdb/iterable)
- Improve error handling
- Fix bulk mode glob pattern support
- Eliminate code duplication with shared utilities

**Status**: ✅ Validated
**Location**: `openspec/changes/improve-schema-command/`

**Dependencies**: None - can be implemented independently

---

### 2. `consolidate-schema-commands` (Priority: HIGH)

**Purpose**: Merge `schema` and `scheme` commands into a unified interface with format selection.

**Key Changes**:
- Add `--format` parameter to `schema` command
- Support formats: `yaml`, `json`, `cerberus`, `jsonschema`, `avro`, `parquet`
- Deprecate `scheme` command with migration path
- Redirect `scheme` to `schema --format cerberus`

**Status**: ✅ Validated
**Location**: `openspec/changes/consolidate-schema-commands/`

**Dependencies**: Should be implemented after `improve-schema-command` to ensure unified command has all features

---

### 3. `add-schema-format-exports` (Priority: HIGH)

**Purpose**: Add support for industry-standard schema formats (JSON Schema, Avro, Parquet).

**Key Changes**:
- Implement JSON Schema export (W3C/IETF standard)
- Implement Avro Schema export (Apache standard)
- Implement Parquet Schema export
- Add type mapping utilities for format conversion

**Status**: ✅ Validated
**Location**: `openspec/changes/add-schema-format-exports/`

**Dependencies**: Should be implemented after `consolidate-schema-commands` to add formats to unified command

---

## Implementation Order

Recommended sequence:

1. **First**: `improve-schema-command`
   - Fixes critical bugs
   - Adds missing features
   - Makes command functional
   - No dependencies

2. **Second**: `consolidate-schema-commands`
   - Unifies command interface
   - Deprecates old command
   - Depends on improved schema command

3. **Third**: `add-schema-format-exports`
   - Adds standard formats
   - Enhances unified command
   - Depends on consolidated command

## Validation Status

All proposals have been validated with `openspec validate --strict`:
- ✅ `improve-schema-command` - Valid
- ✅ `consolidate-schema-commands` - Valid
- ✅ `add-schema-format-exports` - Valid

## Next Steps

1. Review proposals for approval
2. Implement `improve-schema-command` first (critical fixes)
3. Implement `consolidate-schema-commands` (unify interface)
4. Implement `add-schema-format-exports` (add standard formats)

## Related Documents

- **Review Report**: `dev/docs/SCHEMA_COMMAND_REVIEW.md` - Comprehensive analysis
- **Proposal 1**: `openspec/changes/improve-schema-command/proposal.md`
- **Proposal 2**: `openspec/changes/consolidate-schema-commands/proposal.md`
- **Proposal 3**: `openspec/changes/add-schema-format-exports/proposal.md`
