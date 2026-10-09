# OpenSpec Workflow Guide

## Quick Reference

### Common Commands

```bash
# List all active proposals
openspec list

# List all capabilities (specs)
openspec list --specs

# Show a specific proposal
openspec show <change-id>

# Validate a proposal
openspec validate <change-id> --strict

# Archive completed work
openspec archive <change-id> --yes
```

## Three-Stage Workflow

### Stage 1: Creating Changes (Proposal)

**When:** Planning new features, optimizations, breaking changes

**Steps:**
1. Check existing work: `openspec list` and `openspec list --specs`
2. Create proposal with:
   - `proposal.md` - Why, what, impact
   - `tasks.md` - Implementation checklist
   - `design.md` - Technical decisions (if needed)
   - `specs/[capability]/spec.md` - Requirements with scenarios
3. Validate: `openspec validate [change-id] --strict`
4. **Wait for approval** before implementing


### Stage 2: Implementing Changes

**When:** Proposal is approved

**Steps:**
1. Read `proposal.md` to understand goals
2. Read `design.md` (if exists) for technical decisions
3. Follow `tasks.md` sequentially
4. Mark tasks complete: `- [x]`
5. Test thoroughly
6. Update documentation


### Stage 3: Archiving Changes

**When:** Feature is deployed

**Steps:**
1. Ensure all tasks in `tasks.md` are marked `- [x]`
2. Archive: `openspec archive [change-id] --yes`
3. This moves the change to `changes/archive/YYYY-MM-DD-[name]/`

## Working with AI Assistant

### Requesting Proposals
- "Create a proposal for [feature]"
- "Help me plan [change]"
- "Generate OpenSpec proposal for [optimization]"

### During Implementation
- "Implement task 1.1.1 from [change-id]"
- "Update the implementation for [change-id]"
- "Help me complete [specific task]"

### Review and Approval
- Review proposal files in `openspec/changes/[change-id]/`
- Ask questions or request changes
- Approve when ready

## Key Principles

1. **Specs are truth** - `openspec/specs/` shows what IS built
2. **Changes are proposals** - `openspec/changes/` shows what SHOULD be built
3. **Always validate** - Use `--strict` flag
4. **Approval gate** - No implementation until approved
5. **Track progress** - Keep `tasks.md` updated

## File Structure

```
openspec/
├── specs/                    # Current truth
│   └── [capability]/
│       └── spec.md
├── changes/                  # Active proposals
│   └── [change-id]/
│       ├── proposal.md
│       ├── design.md
│       ├── tasks.md
│       └── specs/
│           └── [capability]/
│               └── spec.md
└── changes/archive/          # Completed work
    └── YYYY-MM-DD-[name]/
```

## Decision Tree

**Need to make a change?**
- Bug fix → Fix directly (no proposal)
- Typo/formatting → Fix directly (no proposal)
- New feature → Create proposal
- Optimization → Create proposal
- Breaking change → Create proposal

## Related

- [`openspec/AGENTS.md`](openspec/AGENTS.md) — full workflow and spec format
- [Contributing](docs/docs/development/contributing.md), [architecture](docs/docs/development/architecture.md), [testing](docs/docs/development/testing.md)
