"""Tests for retrieval module - recall strategies and engine."""

import tempfile
import unittest
from pathlib import Path

from memvcs.core.repository import Repository
from memvcs.core.access_index import AccessIndex
from memvcs.retrieval import RecallEngine, RecallResult
from memvcs.retrieval.strategies import RecencyStrategy, ImportanceStrategy, _matches_exclude


class TestMatchesExclude(unittest.TestCase):
    """Test exclude pattern matching."""

    def test_empty_exclude_matches_nothing(self):
        assert _matches_exclude("semantic/prefs.md", []) is False

    def test_exact_pattern(self):
        assert _matches_exclude("experiment/foo.md", ["experiment/*"]) is True
        assert _matches_exclude("semantic/prefs.md", ["experiment/*"]) is False

    def test_path_with_slash(self):
        # */pattern matches path with slash
        assert _matches_exclude("semantic/prefs.md", ["*/prefs.md"]) is True
        assert _matches_exclude("semantic/prefs.md", ["other.md"]) is False


class TestRecallResult:
    """Test RecallResult dataclass."""

    def test_to_dict_serializable(self):
        r = RecallResult(
            path="p.md",
            content="c",
            relevance_score=0.8,
            source={"commit_hash": "abc"},
            importance=0.9,
        )
        d = r.to_dict()
        assert d["path"] == "p.md"
        assert d["relevance_score"] == 0.8
        assert d["importance"] == 0.9


class TestRecencyStrategy(unittest.TestCase):
    """Test RecencyStrategy recall."""

    def test_recall_returns_files_sorted_newest_first(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            (repo.current_dir / "semantic" / "a.md").write_text("a")
            (repo.current_dir / "semantic" / "b.md").write_text("b")
            strategy = RecencyStrategy(repo)
            results = strategy.recall(context="", limit=10, exclude=[])
            assert len(results) == 2
            assert all(isinstance(r, RecallResult) for r in results)
            assert all(r.path.startswith("semantic/") for r in results)

    def test_recall_respects_exclude(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            (repo.current_dir / "semantic" / "prefs.md").write_text("prefs")
            (repo.current_dir / "experiment").mkdir(exist_ok=True)
            (repo.current_dir / "experiment" / "x.md").write_text("x")
            strategy = RecencyStrategy(repo)
            results = strategy.recall(context="", limit=10, exclude=["experiment/*"])
            paths = [r.path for r in results]
            assert "semantic/prefs.md" in paths
            assert not any("experiment" in p for p in paths)

    def test_recall_respects_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            for i in range(5):
                (repo.current_dir / "semantic" / f"f{i}.md").write_text(str(i))
            strategy = RecencyStrategy(repo)
            results = strategy.recall(context="", limit=2, exclude=[])
            assert len(results) == 2


class TestImportanceStrategy:
    """Test ImportanceStrategy recall."""

    def test_recall_returns_results_from_head_tree(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            (repo.current_dir / "semantic" / "prefs.md").write_text(
                "---\nschema_version: 1.0\n---\nprefs"
            )
            repo.stage_file("semantic/prefs.md")
            repo.commit("Initial", {"importance": 0.8})
            strategy = ImportanceStrategy(repo)
            results = strategy.recall(context="", limit=10, exclude=[])
            assert len(results) >= 1
            assert any(r.path == "semantic/prefs.md" for r in results)


class TestRecallEngine(unittest.TestCase):
    """Test RecallEngine orchestration."""

    def test_recall_hybrid_falls_back_to_recency_without_vector(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            (repo.current_dir / "semantic" / "a.md").write_text("content")
            access = AccessIndex(repo.mem_dir)
            engine = RecallEngine(
                repo=repo, vector_store=None, access_index=access, use_cache=False
            )
            results = engine.recall(context="task", limit=5, strategy="hybrid", exclude=[])
            assert len(results) >= 1
            assert results[0].path == "semantic/a.md"

    def test_recall_recency_strategy_no_vector_needed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            (repo.current_dir / "semantic" / "prefs.md").write_text("prefs")
            engine = RecallEngine(repo=repo, vector_store=None, access_index=None, use_cache=False)
            results = engine.recall(context="", limit=10, strategy="recency", exclude=[])
            assert len(results) == 1
            assert results[0].path == "semantic/prefs.md"

    def test_recall_records_access_when_access_index_provided(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            (repo.current_dir / "semantic" / "x.md").write_text("x")
            repo.stage_file("semantic/x.md")
            repo.commit("C1")
            access = AccessIndex(repo.mem_dir)
            engine = RecallEngine(
                repo=repo, vector_store=None, access_index=access, use_cache=False
            )
            engine.recall(context="", limit=10, strategy="recency", exclude=[])
            assert access.get_access_count(path="semantic/x.md") == 1
