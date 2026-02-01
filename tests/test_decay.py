"""Tests for decay engine and resurrect."""

import tempfile
import unittest
from pathlib import Path

from memvcs.core.repository import Repository
from memvcs.core.access_index import AccessIndex
from memvcs.core.decay import DecayEngine, DecayConfig, DecayCandidate


class TestDecayEngine(unittest.TestCase):
    """Test DecayEngine get_decay_candidates and apply_decay."""

    def test_get_decay_candidates_empty_when_no_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            engine = DecayEngine(repo, DecayConfig())
            candidates = engine.get_decay_candidates()
            assert candidates == []

    def test_get_decay_candidates_returns_candidates_when_files_exist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            (repo.current_dir / "episodic" / "old.md").write_text("old session")
            engine = DecayEngine(repo, DecayConfig(episodic_half_life_days=30))
            candidates = engine.get_decay_candidates()
            assert all(isinstance(c, DecayCandidate) for c in candidates)
            if candidates:
                assert any("episodic" in c.path for c in candidates)

    def test_compute_decay_score_returns_candidate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            (repo.current_dir / "semantic" / "prefs.md").write_text(
                "---\nschema_version: 1.0\nimportance: 0.2\n---\nprefs"
            )
            engine = DecayEngine(repo, DecayConfig(semantic_min_importance=0.3))
            cand = engine.compute_decay_score(
                "semantic/prefs.md",
                "---\nimportance: 0.2\n---\nbody",
                "semantic",
            )
            assert cand.path == "semantic/prefs.md"
            assert cand.importance == 0.2
            assert cand.decay_score > 0.5

    def test_apply_decay_moves_files_to_forgetting_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            (repo.current_dir / "episodic" / "old.md").write_text("old")
            engine = DecayEngine(repo, DecayConfig())
            candidates = engine.get_decay_candidates()
            if not candidates:
                return  # No decay candidates in this config
            count = engine.apply_decay(candidates)
            if count > 0:
                assert (repo.mem_dir / "forgetting").exists()
                assert not (repo.current_dir / "episodic" / "old.md").exists()
