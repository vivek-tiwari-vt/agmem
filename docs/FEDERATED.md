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
- `differential_privacy.enabled`: If true, fact-level numeric fields are noised before push (metadata is exempt).

## Coordinator API

The coordinator must expose two endpoints.

### POST /push

**Request**

- Body: JSON object (protocol-compliant summary envelope).
- `Content-Type: application/json`.

**Summary shape**

Top-level envelope:

- `summary`: object containing the fields below.

Summary fields:

- `agent_id`: deterministic client identifier (SHA-256).
- `timestamp`: ISO-8601 UTC timestamp.
- `memory_types`: list of strings (e.g. `["episodic", "semantic"]`).
- `topic_counts`: dict of memory type → integer count (may be noised if DP enabled).
- `fact_hashes`: list of strings (hashes; no raw content).

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
