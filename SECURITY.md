# Security policy

## Supported versions

Security fixes are released for the latest minor version only.

| Version | Supported |
|---------|-----------|
| 1.7.x   | Yes       |
| < 1.7   | No        |

## Reporting a vulnerability

Please do not open a public issue for a security problem.

Email **ivan@begtin.tech** with:

- the undatum version (`undatum --version`) and how it was installed (pip, pipx, uv,
  release binary);
- the command, Data API route or MCP tool involved;
- a minimal input file or request that reproduces the problem, and what an attacker gains.

You will get an acknowledgement within 5 working days. Confirmed issues are fixed in a
patch release and credited in the changelog unless you prefer otherwise. Please give us
90 days, or until a fix is released, before publishing details.

## Scope

Areas where a vulnerability is most likely and most welcome:

- the read-only Data API (`undatum api serve`): authentication, query sandboxing, resource
  limits;
- the MCP server and LangChain tools (`undatum mcp serve`): path sandboxing (`--root`),
  read-only SQL;
- validation rule files and pipeline YAML, which may come from other people;
- archive handling (ZIP, 7z, tar) and file paths taken from data.

Problems in dependencies should be reported to the dependency; tell us too if undatum's
use of it makes the impact worse.
