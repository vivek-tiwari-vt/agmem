"""
Tier 3: Protocol Validation Tests

Tests for schema validation, protocol compliance, and privacy audit.
Ensures client and server communicate correctly and privacy guarantees hold.

Coverage target: 80% for protocol components
"""

import pytest
import json
from pathlib import Path
from typing import Dict, Any
import tempfile
import shutil

import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def temp_repo():
    """Create a temporary repository for testing."""
    temp_dir = tempfile.mkdtemp()
    repo_root = Path(temp_dir)
    (repo_root / "current").mkdir(parents=True, exist_ok=True)
    yield repo_root
    shutil.rmtree(temp_dir, ignore_errors=True)


class TestClientServerSchemaValidation:
    """Tests for protocol schema compatibility."""

    def test_client_summary_matches_server_schema(self, temp_repo):
        """Test that ClientSummaryBuilder output matches server PushRequest schema."""
        from memvcs.core.protocol_builder import ClientSummaryBuilder

        raw_summary = {
            "memory_types": ["semantic"],
            "topics": {"semantic": 5},
            "topic_hashes": {"semantic": ["hash1", "hash2"]},
            "fact_count": 5,
        }

        result = ClientSummaryBuilder.build(temp_repo, raw_summary)

        # Verify it matches server's AgentSummary schema
        summary = result["summary"]
        assert isinstance(summary["agent_id"], str)
        assert isinstance(summary["timestamp"], str)
        assert isinstance(summary["topic_counts"], dict)
        assert isinstance(summary["fact_hashes"], list)

        # All values in topic_counts should be ints
        for k, v in summary["topic_counts"].items():
            assert isinstance(k, str)
            assert isinstance(v, int)

        # All values in fact_hashes should be strings (hex hashes)
        for h in summary["fact_hashes"]:
            assert isinstance(h, str)

    def test_protocol_envelope_structure(self, temp_repo):
        """Test that result is properly wrapped in envelope."""
        from memvcs.core.protocol_builder import ClientSummaryBuilder

        raw = {"memory_types": [], "topics": {}, "topic_hashes": {}, "fact_count": 0}
        result = ClientSummaryBuilder.build(temp_repo, raw)

        # Must have top-level "summary" key
        assert "summary" in result
        assert len(result) == 1  # Only "summary" key at top level

    def test_invalid_key_names_corrected(self, temp_repo):
        """Test that client's wrong key names are corrected."""
        from memvcs.core.protocol_builder import ClientSummaryBuilder

        # Client sends "topics" and "topic_hashes", server expects "topic_counts"
        raw_summary = {
            "memory_types": ["semantic"],
            "topics": {"semantic": 10},  # Wrong key name
            "topic_hashes": {"semantic": ["hash1"]},
            "fact_count": 1,
        }

        result = ClientSummaryBuilder.build(temp_repo, raw_summary)
        summary = result["summary"]

        # Should have "topic_counts", not "topics"
        assert "topic_counts" in summary
        assert "topics" not in summary
        assert summary["topic_counts"]["semantic"] == 10

    def test_fact_count_to_fact_hashes_conversion(self, temp_repo):
        """Test that fact_count (int) is converted to fact_hashes (list)."""
        from memvcs.core.protocol_builder import ClientSummaryBuilder

        raw_summary = {
            "memory_types": ["semantic"],
            "topics": {"semantic": 3},
            "topic_hashes": {"semantic": ["h1", "h2", "h3"]},
            "fact_count": 3,
        }

        result = ClientSummaryBuilder.build(temp_repo, raw_summary)
        summary = result["summary"]

        # Should have "fact_hashes", not "fact_count"
        assert "fact_hashes" in summary
        assert "fact_count" not in summary
        assert isinstance(summary["fact_hashes"], list)
        assert len(summary["fact_hashes"]) == 3

    def test_schema_validation_with_missing_fields(self, temp_repo):
        """Test schema validation catches missing required fields."""
        from memvcs.core.protocol_builder import ClientSummaryBuilder, SchemaValidationError

        raw_summary = {
            "topics": {"semantic": 5},
            # Missing memory_types, topic_hashes, fact_count
        }

        # In strict mode, should raise
        with pytest.raises(SchemaValidationError):
            ClientSummaryBuilder.build(temp_repo, raw_summary, strict_mode=True)

    def test_schema_validation_iso8601_timestamp(self, temp_repo):
        """Test that generated timestamp is valid ISO-8601."""
        from memvcs.core.protocol_builder import ClientSummaryBuilder
        from datetime import datetime

        raw = {"memory_types": [], "topics": {}, "topic_hashes": {}, "fact_count": 0}
        result = ClientSummaryBuilder.build(temp_repo, raw)

        timestamp = result["summary"]["timestamp"]

        # Should be parseable as ISO-8601
        try:
            if timestamp.endswith("Z"):
                datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            else:
                datetime.fromisoformat(timestamp)
        except ValueError as e:
            pytest.fail(f"Timestamp not valid ISO-8601: {timestamp}, error: {e}")


class TestPrivacyAudit:
    """Tests for privacy field validation and auditing."""

    def test_privacy_exempt_fields_identified(self):
        """Test that privacy-exempt fields are correctly identified."""
        from memvcs.core.privacy_validator import PrivacyFieldValidator

        validator = PrivacyFieldValidator()

        # These should be identified as exempt
        exempt_fields = [
            "clusters_found",
            "insights_generated",
            "episodes_archived",
            "confidence_score",
        ]

        for field in exempt_fields:
            assert field in PrivacyFieldValidator.EXEMPT_FIELDS

    def test_privacy_validator_rejects_metadata_noise(self):
        """Test that validator rejects noise on metadata fields."""
        from memvcs.core.privacy_validator import PrivacyFieldValidator

        validator = PrivacyFieldValidator()

        # Should raise: attempting to apply noise to exempt field
        with pytest.raises(RuntimeError) as exc_info:
            validator.validate_noised_field("confidence_score", 0.95, is_noised=True)

        assert "exempt" in str(exc_info.value).lower()

    def test_privacy_validator_allows_fact_noise(self):
        """Test that validator allows noise on fact fields."""
        from memvcs.core.privacy_validator import PrivacyFieldValidator

        validator = PrivacyFieldValidator()

        # Should not raise: fact fields can be noised
        validator.validate_noised_field("fact_count", 42, is_noised=True)
        validator.validate_noised_field("memory_count", 100, is_noised=True)

        assert "fact_count" in validator.audit_report.noised_fields
        assert "memory_count" in validator.audit_report.noised_fields

    def test_privacy_audit_report_generation(self):
        """Test that privacy audit report is generated correctly."""
        from memvcs.core.privacy_validator import PrivacyFieldValidator

        validator = PrivacyFieldValidator()

        # Record some field activities
        validator.validate_noised_field("fact_count", 42, is_noised=True)
        validator.validate_noised_field("created_at", "2024-01-01", is_noised=False)

        report = validator.get_report()

        # Verify report structure
        assert "fact_count" in report.noised_fields
        assert "created_at" in report.exempt_fields
        assert "timestamp" in report.to_dict()

    def test_privacy_guard_context_manager(self):
        """Test PrivacyGuard context manager."""
        from memvcs.core.privacy_validator import PrivacyGuard

        with PrivacyGuard(strict=False) as pg:
            pg.mark_noised("fact_count", 50)
            pg.mark_exempt("metadata_field", "value")

        report = pg.get_report()

        assert "fact_count" in report.noised_fields
        assert "metadata_field" in report.exempt_fields

    def test_privacy_guard_strict_mode_catches_errors(self):
        """Test that PrivacyGuard strict mode catches violations."""
        from memvcs.core.privacy_validator import PrivacyGuard

        with pytest.raises(RuntimeError):
            with PrivacyGuard(strict=True) as pg:
                pg.mark_noised("confidence_score", 0.9)  # Should fail


class TestVersionManagement:
    """Tests for version handling and consistency."""

    def test_coordinator_version_from_pyproject(self):
        """Test that coordinator loads version from pyproject.toml."""
        from memvcs.coordinator.server import _version

        # Should be a version string, not hardcoded
        assert _version is not None
        assert isinstance(_version, str)
        assert _version != "0.1.6"  # Should not be the old hardcoded version
        assert "." in _version  # Should look like a version number

    def test_protocol_builder_agent_id_format(self, temp_repo):
        """Test that agent_id has expected format."""
        from memvcs.core.protocol_builder import ClientSummaryBuilder

        raw = {"memory_types": [], "topics": {}, "topic_hashes": {}, "fact_count": 0}
        result = ClientSummaryBuilder.build(temp_repo, raw)

        agent_id = result["summary"]["agent_id"]

        # Should start with "agent-"
        assert agent_id.startswith("agent-")
        # Should have hash portion
        assert len(agent_id) > 6


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
