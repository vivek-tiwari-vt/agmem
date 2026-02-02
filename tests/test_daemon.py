"""
Tests for the Real-Time Observation Daemon.
"""

import json
import os
import pytest
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from memvcs.core.repository import Repository


class TestObservation:
    """Test Observation dataclass."""

    def test_observation_create(self):
        """Test creating an observation."""
        from memvcs.core.daemon import Observation

        obs = Observation(
            id="test-123",
            timestamp="2024-01-01T12:00:00Z",
            tool_name="write_file",
            arguments={"path": "test.txt"},
            result="File written",
            memory_type="episodic",
            summary="write_file path=test.txt",
        )

        assert obs.id == "test-123"
        assert obs.tool_name == "write_file"
        assert obs.memory_type == "episodic"

    def test_observation_to_dict_roundtrip(self):
        """Test observation serialization/deserialization."""
        from memvcs.core.daemon import Observation

        obs = Observation(
            id="test-123",
            timestamp="2024-01-01T12:00:00Z",
            tool_name="read_file",
            arguments={"path": "config.json"},
            result='{"key": "value"}',
            memory_type="semantic",
        )

        data = obs.to_dict()
        obs2 = Observation.from_dict(data)

        assert obs.id == obs2.id
        assert obs.tool_name == obs2.tool_name
        assert obs.memory_type == obs2.memory_type
        assert obs.result == obs2.result


class TestObservationExtractor:
    """Test ObservationExtractor class."""

    def test_classify_episodic_tools(self):
        """Test classification of episodic tools."""
        from memvcs.core.daemon import ObservationExtractor

        extractor = ObservationExtractor()

        assert extractor.classify_memory_type("run_command") == "episodic"
        assert extractor.classify_memory_type("write_file") == "episodic"
        assert extractor.classify_memory_type("delete_file") == "episodic"
        assert extractor.classify_memory_type("git_commit") == "episodic"
        assert extractor.classify_memory_type("deploy_app") == "episodic"

    def test_classify_semantic_tools(self):
        """Test classification of semantic tools."""
        from memvcs.core.daemon import ObservationExtractor

        extractor = ObservationExtractor()

        assert extractor.classify_memory_type("search_web") == "semantic"
        assert extractor.classify_memory_type("read_file") == "semantic"
        assert extractor.classify_memory_type("fetch_url") == "semantic"
        assert extractor.classify_memory_type("query_database") == "semantic"
        assert extractor.classify_memory_type("memory_search") == "semantic"

    def test_classify_procedural_tools(self):
        """Test classification of procedural tools."""
        from memvcs.core.daemon import ObservationExtractor

        extractor = ObservationExtractor()

        assert extractor.classify_memory_type("generate_code") == "procedural"
        assert extractor.classify_memory_type("refactor_class") == "procedural"
        assert extractor.classify_memory_type("setup_project") == "procedural"
        assert extractor.classify_memory_type("configure_ci") == "procedural"

    def test_should_capture_normal_tools(self):
        """Test that normal tools are captured."""
        from memvcs.core.daemon import ObservationExtractor

        extractor = ObservationExtractor()

        assert extractor.should_capture("write_file", "File content" * 20)
        assert extractor.should_capture("run_command", "Command output" * 10)

    def test_should_ignore_trivial_tools(self):
        """Test that trivial tools are ignored."""
        from memvcs.core.daemon import ObservationExtractor

        extractor = ObservationExtractor()

        assert not extractor.should_capture("echo", "hello")
        assert not extractor.should_capture("pwd", "/home/user")
        assert not extractor.should_capture("whoami", "user")

    def test_should_ignore_short_results(self):
        """Test that short results are ignored."""
        from memvcs.core.daemon import ObservationExtractor

        extractor = ObservationExtractor(min_content_length=50)

        assert not extractor.should_capture("some_tool", "short")

    def test_extract_observation(self):
        """Test extracting an observation from a tool call."""
        from memvcs.core.daemon import ObservationExtractor

        extractor = ObservationExtractor()

        obs = extractor.extract(
            tool_name="write_file",
            arguments={"path": "/tmp/test.txt", "content": "hello world"},
            result="File written successfully" * 5,
        )

        assert obs is not None
        assert obs.tool_name == "write_file"
        assert obs.memory_type == "episodic"
        assert "path=/tmp/test.txt" in obs.summary


class TestAutoStagingEngine:
    """Test AutoStagingEngine class."""

    def test_stage_observation(self):
        """Test staging an observation to disk."""
        from memvcs.core.daemon import AutoStagingEngine, Observation

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "current").mkdir()

            stager = AutoStagingEngine(repo_root)

            obs = Observation(
                id="test-123",
                timestamp="2024-01-15T10:30:00+00:00",
                tool_name="write_file",
                arguments={"path": "test.txt"},
                result="File written",
                memory_type="episodic",
            )

            filepath = stager.stage_observation(obs)

            assert filepath.exists()
            assert "episodic" in str(filepath)
            assert "2024-01-15" in str(filepath)

            content = filepath.read_text()
            assert "write_file" in content
            assert "schema_version: \"1.0\"" in content

    def test_stage_semantic_observation(self):
        """Test staging a semantic observation."""
        from memvcs.core.daemon import AutoStagingEngine, Observation

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "current").mkdir()

            stager = AutoStagingEngine(repo_root)

            obs = Observation(
                id="test-456",
                timestamp="2024-01-15T10:30:00+00:00",
                tool_name="search_web",
                arguments={"query": "python best practices"},
                result="Search results",
                memory_type="semantic",
            )

            filepath = stager.stage_observation(obs)

            assert filepath.exists()
            assert "semantic" in str(filepath)


class TestCommitMessageGenerator:
    """Test CommitMessageGenerator class."""

    def test_generate_template_single_tool(self):
        """Test template generation for a single tool."""
        from memvcs.core.daemon import CommitMessageGenerator, Observation

        gen = CommitMessageGenerator(use_llm=False)

        observations = [
            Observation(
                id="1",
                timestamp="2024-01-01T12:00:00Z",
                tool_name="write_file",
                arguments={},
                memory_type="episodic",
                summary="write_file test.txt",
            )
        ]

        message = gen.generate(observations)

        assert "Auto-commit" in message
        assert "write_file" in message

    def test_generate_template_multiple_tools(self):
        """Test template generation for multiple tools."""
        from memvcs.core.daemon import CommitMessageGenerator, Observation

        gen = CommitMessageGenerator(use_llm=False)

        observations = [
            Observation(
                id="1",
                timestamp="2024-01-01T12:00:00Z",
                tool_name="write_file",
                arguments={},
                memory_type="episodic",
            ),
            Observation(
                id="2",
                timestamp="2024-01-01T12:01:00Z",
                tool_name="run_command",
                arguments={},
                memory_type="episodic",
            ),
            Observation(
                id="3",
                timestamp="2024-01-01T12:02:00Z",
                tool_name="search_web",
                arguments={},
                memory_type="semantic",
            ),
        ]

        message = gen.generate(observations)

        assert "3 observations" in message
        assert "3 tools" in message


class TestSessionState:
    """Test SessionState class."""

    def test_session_state_roundtrip(self):
        """Test session state serialization."""
        from memvcs.core.daemon import SessionState, Observation

        session = SessionState(
            session_id="sess-123",
            started_at="2024-01-01T10:00:00Z",
            observations=[
                Observation(
                    id="obs-1",
                    timestamp="2024-01-01T10:05:00Z",
                    tool_name="test_tool",
                    arguments={"arg": "value"},
                )
            ],
            commit_count=5,
        )

        data = session.to_dict()
        session2 = SessionState.from_dict(data)

        assert session.session_id == session2.session_id
        assert session.commit_count == session2.commit_count
        assert len(session.observations) == len(session2.observations)


class TestObservationDaemon:
    """Test ObservationDaemon class."""

    def test_daemon_lifecycle(self):
        """Test daemon start/stop lifecycle."""
        from memvcs.core.daemon import ObservationDaemon

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            Repository.init(repo_root)

            daemon = ObservationDaemon(repo_root)

            # Start
            daemon.start()
            assert daemon._running
            assert daemon.session is not None

            status = daemon.get_status()
            assert status["running"]
            assert status["session_id"] is not None

            # Stop
            daemon.stop()
            assert not daemon._running

    def test_add_observation(self):
        """Test adding observations to daemon."""
        from memvcs.core.daemon import ObservationDaemon

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            Repository.init(repo_root)

            daemon = ObservationDaemon(repo_root)
            daemon.start()

            try:
                obs_id = daemon.add_observation(
                    tool_name="write_file",
                    arguments={"path": "test.txt"},
                    result="Success" * 20,
                )

                assert obs_id is not None
                assert len(daemon.session.observations) == 1
            finally:
                daemon.stop()

    def test_session_persistence(self):
        """Test that session is persisted across restarts."""
        from memvcs.core.daemon import ObservationDaemon

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            Repository.init(repo_root)

            # First daemon instance
            daemon1 = ObservationDaemon(repo_root)
            daemon1.start()
            daemon1.add_observation("write_file", {"path": "a.txt"}, "x" * 100)
            session_id = daemon1.session.session_id

            # Stop and save without committing
            daemon1._save_session()
            daemon1._running = False

            # New daemon instance should recover session
            daemon2 = ObservationDaemon(repo_root)
            loaded = daemon2._load_session()

            assert loaded is not None
            assert loaded.session_id == session_id
            assert len(loaded.observations) == 1


class TestMCPIntegration:
    """Test MCP server observation capture integration."""

    def test_capture_observation_function(self):
        """Test the capture_observation function."""
        from memvcs.core.daemon import initialize_daemon, get_daemon, capture_observation

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            Repository.init(repo_root)

            daemon = initialize_daemon(repo_root)
            daemon.start()

            try:
                obs_id = capture_observation(
                    tool_name="memory_search",
                    arguments={"query": "test"},
                    result="Found results" * 10,
                )

                assert obs_id is not None
                assert get_daemon() is daemon
            finally:
                daemon.stop()
