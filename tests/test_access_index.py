"""Tests for access index - recall access patterns and cache."""

import tempfile
import unittest
from pathlib import Path

from memvcs.core.access_index import AccessIndex, ACCESS_LOG_MAX


class TestAccessIndex(unittest.TestCase):
    """Test AccessIndex record_access, get_access_count, cache."""

    def test_init_creates_default_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            idx = AccessIndex(Path(tmpdir))
            data = idx._load()
            assert data["version"] == 1
            assert data["access_log"] == []
            assert "recall_cache" in data

    def test_record_access_appends_entry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            idx = AccessIndex(Path(tmpdir))
            idx.record_access("semantic/prefs.md", "abc123", "2026-01-31T12:00:00Z")
            count = idx.get_access_count(path="semantic/prefs.md")
            assert count == 1
            recent = idx.get_recent_accesses(limit=5)
            assert len(recent) == 1
            assert recent[0]["path"] == "semantic/prefs.md"
            assert recent[0]["commit"] == "abc123"

    def test_get_access_count_filters_by_path_and_commit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            idx = AccessIndex(Path(tmpdir))
            idx.record_access("a.md", "c1")
            idx.record_access("a.md", "c1")
            idx.record_access("b.md", "c1")
            assert idx.get_access_count(path="a.md") == 2
            assert idx.get_access_count(commit="c1") == 3
            assert idx.get_access_count(path="a.md", commit="c1") == 2

    def test_get_access_counts_by_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            idx = AccessIndex(Path(tmpdir))
            idx.record_access("semantic/x.md", "c1")
            idx.record_access("semantic/x.md", "c1")
            idx.record_access("episodic/y.md", "c1")
            counts = idx.get_access_counts_by_path()
            assert counts["semantic/x.md"] == 2
            assert counts["episodic/y.md"] == 1

    def test_cache_key_deterministic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            idx = AccessIndex(Path(tmpdir))
            k1 = idx.get_cache_key("ctx", "hybrid", 10, ["a", "b"])
            k2 = idx.get_cache_key("ctx", "hybrid", 10, ["b", "a"])
            assert k1 == k2

    def test_set_and_get_cached_recall(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            idx = AccessIndex(Path(tmpdir))
            results = [{"path": "p.md", "content": "c", "relevance_score": 0.9}]
            idx.set_cached_recall("ctx", "recency", 5, [], results)
            cached = idx.get_cached_recall("ctx", "recency", 5, [])
            assert cached is not None
            assert cached["results"] == results
            assert "cached_at" in cached
