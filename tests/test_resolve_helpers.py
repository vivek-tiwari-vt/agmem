"""Tests for resolve command helpers (path safety, content resolution)."""

import pytest
import tempfile
from pathlib import Path

from memvcs.commands.resolve import _path_under_current, _resolved_content


class TestPathUnderCurrent:
    """Test path traversal safety."""

    def test_path_under_current_valid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            current = Path(tmpdir) / "current"
            current.mkdir()
            (current / "semantic").mkdir()
            out = _path_under_current("semantic/file.md", current)
            assert out is not None
            assert out == (current / "semantic" / "file.md").resolve()

    def test_path_under_current_escapes_returns_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            current = Path(tmpdir) / "current"
            current.mkdir()
            out = _path_under_current("../../../etc/passwd", current)
            assert out is None

    def test_path_under_current_dot_dot_returns_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            current = Path(tmpdir) / "current"
            current.mkdir()
            (current / "a").mkdir()
            out = _path_under_current("a/../../outside", current)
            assert out is None


class TestResolvedContent:
    """Test content resolution (ours/theirs/both)."""

    def test_resolved_content_ours(self):
        content = _resolved_content("ours", "hello", "world")
        assert content == "hello"

    def test_resolved_content_theirs(self):
        content = _resolved_content("theirs", "hello", "world")
        assert content == "world"

    def test_resolved_content_both(self):
        content = _resolved_content("both", "hello\n", "world")
        assert "hello" in content
        assert "world" in content
        assert "--- merged ---" in content
