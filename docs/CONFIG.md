# agmem config (config.yaml / .agmemrc)

Optional configuration for cloud storage (S3/GCS) and PII scanning. **Credentials must be set via environment variables or standard AWS/GCP mechanisms; never store secret values in config files.**

## File locations

| Scope   | Path |
|---------|------|
| User    | `~/.config/agmem/config.yaml` or `$XDG_CONFIG_HOME/agmem/config.yaml` |
| Repo    | `<repo_root>/.agmemrc` or `<repo_root>/.mem/config.yaml` (first found) |

Merge order: defaults → user config → repo config (repo overrides user).

## Schema (non-secret only in files)

All credential *values* come from environment variables. Config may only reference env var *names* and non-secret options.

### Cloud: S3

```yaml
cloud:
  s3:
    region: null              # e.g. us-east-1
    endpoint_url: null        # e.g. https://minio.example.com (for MinIO)
    access_key_var: AWS_ACCESS_KEY_ID      # env var name for access key
    secret_key_var: AWS_SECRET_ACCESS_KEY  # env var name for secret key
    lock_table: null          # optional DynamoDB table for distributed locks
```

- When using **s3://** or **gs://** as a remote URL (`agmem remote add origin s3://bucket/prefix`), push and fetch **acquire a distributed lock** (DynamoDB for S3 when `lock_table` is set, or storage-based lock for GCS) before running and **release it** in a `finally` block. This prevents concurrent pushes/fetches from corrupting the remote.

- Set `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` in the environment (or use `~/.aws/credentials` and omit these in config).
- If `access_key_var` / `secret_key_var` are set, agmem resolves credentials with `os.getenv(var)` and passes them to the S3 client. If unset, boto3 uses its default credential chain.

### Cloud: GCS

```yaml
cloud:
  gcs:
    project: null             # GCP project ID
    credentials_path: null    # path to service account JSON (validated under repo or home)
    credentials_json_var: null # env var name containing JSON key (alternative to file)
```

- **credentials_path**: If relative, resolved from repo root or user home. Must be under an allowed root (no path traversal).
- **credentials_json_var**: Name of an env var whose value is a JSON string (service account key). Useful for CI; never put the JSON in the config file.
- If neither is set, GCS uses Application Default Credentials (`GOOGLE_APPLICATION_CREDENTIALS` or `gcloud auth`).

### Daemon health monitoring

```yaml
daemon:
  health_check_interval_seconds: 3600   # periodic Merkle/signature check (default 3600); 0 to disable
```

- Override via env: `AGMEM_DAEMON_HEALTH_INTERVAL` (seconds).
- On verify failure the daemon only logs to stderr and suggests `agmem fsck`; no automatic destructive action.

### PII / hooks

```yaml
pii:
  enabled: true               # set false to skip PII scan on commit
  allowlist: []               # path globs to skip (e.g. ["current/semantic/public/*"])
```

- **enabled**: If `false`, the pre-commit PII scanner is skipped (config-driven).
- **allowlist**: Paths matching any glob are excluded from PII scanning (and thus do not fail the commit).

## Example: user config

`~/.config/agmem/config.yaml`:

```yaml
cloud:
  s3:
    region: us-east-1
    access_key_var: AWS_ACCESS_KEY_ID
    secret_key_var: AWS_SECRET_ACCESS_KEY
  gcs:
    project: my-gcp-project
pii:
  enabled: true
  allowlist: []
```

## Example: repo overrides (MinIO + disable PII)

`.agmemrc` in repo root:

```yaml
cloud:
  s3:
    endpoint_url: https://minio.example.com
    region: us-east-1
    access_key_var: AGMEM_S3_ACCESS_KEY
    secret_key_var: AGMEM_S3_SECRET_KEY
pii:
  enabled: false
```

Then set `AGMEM_S3_ACCESS_KEY` and `AGMEM_S3_SECRET_KEY` in the environment.

## Safety

1. **No credential values in config** — only env var names and non-secret options.
2. **Path safety** — `credentials_path` for GCS is resolved to absolute and must lie under repo root or user home.
3. **YAML** — only `yaml.safe_load` is used; no custom tags.
4. **Logs** — secret values and env var contents are never printed in logs or error messages.
