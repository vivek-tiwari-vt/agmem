"""Tests for commit --importance and importance scoring."""

import tempfile
import unittest
from pathlib import Path

from memvcs.core.repository import Repository
from memvcs.core.objects import Commit
from memvcs.core.hooks import compute_suggested_importance


class TestCommitImportance(unittest.TestCase):
    """Test commit stores importance in metadata."""

    def test_commit_metadata_includes_importance(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            (repo.current_dir / "semantic" / "prefs.md").write_text("prefs")
            repo.stage_file("semantic/prefs.md")
            commit_hash = repo.commit("Learned prefs", {"importance": 0.9})
            commit = Commit.load(repo.object_store, commit_hash)
            assert commit is not None
            assert commit.metadata.get("importance") == 0.9

    def test_compute_suggested_importance_important_message(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            score = compute_suggested_importance(repo, {}, "IMPORTANT: remember this", {})
            assert score == 0.8

    def test_compute_suggested_importance_remember_message(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            score = compute_suggested_importance(repo, {}, "remember this for later", {})
            assert score == 0.7

    def test_compute_suggested_importance_auto_commit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            score = compute_suggested_importance(repo, {}, "auto", {"auto_commit": True})
            assert score == 0.5

    def test_compute_suggested_importance_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            score = compute_suggested_importance(repo, {}, "normal message", {})
            assert score == 0.5
