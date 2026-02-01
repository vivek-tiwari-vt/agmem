# Federated collaboration

Agmem can push local summaries to an external coordinator and pull merged summaries. No coordinator is shipped with the package; you run your own or use a third-party service.

## Configuration

In `.mem/config.json` or user config:

```json
{
  "federated": {
    "enabled": true,
    "coordinator_url": "https://your-coordinator.example.com",
    "memory_types": ["episodic", "semantic"],
    "differential_privacy": {
      "enabled": true,
      "epsilon": 0.1,
      "delta": 1e-5
    }
  }
}
```

- `coordinator_url`: Base URL of the coordinator (no trailing slash).
- `memory_types`: Which memory dirs to include in the summary.
- `differential_privacy.enabled`: If true, numeric fields in the summary are noised before push.

## Coordinator API

The coordinator must expose two endpoints.

### POST /push

**Request**

- Body: JSON object (local summary from `produce_local_summary`).
- `Content-Type: application/json`.

**Summary shape**

- `memory_types`: list of strings (e.g. `["episodic", "semantic"]`).
- `topics`: dict of memory type → integer count (file count per type; may be noised if DP enabled).
- `topic_hashes`: dict of memory type → list of topic labels (no raw content).
- `fact_count`: integer (total fact/file count; may be noised if DP enabled).

**Response**

- Status `200` or `201`: success.
- Any other status: push is considered failed (agmem reports the status).

### GET /pull

**Request**

- No body.

**Response**

- Status `200`: body is JSON (merged summary from coordinator).
- Any other status or failure: pull returns `None` (agmem reports failure).

The merged summary shape is defined by the coordinator (e.g. aggregated topic counts, list of topic labels from all agents). Agmem does not interpret it; it only prints the returned object.

## Commands

- `agmem federated push`: Produce local summary (with optional DP) and POST to coordinator `/push`.
- `agmem federated pull`: GET coordinator `/pull` and print merged summary.

## Security

- Use HTTPS for `coordinator_url`.
- Request timeout is 30 seconds.
- No authentication is built in; if the coordinator requires auth, you must extend the client (e.g. custom header or token in config) or run the coordinator behind a gateway that adds auth.
