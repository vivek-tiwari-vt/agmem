"""
Tests for Compliance Dashboard features.
"""

import json
import pytest
import tempfile
from pathlib import Path

from memvcs.core.repository import Repository


@pytest.fixture
def test_repo():
    """Create a test repository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        repo = Repository.init(repo_path, author_name="Test", author_email="test@example.com")
        yield repo


class TestPrivacyBudget:
    """Test PrivacyBudget dataclass."""

    def test_budget_creation(self):
        """Test creating a privacy budget."""
        from memvcs.core.compliance import PrivacyBudget

        budget = PrivacyBudget(epsilon=0.1, delta=1e-5, budget_limit=1.0)
        assert budget.epsilon == 0.1
        assert budget.remaining() == 1.0

    def test_consume_budget(self):
        """Test consuming privacy budget."""
        from memvcs.core.compliance import PrivacyBudget

        budget = PrivacyBudget(epsilon=0.1, delta=1e-5, budget_limit=1.0)

        result = budget.consume(0.3)
        assert result is True
        assert budget.remaining() == 0.7
        assert budget.queries_made == 1

    def test_budget_exhaustion(self):
        """Test budget exhaustion."""
        from memvcs.core.compliance import PrivacyBudget

        budget = PrivacyBudget(epsilon=0.1, delta=1e-5, budget_limit=0.5)
        budget.consume(0.5)

        assert budget.is_exhausted() is True
        assert budget.consume(0.1) is False


class TestPrivacyManager:
    """Test PrivacyManager class."""

    def test_create_budget(self, test_repo):
        """Test creating a privacy budget."""
        from memvcs.core.compliance import PrivacyManager

        mgr = PrivacyManager(test_repo.mem_dir)
        budget = mgr.create_budget("user_data", epsilon=0.1, delta=1e-5)

        assert budget.epsilon == 0.1

    def test_consume_budget(self, test_repo):
        """Test consuming from a budget."""
        from memvcs.core.compliance import PrivacyManager

        mgr = PrivacyManager(test_repo.mem_dir)
        mgr.create_budget("user_data", limit=1.0)

        success, budget = mgr.consume("user_data", 0.3)
        assert success is True
        assert budget.remaining() == pytest.approx(0.7)

    def test_get_dashboard_data(self, test_repo):
        """Test getting dashboard data."""
        from memvcs.core.compliance import PrivacyManager

        mgr = PrivacyManager(test_repo.mem_dir)
        mgr.create_budget("source1", limit=1.0)
        mgr.create_budget("source2", limit=2.0)

        data = mgr.get_dashboard_data()
        assert len(data["budgets"]) == 2


class TestEncryptionVerifier:
    """Test EncryptionVerifier class."""

    def test_check_unencrypted_file(self, test_repo):
        """Test checking an unencrypted file."""
        from memvcs.core.compliance import EncryptionVerifier

        # Create test file
        test_file = test_repo.current_dir / "test.txt"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("Hello World")

        verifier = EncryptionVerifier(test_repo.mem_dir, test_repo.current_dir)
        status = verifier.check_file(test_file)

        assert status.is_encrypted is False

    def test_scan_directory(self, test_repo):
        """Test scanning a directory."""
        from memvcs.core.compliance import EncryptionVerifier

        # Create test files
        (test_repo.current_dir / "episodic").mkdir(parents=True, exist_ok=True)
        (test_repo.current_dir / "episodic" / "test.md").write_text("Test content")

        verifier = EncryptionVerifier(test_repo.mem_dir, test_repo.current_dir)
        results = verifier.scan_directory()

        assert "total" in results
        assert "encryption_coverage" in results


class TestTamperDetector:
    """Test TamperDetector class."""

    def test_compute_file_hash(self, test_repo):
        """Test computing file hash."""
        from memvcs.core.compliance import TamperDetector

        # Create test file
        test_file = test_repo.current_dir / "test.txt"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("Hello World")

        detector = TamperDetector(test_repo.mem_dir)
        hash_value = detector.compute_file_hash(test_file)

        assert len(hash_value) == 64  # SHA-256 hex

    def test_store_and_verify(self, test_repo):
        """Test storing and verifying Merkle state."""
        from memvcs.core.compliance import TamperDetector

        # Create test files
        (test_repo.current_dir / "episodic").mkdir(parents=True, exist_ok=True)
        (test_repo.current_dir / "episodic" / "test.md").write_text("Test content")

        detector = TamperDetector(test_repo.mem_dir)
        state = detector.store_merkle_state(test_repo.current_dir)

        assert "merkle_root" in state
        assert state["file_count"] >= 1

        # Verify unchanged
        result = detector.verify_integrity(test_repo.current_dir)
        assert result["verified"] is True

    def test_detect_modification(self, test_repo):
        """Test detecting file modification."""
        from memvcs.core.compliance import TamperDetector

        # Create test file and store state
        (test_repo.current_dir / "episodic").mkdir(parents=True, exist_ok=True)
        test_file = test_repo.current_dir / "episodic" / "test.md"
        test_file.write_text("Original")

        detector = TamperDetector(test_repo.mem_dir)
        detector.store_merkle_state(test_repo.current_dir)

        # Modify file
        test_file.write_text("Modified")

        # Verify should detect change
        result = detector.verify_integrity(test_repo.current_dir)
        assert result["verified"] is False
        assert len(result["modified_files"]) >= 1


class TestAuditAnalyzer:
    """Test AuditAnalyzer class."""

    def test_empty_audit(self, test_repo):
        """Test with no audit entries."""
        from memvcs.core.compliance import AuditAnalyzer

        analyzer = AuditAnalyzer(test_repo.mem_dir)
        result = analyzer.verify_chain()

        assert result["valid"] is True
        assert result["entries"] == 0

    def test_get_statistics(self, test_repo):
        """Test getting audit statistics."""
        from memvcs.core.compliance import AuditAnalyzer

        # Create some audit entries
        audit_file = test_repo.mem_dir / "audit.log"
        entries = [
            {"operation": "commit", "agent": "agent-1", "timestamp": "2024-01-01T10:00:00Z"},
            {"operation": "commit", "agent": "agent-1", "timestamp": "2024-01-01T11:00:00Z"},
            {"operation": "read", "agent": "agent-2", "timestamp": "2024-01-01T12:00:00Z"},
        ]
        audit_file.write_text("\n".join(json.dumps(e) for e in entries))

        analyzer = AuditAnalyzer(test_repo.mem_dir)
        stats = analyzer.get_statistics()

        assert stats["total_entries"] == 3
        assert stats["operations"]["commit"] == 2


class TestComplianceDashboard:
    """Test compliance dashboard helper."""

    def test_get_compliance_dashboard(self, test_repo):
        """Test getting full compliance dashboard."""
        from memvcs.core.compliance import get_compliance_dashboard

        # Create some test data
        (test_repo.current_dir / "episodic").mkdir(parents=True, exist_ok=True)
        (test_repo.current_dir / "episodic" / "test.md").write_text("Test")

        dashboard = get_compliance_dashboard(test_repo.mem_dir, test_repo.current_dir)

        assert "privacy" in dashboard
        assert "encryption" in dashboard
        assert "integrity" in dashboard
        assert "audit" in dashboard
