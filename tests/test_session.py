"""
Tests for Session-Aware Auto-Commit.
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


class TestSessionConfig:
    """Test SessionConfig class."""

    def test_default_config(self):
        """Test default configuration values."""
        from memvcs.core.session import SessionConfig

        config = SessionConfig()
        assert config.idle_timeout_seconds == 300
        assert config.max_observations_per_commit == 50
        assert config.use_llm_messages is True


class TestTopicClassifier:
    """Test TopicClassifier class."""

    def test_classify_file_operations(self):
        """Test classification of file operations."""
        from memvcs.core.session import TopicClassifier

        classifier = TopicClassifier()
        assert classifier.classify("write_file", {}) == "file_operations"
        assert classifier.classify("read_file", {}) == "file_operations"
        assert classifier.classify("delete_file", {}) == "file_operations"

    def test_classify_git_operations(self):
        """Test classification of git operations."""
        from memvcs.core.session import TopicClassifier

        classifier = TopicClassifier()
        assert classifier.classify("git_commit", {}) == "git_operations"
        assert classifier.classify("git_push", {}) == "git_operations"

    def test_classify_from_arguments(self):
        """Test classification from argument values."""
        from memvcs.core.session import TopicClassifier

        classifier = TopicClassifier()
        # Should detect "test" in arguments
        assert classifier.classify("run_command", {"cmd": "pytest test_file.py"}) == "testing"

    def test_classify_general(self):
        """Test fallback to general topic."""
        from memvcs.core.session import TopicClassifier

        classifier = TopicClassifier()
        assert classifier.classify("some_random_tool", {}) == "general"


class TestSession:
    """Test Session class."""

    def test_session_create(self):
        """Test creating a session."""
        from memvcs.core.session import Session

        session = Session(
            id="test-123",
            started_at="2024-01-01T10:00:00Z",
        )
        assert session.id == "test-123"
        assert session.status == "active"
        assert len(session.observations) == 0

    def test_session_roundtrip(self):
        """Test session serialization/deserialization."""
        from memvcs.core.session import Session, Observation

        session = Session(
            id="test-123",
            started_at="2024-01-01T10:00:00Z",
            observations=[
                Observation(
                    id="obs-1",
                    timestamp="2024-01-01T10:05:00Z",
                    tool_name="write_file",
                    arguments={"path": "test.txt"},
                )
            ],
            topics={"file_operations": ["obs-1"]},
        )

        data = session.to_dict()
        session2 = Session.from_dict(data)

        assert session.id == session2.id
        assert len(session.observations) == len(session2.observations)
        assert session.topics == session2.topics


class TestSessionManager:
    """Test SessionManager class."""

    def test_start_session(self, test_repo):
        """Test starting a new session."""
        from memvcs.core.session import SessionManager

        manager = SessionManager(test_repo.root)
        session = manager.start_session(project_context="Test project")

        assert session is not None
        assert session.status == "active"
        assert session.project_context == "Test project"

    def test_add_observation(self, test_repo):
        """Test adding observations."""
        from memvcs.core.session import SessionManager

        manager = SessionManager(test_repo.root)
        manager.start_session()

        obs_id = manager.add_observation(
            tool_name="write_file",
            arguments={"path": "test.txt", "content": "hello"},
            result="success",
        )

        assert obs_id is not None
        assert len(manager.session.observations) == 1
        assert "file_operations" in manager.session.topics

    def test_session_persistence(self, test_repo):
        """Test session persistence across manager instances."""
        from memvcs.core.session import SessionManager

        # Create session
        manager1 = SessionManager(test_repo.root)
        session = manager1.start_session()
        session_id = session.id
        manager1.add_observation("write_file", {"path": "a.txt"})

        # New manager should load same session
        manager2 = SessionManager(test_repo.root)
        assert manager2.session is not None
        assert manager2.session.id == session_id
        assert len(manager2.session.observations) == 1

    def test_end_session(self, test_repo):
        """Test ending a session."""
        from memvcs.core.session import SessionManager

        manager = SessionManager(test_repo.root)
        manager.start_session()
        manager.add_observation("write_file", {"path": "test.txt"})

        commit_hash = manager.end_session(commit=True)

        assert manager.session.status == "ended"
        assert manager.session.ended_at is not None
        # Commit should have happened
        assert commit_hash is not None

    def test_pause_resume_session(self, test_repo):
        """Test pausing and resuming a session."""
        from memvcs.core.session import SessionManager

        manager = SessionManager(test_repo.root)
        manager.start_session()

        manager.pause_session()
        assert manager.session.status == "paused"

        manager.resume_session()
        assert manager.session.status == "active"

    def test_discard_session(self, test_repo):
        """Test discarding a session."""
        from memvcs.core.session import SessionManager

        manager = SessionManager(test_repo.root)
        manager.start_session()
        manager.add_observation("write_file", {"path": "test.txt"})

        manager.discard_session()
        assert manager._session is None
        assert not manager.session_file.exists()

    def test_get_status(self, test_repo):
        """Test getting session status."""
        from memvcs.core.session import SessionManager

        manager = SessionManager(test_repo.root)
        manager.start_session()
        manager.add_observation("write_file", {"path": "test.txt"})

        status = manager.get_status()
        assert status["active"] is True
        assert status["observation_count"] == 1
        assert "file_operations" in status["topics"]


class TestCLIHelpers:
    """Test CLI helper functions."""

    def test_session_start(self, test_repo):
        """Test session_start helper."""
        from memvcs.core.session import session_start

        status = session_start(test_repo.root, context="CLI test")
        assert status["active"] is True

    def test_session_status(self, test_repo):
        """Test session_status helper."""
        from memvcs.core.session import session_start, session_status

        session_start(test_repo.root)
        status = session_status(test_repo.root)
        assert "session_id" in status

    def test_session_discard(self, test_repo):
        """Test session_discard helper."""
        from memvcs.core.session import session_start, session_discard, session_status

        session_start(test_repo.root)
        result = session_discard(test_repo.root)
        assert result["discarded"] is True

        status = session_status(test_repo.root)
        assert status["active"] is False
