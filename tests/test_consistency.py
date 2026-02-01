"""Tests for consistency checker and verify/repair."""

import tempfile
import unittest
from pathlib import Path

from memvcs.core.repository import Repository
from memvcs.core.consistency import (
    ConsistencyChecker,
    ConsistencyResult,
    Triple,
    Contradiction,
    INVERSE_PREDICATES,
)


class TestConsistencyChecker(unittest.TestCase):
    """Test ConsistencyChecker extract_triples and detect_contradictions."""

    def test_extract_triples_simple(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            checker = ConsistencyChecker(repo)
            content = "user prefers dark mode\nuser likes Python"
            triples = checker.extract_triples(content, "semantic/prefs.md", use_llm=False)
            assert len(triples) >= 1
            assert all(isinstance(t, Triple) for t in triples)

    def test_detect_contradictions_finds_inverse_predicates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            checker = ConsistencyChecker(repo)
            t1 = Triple("user", "likes", "Python", 0.8, "a.md", 1)
            t2 = Triple("user", "dislikes", "Python", 0.7, "b.md", 1)
            contradictions = checker.detect_contradictions([t1, t2])
            assert len(contradictions) == 1
            assert contradictions[0].reason

    def test_check_returns_result_with_files_checked(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            (repo.current_dir / "semantic" / "prefs.md").write_text(
                "---\nschema_version: 1.0\n---\nuser prefers dark mode"
            )
            checker = ConsistencyChecker(repo)
            result = checker.check(use_llm=False)
            assert isinstance(result, ConsistencyResult)
            assert result.files_checked >= 1
            assert isinstance(result.valid, bool)
