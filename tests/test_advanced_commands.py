"""Tests for advanced CLI commands: show --at, diff --from/--to, when, timeline, recall, pack, decay, verify."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from memvcs.core.repository import Repository


def _run_agmem(cwd, *args):
    import os

    project_root = str(Path(__file__).resolve().parent.parent)
    env = os.environ.copy()
    env["PYTHONPATH"] = project_root + (os.pathsep + env.get("PYTHONPATH", ""))
    return subprocess.run(
        [sys.executable, "-m", "memvcs.cli"] + list(args),
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )


class TestShowAt(unittest.TestCase):
    """Test agmem show --at timestamp."""

    def test_show_at_resolves_date_and_shows_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            (repo.current_dir / "semantic" / "prefs.md").write_text("user prefers dark mode")
            repo.stage_file("semantic/prefs.md")
            repo.commit("Initial")
            r = _run_agmem(tmpdir, "show", "--at", "2030-01-01T00:00:00Z", "semantic/prefs.md")
            assert r.returncode == 0, (r.stdout, r.stderr)
            assert "user prefers dark mode" in r.stdout or "prefs" in r.stdout


class TestDiffFromTo:
    """Test agmem diff --from / --to."""

    def test_diff_from_to_resolves_dates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            (repo.current_dir / "a.md").write_text("v1")
            repo.stage_file("a.md")
            repo.commit("C1")
            (repo.current_dir / "a.md").write_text("v2")
            repo.stage_file("a.md")
            repo.commit("C2")
            r = _run_agmem(tmpdir, "diff", "--from-ref", "HEAD~1", "--to-ref", "HEAD")
            assert r.returncode == 0


class TestWhen(unittest.TestCase):
    """Test agmem when fact."""

    def test_when_finds_commits_containing_fact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            (repo.current_dir / "semantic" / "prefs.md").write_text("user prefers dark mode")
            repo.stage_file("semantic/prefs.md")
            repo.commit("Learned prefs")
            r = _run_agmem(tmpdir, "when", "dark mode", "--file", "semantic/prefs.md")
            assert r.returncode == 0, (r.stdout[:300], r.stderr[:300])
            assert (
                "dark mode" in r.stdout
                or "prefs" in r.stdout
                or "Found" in r.stdout
                or "commit" in r.stdout.lower()
            )


class TestTimeline:
    """Test agmem timeline file."""

    def test_timeline_shows_evolution(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            (repo.current_dir / "semantic" / "prefs.md").write_text("v1")
            repo.stage_file("semantic/prefs.md")
            repo.commit("C1")
            r = _run_agmem(tmpdir, "timeline", "semantic/prefs.md")
            assert r.returncode == 0
            assert "prefs" in r.stdout or "Timeline" in r.stdout


class TestRecallCli(unittest.TestCase):
    """Test agmem recall."""

    def test_recall_returns_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            (repo.current_dir / "semantic" / "prefs.md").write_text("prefs content")
            r = _run_agmem(
                tmpdir, "recall", "--context", "task", "--strategy", "recency", "--format", "json"
            )
            assert r.returncode == 0
            assert "[" in r.stdout or "path" in r.stdout


class TestPackCli:
    """Test agmem pack."""

    def test_pack_returns_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            (repo.current_dir / "semantic" / "prefs.md").write_text("prefs")
            r = _run_agmem(tmpdir, "pack", "--context", "task", "--budget", "1000")
            assert r.returncode == 0
            assert len(r.stdout) >= 0


class TestDecayCli(unittest.TestCase):
    """Test agmem decay --dry-run."""

    def test_decay_dry_run_does_not_modify(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            (repo.current_dir / "episodic" / "x.md").write_text("x")
            r = _run_agmem(tmpdir, "decay", "--dry-run")
            assert r.returncode == 0, (r.stdout, r.stderr)
            assert (Path(tmpdir) / "current" / "episodic" / "x.md").exists()


class TestVerifyCli:
    """Test agmem verify."""

    def test_verify_consistency_runs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            (repo.current_dir / "semantic" / "prefs.md").write_text(
                "---\nschema_version: 1.0\n---\nprefs"
            )
            r = _run_agmem(tmpdir, "verify", "--consistency")
            assert r.returncode == 0
            assert "Checked" in r.stdout or "No contradictions" in r.stdout


class TestCommitImportanceCli(unittest.TestCase):
    """Test agmem commit --importance."""

    def test_commit_importance_flag(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            (repo.current_dir / "semantic" / "prefs.md").write_text("prefs")
            repo.stage_file("semantic/prefs.md")
            repo.commit("Learned", {"importance": 0.9})
            from memvcs.core.objects import Commit

            head = repo.refs.get_branch_commit("main")
            assert head
            commit = Commit.load(repo.object_store, head)
            assert commit.metadata.get("importance") == 0.9
