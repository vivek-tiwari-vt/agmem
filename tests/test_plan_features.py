"""Tests for plan features: HEAD~n, branch names with /, search fallback, clone, remote, pull."""

import pytest
import tempfile
from pathlib import Path

from memvcs.core.repository import Repository
from memvcs.core.refs import RefsManager, _ref_path_under_root


class TestResolveRefHeadN:
    """Test HEAD~n resolution."""

    def test_resolve_ref_head_zero(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            (repo.current_dir / "a.md").write_text("a")
            repo.stage_file("a.md")
            repo.commit("C1")
            head_hash = repo.refs.get_branch_commit("main")
            assert repo.resolve_ref("HEAD~0") == head_hash

    def test_resolve_ref_head_one(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            (repo.current_dir / "a.md").write_text("a")
            repo.stage_file("a.md")
            repo.commit("C1")
            first_hash = repo.refs.get_branch_commit("main")
            (repo.current_dir / "b.md").write_text("b")
            repo.stage_file("b.md")
            repo.commit("C2")
            assert repo.resolve_ref("HEAD~1") == first_hash

    def test_resolve_ref_head_two(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            for i in range(3):
                (repo.current_dir / f"f{i}.md").write_text(str(i))
                repo.stage_file(f"f{i}.md")
                repo.commit(f"C{i}")
            first_hash = repo.refs.get_branch_commit("main")
            (repo.current_dir / "f1.md").write_text("1x")
            repo.stage_file("f1.md")
            repo.commit("C1x")
            (repo.current_dir / "f2.md").write_text("2x")
            repo.stage_file("f2.md")
            repo.commit("C2x")
            assert repo.resolve_ref("HEAD~2") != repo.resolve_ref("HEAD")
            assert repo.resolve_ref("HEAD~1") != repo.resolve_ref("HEAD")


class TestBranchNamesWithSlash:
    """Test branch names with / (Git-style)."""

    def test_create_branch_with_slash(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            (repo.current_dir / "a.md").write_text("a")
            repo.stage_file("a.md")
            repo.commit("C1")
            result = repo.refs.create_branch("feature/test-branch")
            assert result
            assert repo.refs.branch_exists("feature/test-branch")
            branches = repo.refs.list_branches()
            assert "feature/test-branch" in branches
            assert "main" in branches

    def test_ref_path_under_root_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            assert _ref_path_under_root("a/b", base) is True
            assert _ref_path_under_root("..", base) is False
            assert _ref_path_under_root("../x", base) is False


class TestSearchTextFallback:
    """Test search fallback when vector store is missing."""

    def test_search_text_fallback_returns_matches(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            (repo.current_dir / "semantic" / "prefs.md").write_text("User prefers Python and TypeScript")
            (repo.current_dir / "episodic" / "s1.md").write_text("Session about Python")
            import subprocess
            import sys
            r = subprocess.run(
                [sys.executable, "-m", "memvcs.cli", "search", "Python"],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert r.returncode == 0
            assert "prefs.md" in r.stdout or "s1.md" in r.stdout
            assert "Python" in r.stdout


class TestCloneAndRemote:
    """Test clone and remote path validation."""

    def test_clone_file_url(self):
        with tempfile.TemporaryDirectory() as src_dir:
            repo = Repository.init(path=Path(src_dir))
            (repo.current_dir / "episodic" / "x.md").write_text("x")
            repo.stage_file("episodic/x.md")
            repo.commit("Initial")
            with tempfile.TemporaryDirectory() as dst_parent:
                import subprocess
                import sys
                r = subprocess.run(
                    [sys.executable, "-m", "memvcs.cli", "clone", f"file://{src_dir}", "clone_dst"],
                    cwd=dst_parent,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                assert r.returncode == 0
                clone_path = Path(dst_parent) / "clone_dst"
                assert (clone_path / ".mem").exists()
                assert (clone_path / "current" / "episodic" / "x.md").exists()

    def test_remote_add_show(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            import subprocess
            import sys
            r = subprocess.run(
                [sys.executable, "-m", "memvcs.cli", "remote", "add", "origin", f"file:///tmp/remote"],
                cwd=tmpdir,
                capture_output=True,
                text=True,
            )
            assert r.returncode == 0
            r2 = subprocess.run(
                [sys.executable, "-m", "memvcs.cli", "remote", "show"],
                cwd=tmpdir,
                capture_output=True,
                text=True,
            )
            assert r2.returncode == 0
            assert "origin" in r2.stdout
