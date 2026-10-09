---
title: "Data API"
description: "Read-only FastAPI + DuckDB server over files"
---
# Data API

The file-backed Data API (`undatum api serve` / `undatum api run`) is **read-only**.
It is intended for local exploration and trusted networks. Harden it before exposing
it beyond localhost.

Command examples: [`api`](/commands/api).

## Built-in API key (optional)

Start the server with a key:

```bash norun
undatum api serve --config api.yml --api-key "$UNDATUM_API_KEY"
# or
export UNDATUM_API_KEY=replace-me
undatum api run data.csv
```

Clients must send the key as `X-API-Key` (or `?api_key=`). Requests without a matching
key receive HTTP 401. `/docs`, `/redoc`, and `/openapi.json` stay open so operators can
inspect the schema.

This is a shared-secret check, not a full identity system. Do not treat it as a
replacement for SSO or per-user authorization.

## Reverse proxy (recommended for production)

Put the API behind nginx, Caddy, or a cloud load balancer and terminate TLS there:

- Bind undatum to `127.0.0.1` (the default).
- Require authentication at the proxy (basic auth, OIDC, mTLS).
- Rate-limit and log access at the proxy.
- Use the built-in `--api-key` only as defense in depth, or omit it if the proxy
  already authenticates every request.

## CORS

Browser apps need an explicit origin list:

```bash norun
undatum api serve --config api.yml --cors-origins https://app.example.com
```

Leave `--cors-origins` unset for CLI/server-to-server use.

## Cloud-backed resources

Resource `path` values may be object-storage URIs:

| Provider | URI examples | Extra |
|----------|----------------|-------|
| AWS S3 | `s3://bucket/key` | `undatum[s3]` or `undatum[cloud]` |
| Google Cloud Storage | `gs://bucket/key`, `gcs://bucket/key` | `undatum[gcs]` or `undatum[cloud]` |
| Azure Blob / ADLS | `az://container/key`, `abfs://…`, `abfss://…` | `undatum[azure]` or `undatum[cloud]` |

The server downloads the object to a temporary file at startup (DuckDB needs a
local path). S3 uses the standard AWS credential chain (`AWS_ACCESS_KEY_ID` /
`AWS_SECRET_ACCESS_KEY`, `AWS_PROFILE`, `AWS_REGION`, or `~/.aws/credentials`).
GCS uses Application Default Credentials / `GOOGLE_APPLICATION_CREDENTIALS`.
Azure uses `AZURE_STORAGE_ACCOUNT` / `AZURE_STORAGE_KEY` or the adlfs identity
chain.

HTTP URLs and other non-cloud remote schemes are rejected.

Config files are validated against an embedded JSON Schema (required `resources[]`
with `name`, `path`, and `format` in `csv` / `json` / `jsonl` / `parquet`).
