"""
Protocol Builder for federated agent summaries.

Ensures client-side summaries conform to the server's PushRequest schema
before transmission, preventing 422 Validation Errors and protocol mismatches.

Provides:
- ClientSummaryBuilder: Constructs AgentSummary from raw produce_local_summary output
- SchemaValidationError: Raised when summary doesn't match server schema
- Deterministic agent_id generation from repository content
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class SchemaValidationError(Exception):
    """Raised when client summary doesn't match server schema."""

    pass


class ClientSummaryBuilder:
    """Build protocol-compliant AgentSummary from raw produce_local_summary output.

    Handles:
    - Key name mapping (topics -> topic_counts)
    - Fact count to fact_hashes conversion (int -> list of hash strings)
    - Auto-generation of agent_id from repo hash (deterministic, replayable)
    - ISO-8601 timestamp addition
    - Schema validation against server expectations
    - Wrapping in {"summary": {...}} envelope
    """

    REQUIRED_FIELDS = {"agent_id", "timestamp", "topic_counts", "fact_hashes"}

    @staticmethod
    def generate_agent_id(repo_root: Path) -> str:
        """Generate deterministic agent_id from repository content.

        Uses SHA-256 hash of repo root path to ensure consistency across runs
        while remaining unique per repository. This is deterministic (same repo
        always gets same agent_id) and replayable.

        Args:
            repo_root: Path to the repository root

        Returns:
            Unique agent identifier in format: "agent-<first-16-chars-of-hash>"
        """
        repo_hash = hashlib.sha256(str(repo_root.resolve()).encode()).hexdigest()[:16]
        return f"agent-{repo_hash}"

    @staticmethod
    def build(
        repo_root: Path,
        raw_summary: Dict[str, Any],
        strict_mode: bool = False,
    ) -> Dict[str, Any]:
        """Build protocol-compliant summary from raw produce_local_summary output.

        Transforms the client's produce_local_summary() output into the format
        expected by the server's PushRequest model.

        Args:
            repo_root: Path to repository root (used for agent_id generation)
            raw_summary: Output from produce_local_summary()
            strict_mode: If True, raise on validation error; if False, warn and repair

        Returns:
            Dict with structure: {"summary": {"agent_id": "...", "timestamp": "...",
                                              "topic_counts": {...}, "fact_hashes": [...]}}

        Raises:
            SchemaValidationError: If strict_mode=True and schema validation fails
        """
        # In strict mode, validate raw input has required fields BEFORE transformation
        if strict_mode:
            required_raw_fields = {"memory_types", "topics", "topic_hashes", "fact_count"}
            missing = required_raw_fields - set(raw_summary.keys())
            if missing:
                raise SchemaValidationError(
                    f"Raw summary missing required fields: {', '.join(sorted(missing))}"
                )

        # Generate required fields
        agent_id = ClientSummaryBuilder.generate_agent_id(repo_root)
        timestamp = datetime.now(timezone.utc).isoformat()

        # Transform key names and structure
        topic_counts = raw_summary.get("topics", {})
        if not isinstance(topic_counts, dict):
            topic_counts = {}

        # Convert fact_count (int) to fact_hashes (list of strings)
        # If topic_hashes is present, use it; otherwise generate from fact_count
        fact_hashes: List[str] = []
        if "topic_hashes" in raw_summary and isinstance(raw_summary["topic_hashes"], dict):
            # Flatten all topic hashes into a single list
            for topic_hash_list in raw_summary["topic_hashes"].values():
                if isinstance(topic_hash_list, list):
                    fact_hashes.extend(topic_hash_list)

        # If fact_hashes is still empty but we have fact_count, generate placeholder hashes
        if not fact_hashes and "fact_count" in raw_summary:
            fact_count = raw_summary["fact_count"]
            if isinstance(fact_count, int):
                # Generate placeholder hashes (in real scenario, client would preserve actual hashes)
                fact_hashes = [
                    hashlib.sha256(f"fact-{i}".encode()).hexdigest() for i in range(fact_count)
                ]

        # Build AgentSummary structure
        agent_summary = {
            "agent_id": agent_id,
            "timestamp": timestamp,
            "topic_counts": topic_counts,
            "fact_hashes": fact_hashes,
        }

        # Validate schema
        errors = ClientSummaryBuilder._validate_schema(agent_summary)
        if errors:
            error_msg = f"Schema validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            if strict_mode:
                raise SchemaValidationError(error_msg)
            else:
                print(f"Warning: {error_msg}")

        # Return wrapped in envelope
        return {"summary": agent_summary}

    @staticmethod
    def _validate_schema(agent_summary: Dict[str, Any]) -> List[str]:
        """Validate agent_summary against expected schema.

        Args:
            agent_summary: The summary dict to validate

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        # Check required fields
        for field in ClientSummaryBuilder.REQUIRED_FIELDS:
            if field not in agent_summary:
                errors.append(f"Missing required field: {field}")

        # Validate field types
        if "agent_id" in agent_summary and not isinstance(agent_summary["agent_id"], str):
            errors.append(f"agent_id must be string, got {type(agent_summary['agent_id'])}")

        if "timestamp" in agent_summary:
            ts = agent_summary["timestamp"]
            if not isinstance(ts, str):
                errors.append(f"timestamp must be string, got {type(ts)}")
            # Validate ISO-8601 format
            elif not _is_iso8601(ts):
                errors.append(f"timestamp not in ISO-8601 format: {ts}")

        if "topic_counts" in agent_summary:
            tc = agent_summary["topic_counts"]
            if not isinstance(tc, dict):
                errors.append(f"topic_counts must be dict, got {type(tc)}")
            else:
                for k, v in tc.items():
                    if not isinstance(k, str):
                        errors.append(f"topic_counts key must be string, got {type(k)}")
                    if not isinstance(v, int):
                        errors.append(f"topic_counts value must be int, got {type(v)}")

        if "fact_hashes" in agent_summary:
            fh = agent_summary["fact_hashes"]
            if not isinstance(fh, list):
                errors.append(f"fact_hashes must be list, got {type(fh)}")
            else:
                for h in fh:
                    if not isinstance(h, str):
                        errors.append(f"fact_hashes element must be string, got {type(h)}")

        return errors


def _is_iso8601(timestamp: str) -> bool:
    """Check if timestamp is in ISO-8601 format."""
    try:
        # Try parsing with common ISO-8601 formats
        if timestamp.endswith("Z"):
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        else:
            datetime.fromisoformat(timestamp)
        return True
    except (ValueError, TypeError):
        return False
