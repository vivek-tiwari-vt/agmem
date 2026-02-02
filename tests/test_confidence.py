"""
Tests for Confidence Scoring features.
"""

import json
import math
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


class TestDecayModel:
    """Test DecayModel class."""

    def test_exponential_decay(self):
        """Test exponential decay calculation."""
        from memvcs.core.confidence import DecayModel

        model = DecayModel(model="exponential", half_life_days=30)

        # At t=0, decay should be 1.0
        assert model.calculate_decay(0) == 1.0

        # At t=half_life, decay should be ~0.5
        assert abs(model.calculate_decay(30) - 0.5) < 0.01

    def test_linear_decay(self):
        """Test linear decay calculation."""
        from memvcs.core.confidence import DecayModel

        model = DecayModel(model="linear", half_life_days=30)

        # At t=0, decay should be 1.0
        assert model.calculate_decay(0) == 1.0

        # At t=2*half_life, decay should be 0.0
        assert model.calculate_decay(60) == 0.0

    def test_days_until_threshold(self):
        """Test calculating days until threshold."""
        from memvcs.core.confidence import DecayModel

        model = DecayModel(model="exponential", half_life_days=30)

        days = model.days_until_threshold(1.0, 0.5)
        assert abs(days - 30) < 1  # Should be ~30 days


class TestSourceTracker:
    """Test SourceTracker class."""

    def test_register_source(self, test_repo):
        """Test registering a source."""
        from memvcs.core.confidence import SourceTracker

        tracker = SourceTracker(test_repo.mem_dir)
        source = tracker.register_source("agent-1", "Claude", initial_reliability=0.9)

        assert source["reliability"] == 0.9

    def test_get_reliability(self, test_repo):
        """Test getting source reliability."""
        from memvcs.core.confidence import SourceTracker

        tracker = SourceTracker(test_repo.mem_dir)
        tracker.register_source("agent-1", "Claude", initial_reliability=0.85)

        reliability = tracker.get_reliability("agent-1")
        assert reliability == 0.85

    def test_update_reliability(self, test_repo):
        """Test updating source reliability."""
        from memvcs.core.confidence import SourceTracker

        tracker = SourceTracker(test_repo.mem_dir)
        tracker.register_source("agent-1", "Claude", initial_reliability=0.8)

        new_reliability = tracker.update_reliability("agent-1", 0.1)
        assert new_reliability == 0.9

    def test_record_verification(self, test_repo):
        """Test recording verification."""
        from memvcs.core.confidence import SourceTracker

        tracker = SourceTracker(test_repo.mem_dir)
        tracker.register_source("agent-1", "Claude", initial_reliability=0.8)

        tracker.record_verification("agent-1", verified=True)
        assert tracker.get_reliability("agent-1") > 0.8

        tracker.record_verification("agent-1", verified=False)
        # Should decrease


class TestConfidenceCalculator:
    """Test ConfidenceCalculator class."""

    def test_calculate_score(self, test_repo):
        """Test calculating confidence score."""
        from memvcs.core.confidence import ConfidenceCalculator

        calculator = ConfidenceCalculator(test_repo.mem_dir)
        calculator.source_tracker.register_source("agent-1", "Claude", initial_reliability=0.9)

        score = calculator.calculate_score(
            path="episodic/test.md",
            source_id="agent-1",
            created_at="2024-01-01T10:00:00Z",
        )

        assert 0.0 <= score.score <= 1.0
        assert score.factors.source_reliability == 0.9

    def test_add_corroboration(self, test_repo):
        """Test adding corroboration."""
        from memvcs.core.confidence import ConfidenceCalculator

        calculator = ConfidenceCalculator(test_repo.mem_dir)
        calculator.calculate_score("test.md")
        calculator.add_corroboration("test.md")

        score = calculator.get_score("test.md")
        assert score.factors.corroboration_count >= 1

    def test_add_contradiction(self, test_repo):
        """Test adding contradiction."""
        from memvcs.core.confidence import ConfidenceCalculator

        calculator = ConfidenceCalculator(test_repo.mem_dir)
        calculator.calculate_score("test.md")
        calculator.add_contradiction("test.md")

        score = calculator.get_score("test.md")
        assert score.factors.contradiction_count >= 1

    def test_get_low_confidence(self, test_repo):
        """Test getting low confidence memories."""
        from memvcs.core.confidence import ConfidenceCalculator

        calculator = ConfidenceCalculator(test_repo.mem_dir)

        # Create a low confidence score
        calculator._scores["old.md"] = {
            "score": 0.3,
            "age_days": 100,
        }
        calculator._save()

        low = calculator.get_low_confidence_memories(threshold=0.5)
        assert len(low) >= 1
        assert low[0]["path"] == "old.md"


class TestConfidenceScore:
    """Test ConfidenceScore class."""

    def test_score_to_dict(self):
        """Test score serialization."""
        from memvcs.core.confidence import ConfidenceScore, ConfidenceFactors

        factors = ConfidenceFactors(
            source_reliability=0.9,
            corroboration_count=2,
            age_days=10,
        )

        score = ConfidenceScore(
            score=0.85,
            factors=factors,
            decay_rate=0.023,
            computed_at="2024-01-01T10:00:00Z",
        )

        data = score.to_dict()
        assert data["score"] == 0.85
        assert data["factors"]["source_reliability"] == 0.9


class TestConfidenceDashboard:
    """Test confidence dashboard helper."""

    def test_get_confidence_dashboard(self, test_repo):
        """Test getting dashboard data."""
        from memvcs.core.confidence import get_confidence_dashboard, ConfidenceCalculator

        # Create some test data
        calculator = ConfidenceCalculator(test_repo.mem_dir)
        calculator.calculate_score("test.md")

        dashboard = get_confidence_dashboard(test_repo.mem_dir)

        assert "low_confidence_count" in dashboard
        assert "expiring_soon_count" in dashboard
        assert "sources" in dashboard
