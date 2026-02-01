"""Tests for temporal index - date to commit resolution."""

import tempfile
import unittest
from pathlib import Path

from memvcs.core.repository import Repository
from memvcs.core.temporal_index import TemporalIndex, _parse_iso_timestamp


class TestParseIsoTimestamp(unittest.TestCase):
    """Test ISO timestamp parsing."""

    def test_parse_iso_date(self):
        dt = _parse_iso_timestamp("2025-12-01")
        assert dt is not None
        assert dt.year == 2025
        assert dt.month == 12
        assert dt.day == 1

    def test_parse_iso_datetime_z(self):
        dt = _parse_iso_timestamp("2025-12-01T14:00:00Z")
        assert dt is not None
        assert dt.hour == 14

    def test_parse_empty_returns_none(self):
        assert _parse_iso_timestamp("") is None
        assert _parse_iso_timestamp("   ") is None

    def test_parse_invalid_returns_none(self):
        assert _parse_iso_timestamp("not-a-date") is None


class TestTemporalIndexResolveAt(unittest.TestCase):
    """Test resolve_at with real repo."""

    def test_resolve_at_returns_commit_before_or_at_time(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            (repo.current_dir / "semantic" / "prefs.md").write_text("prefs")
            repo.stage_file("semantic/prefs.md")
            repo.commit("Initial")
            head_hash = repo.refs.get_branch_commit("main")
            ti = TemporalIndex(repo.mem_dir, repo.object_store)
            # Resolve at a time in the future - should return current HEAD
            resolved = ti.resolve_at("2030-01-01T00:00:00Z")
            assert resolved == head_hash

    def test_resolve_at_past_returns_none_when_no_commits(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            ti = TemporalIndex(repo.mem_dir, repo.object_store)
            resolved = ti.resolve_at("2020-01-01")
            assert resolved is None
