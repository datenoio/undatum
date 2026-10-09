## ADDED Requirements

### Requirement: Streaming S3 Reads
Reading `s3://` URIs SHALL stream the object instead of downloading it completely to a local
temporary file, while honouring region and profile options.

#### Scenario: Large S3 object
- **WHEN** user runs `undatum head s3://bucket/big.csv --limit 10`
- **THEN** only the bytes needed for ten rows (plus buffering) are transferred
