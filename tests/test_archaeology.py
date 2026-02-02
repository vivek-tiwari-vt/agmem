"""
Tests for Memory Archaeology features.
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


class TestMemoryEvolution:
    """Test MemoryEvolution dataclass."""

    def test_evolution_create(self):
        """Test creating a memory evolution record."""
        from memvcs.core.archaeology import MemoryEvolution

        evolution = MemoryEvolution(
            path="episodic/session.md",
            first_seen="2024-01-01T10:00:00Z",
            last_modified="2024-01-10T15:00:00Z",
            version_count=5,
            commits=["abc", "def", "ghi"],
            size_history=[("2024-01-01", 100), ("2024-01-05", 200)],
        )

        assert evolution.version_count == 5

    def test_evolution_to_dict(self):
        """Test evolution serialization."""
        from memvcs.core.archaeology import MemoryEvolution

        evolution = MemoryEvolution(
            path="test.md",
            first_seen="2024-01-01",
            last_modified="2024-01-10",
            version_count=3,
            commits=["a", "b", "c"],
            size_history=[],
        )

        data = evolution.to_dict()
        assert data["path"] == "test.md"
        assert len(data["commits"]) == 3


class TestHistoryExplorer:
    """Test HistoryExplorer class."""

    def test_get_file_history(self, test_repo):
        """Test getting file history."""
        from memvcs.core.archaeology import HistoryExplorer

        # Create and commit a file
        (test_repo.current_dir / "episodic").mkdir(parents=True, exist_ok=True)
        test_file = test_repo.current_dir / "episodic" / "test.md"
        test_file.write_text("Test content")
        test_repo.stage_file("episodic/test.md")
        test_repo.commit("Initial commit")

        explorer = HistoryExplorer(test_repo.root)
        history = explorer.get_file_history("episodic/test.md")

        assert len(history) >= 1


class TestForgottenKnowledgeFinder:
    """Test ForgottenKnowledgeFinder class."""

    def test_find_forgotten(self, test_repo):
        """Test finding forgotten memories."""
        from memvcs.core.archaeology import ForgottenKnowledgeFinder

        # Create test files
        (test_repo.current_dir / "episodic").mkdir(parents=True, exist_ok=True)
        (test_repo.current_dir / "episodic" / "test.md").write_text("Test content")

        finder = ForgottenKnowledgeFinder(test_repo.root)
        forgotten = finder.find_forgotten(days_threshold=0, limit=10)

        # Should find at least the test file
        assert isinstance(forgotten, list)

    def test_rediscover_relevant(self, test_repo):
        """Test finding relevant forgotten memories."""
        from memvcs.core.archaeology import ForgottenKnowledgeFinder

        # Create test files
        (test_repo.current_dir / "episodic").mkdir(parents=True, exist_ok=True)
        (test_repo.current_dir / "episodic" / "python.md").write_text("Python programming guide")

        finder = ForgottenKnowledgeFinder(test_repo.root)
        relevant = finder.rediscover_relevant("python", days_threshold=0)

        assert isinstance(relevant, list)


class TestPatternAnalyzer:
    """Test PatternAnalyzer class."""

    def test_analyze_patterns(self, test_repo):
        """Test analyzing activity patterns."""
        from memvcs.core.archaeology import PatternAnalyzer

        # Create some commits
        (test_repo.current_dir / "episodic").mkdir(parents=True, exist_ok=True)
        for i in range(5):
            test_file = test_repo.current_dir / "episodic" / f"test{i}.md"
            test_file.write_text(f"Test {i}")
            test_repo.stage_file(f"episodic/test{i}.md")
            test_repo.commit(f"Commit {i}")

        analyzer = PatternAnalyzer(test_repo.root)
        patterns = analyzer.analyze_activity_patterns(days=90)

        assert isinstance(patterns, list)


class TestContextReconstructor:
    """Test ContextReconstructor class."""

    def test_reconstruct_context(self, test_repo):
        """Test reconstructing context."""
        from memvcs.core.archaeology import ContextReconstructor

        # Create commit
        (test_repo.current_dir / "episodic").mkdir(parents=True, exist_ok=True)
        (test_repo.current_dir / "episodic" / "test.md").write_text("Test")
        test_repo.stage_file("episodic/test.md")
        test_repo.commit("Test commit")

        reconstructor = ContextReconstructor(test_repo.root)
        context = reconstructor.reconstruct_context(
            "episodic/test.md",
            "2024-01-01T10:00:00Z",
            window_days=30,
        )

        assert "target_path" in context


class TestArchaeologyDashboard:
    """Test archaeology dashboard helper."""

    def test_get_archaeology_dashboard(self, test_repo):
        """Test getting dashboard data."""
        from memvcs.core.archaeology import get_archaeology_dashboard

        # Create test data
        (test_repo.current_dir / "episodic").mkdir(parents=True, exist_ok=True)
        (test_repo.current_dir / "episodic" / "test.md").write_text("Test")

        dashboard = get_archaeology_dashboard(test_repo.root)

        assert "forgotten_memories" in dashboard
        assert "activity_patterns" in dashboard
