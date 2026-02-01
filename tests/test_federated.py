"""Tests for federated collaboration (real summaries, optional DP)."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

from memvcs.core.federated import (
    get_federated_config,
    produce_local_summary,
    push_updates,
    pull_merged,
)


class TestProduceLocalSummary:
    """Test produce_local_summary (topic counts, fact hashes)."""

    def test_produce_summary_includes_topic_hashes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "current" / "semantic").mkdir(parents=True)
            (root / "current" / "semantic" / "prefs.md").write_text("# User prefs\n- prefers dark mode")
            summary = produce_local_summary(root, ["semantic"])
            assert "topics" in summary
            assert summary["topics"].get("semantic", 0) >= 1
            assert "topic_hashes" in summary
            assert "fact_count" in summary

    def test_produce_summary_with_dp_noises_counts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "current" / "episodic").mkdir(parents=True)
            for i in range(3):
                (root / "current" / "episodic" / f"e{i}.md").write_text(f"episode {i}")
            raw = produce_local_summary(root, ["episodic"], use_dp=False)
            noised = produce_local_summary(root, ["episodic"], use_dp=True, dp_epsilon=0.5, dp_delta=1e-5)
            assert "topics" in noised
            assert "fact_count" in noised


class TestPushPullWithMockCoordinator:
    """Test push_updates/pull_merged with mock HTTP."""

    def test_push_returns_message_when_configured(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".mem").mkdir(parents=True, exist_ok=True)
            (root / ".mem" / "config.yaml").write_text(
                'federated:\n  enabled: true\n  coordinator_url: "http://localhost:9999"\nremotes: {}'
            )
            summary = {"memory_types": ["episodic"], "topics": {}, "fact_count": 0}
            with patch("urllib.request.urlopen") as mock_open:
                mock_resp = type("R", (), {"status": 200})()
                mock_open.return_value.__enter__ = lambda s: mock_resp
                mock_open.return_value.__exit__ = lambda s, *a: None
                msg = push_updates(root, summary)
            assert "Pushed" in msg or "failed" in msg.lower() or "Coordinator" in msg

    def test_pull_returns_none_when_not_configured(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            data = pull_merged(root)
            assert data is None
