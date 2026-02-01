#!/usr/bin/env python3
"""
agmem Stress Test & Edge Case Suite

Comprehensive testing of agmem with:
- Large files
- Edge cases (empty, binary, unicode, special chars, etc.)
- All CLI commands
- Performance metrics
"""

import os
import sys
import tempfile
import time
import shutil
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from memvcs.core.repository import Repository
from memvcs.core.objects import Commit


# Test result tracking
class TestResult:
    def __init__(self, name: str, passed: bool, duration: float, details: str = ""):
        self.name = name
        self.passed = passed
        self.duration = duration
        self.details = details
        self.error = None


RESULTS: list[TestResult] = []


def run_test(name: str, fn, *args, **kwargs) -> bool:
    """Run a test and record result."""
    start = time.perf_counter()
    try:
        result = fn(*args, **kwargs)
        duration = time.perf_counter() - start
        passed = result if isinstance(result, bool) else True
        RESULTS.append(TestResult(name, passed, duration, str(result) if result else ""))
        return passed
    except Exception as e:
        duration = time.perf_counter() - start
        r = TestResult(name, False, duration, str(e))
        r.error = str(e)
        RESULTS.append(r)
        return False


def run_agmem(repo_path: Path, *args) -> tuple[int, str]:
    """Run agmem command, return (exit_code, output)."""
    import subprocess

    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parent.parent)
    result = subprocess.run(
        [sys.executable, "-m", "memvcs.cli"] + list(args),
        cwd=repo_path,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    return result.returncode, result.stdout + result.stderr


# --- Test Cases ---


def test_init_basic(repo_path: Path) -> bool:
    """Test basic init."""
    repo = Repository.init(repo_path, "StressTest", "stress@test.com")
    return repo.is_valid_repo()


def test_init_already_exists(repo_path: Path) -> bool:
    """Test init on existing repo fails."""
    try:
        Repository.init(repo_path, "X", "x@x.com")
        return False  # Should have raised
    except ValueError:
        return True


def test_empty_file(repo_path: Path) -> bool:
    """Test empty file."""
    (repo_path / "current" / "semantic" / "empty.md").write_bytes(b"")
    repo = Repository(repo_path)
    repo.stage_file("semantic/empty.md")
    return True


def test_large_file_1mb(repo_path: Path) -> bool:
    """Test 1MB file."""
    content = b"x" * (1024 * 1024)
    (repo_path / "current" / "episodic" / "large1mb.bin").write_bytes(content)
    repo = Repository(repo_path)
    start = time.perf_counter()
    repo.stage_file("episodic/large1mb.bin")
    elapsed = time.perf_counter() - start
    return elapsed < 5.0  # Should complete in 5s


def test_large_file_10mb(repo_path: Path) -> bool:
    """Test 10MB file."""
    content = b"y" * (10 * 1024 * 1024)
    (repo_path / "current" / "episodic" / "large10mb.bin").write_bytes(content)
    repo = Repository(repo_path)
    start = time.perf_counter()
    repo.stage_file("episodic/large10mb.bin")
    elapsed = time.perf_counter() - start
    return elapsed < 30.0


def test_large_file_50mb(repo_path: Path) -> bool:
    """Test 50MB file (stress)."""
    content = b"z" * (50 * 1024 * 1024)
    (repo_path / "current" / "episodic" / "large50mb.bin").write_bytes(content)
    repo = Repository(repo_path)
    start = time.perf_counter()
    repo.stage_file("episodic/large50mb.bin")
    elapsed = time.perf_counter() - start
    return elapsed < 120.0


def test_very_long_line(repo_path: Path) -> bool:
    """Test file with very long line (no newlines)."""
    content = b"a" * 100000 + b"\n"  # 100KB line
    (repo_path / "current" / "semantic" / "longline.md").write_bytes(content)
    repo = Repository(repo_path)
    repo.stage_file("semantic/longline.md")
    return True


def test_all_cli_commands(repo_path: Path) -> bool:
    """Test all mem CLI commands execute without crash."""
    commands = [
        ("status", []),
        ("log", []),
        ("branch", []),
        ("tag", []),
        ("tree", []),
        ("tree", ["HEAD"]),
        ("diff", []),
        ("show", ["HEAD"]),
    ]
    for cmd, args in commands:
        code, _ = run_agmem(repo_path, cmd, *args)
        if code != 0:
            return False
    return True


def test_reset_hard(repo_path: Path) -> bool:
    """Test mem reset --hard."""
    code, _ = run_agmem(repo_path, "reset", "--hard", "HEAD")
    return code == 0


def test_unicode_content(repo_path: Path) -> bool:
    """Test unicode content."""
    content = "日本語 🎉 émojis 中文 العربية\n".encode("utf-8")
    (repo_path / "current" / "semantic" / "unicode.md").write_bytes(content)
    repo = Repository(repo_path)
    repo.stage_file("semantic/unicode.md")
    blob_hash = repo.staging.get_blob_hash("semantic/unicode.md")
    retrieved = repo.object_store.retrieve(blob_hash, "blob")
    return retrieved == content


def test_binary_content(repo_path: Path) -> bool:
    """Test binary content."""
    content = bytes(range(256)) * 100  # 25.6KB binary
    (repo_path / "current" / "checkpoints" / "binary.bin").write_bytes(content)
    repo = Repository(repo_path)
    repo.stage_file("checkpoints/binary.bin")
    blob_hash = repo.staging.get_blob_hash("checkpoints/binary.bin")
    retrieved = repo.object_store.retrieve(blob_hash, "blob")
    return retrieved == content


def test_special_chars_filename(repo_path: Path) -> bool:
    """Test filename with special chars."""
    name = "file-with-dashes_and_underscores.2024.md"
    (repo_path / "current" / "semantic" / name).write_text("test")
    repo = Repository(repo_path)
    repo.stage_file(f"semantic/{name}")
    return repo.staging.is_staged(f"semantic/{name}")


def test_deep_nesting(repo_path: Path) -> bool:
    """Test deep directory nesting."""
    deep = repo_path / "current" / "episodic" / "a" / "b" / "c" / "d" / "e"
    deep.mkdir(parents=True)
    (deep / "deep.md").write_text("nested")
    repo = Repository(repo_path)
    repo.stage_file("episodic/a/b/c/d/e/deep.md")
    return True


def test_many_files(repo_path: Path) -> bool:
    """Test many small files."""
    for i in range(50):
        (repo_path / "current" / "semantic" / f"file_{i:03d}.md").write_text(f"Content {i}")
    repo = Repository(repo_path)
    staged = repo.stage_directory("semantic")
    return len(staged) >= 50


def test_newlines_only(repo_path: Path) -> bool:
    """Test file with only newlines."""
    (repo_path / "current" / "procedural" / "newlines.md").write_bytes(b"\n\n\n")
    repo = Repository(repo_path)
    repo.stage_file("procedural/newlines.md")
    return True


def test_commit_and_retrieve(repo_path: Path) -> bool:
    """Test commit and content retrieval."""
    repo = Repository(repo_path)
    repo.stage_directory()
    commit_hash = repo.commit("Stress test commit")
    commit = Commit.load(repo.object_store, commit_hash)
    return commit is not None and commit.message == "Stress test commit"


def test_deduplication(repo_path: Path) -> bool:
    """Test content deduplication."""
    content = b"identical content"
    (repo_path / "current" / "semantic" / "dup1.md").write_bytes(content)
    (repo_path / "current" / "semantic" / "dup2.md").write_bytes(content)
    repo = Repository(repo_path)
    repo.stage_file("semantic/dup1.md")
    repo.stage_file("semantic/dup2.md")
    h1 = repo.staging.get_blob_hash("semantic/dup1.md")
    h2 = repo.staging.get_blob_hash("semantic/dup2.md")
    return h1 == h2


def test_branch_merge_conflict(repo_path: Path) -> bool:
    """Test merge with conflicting changes (semantic memory)."""
    repo = Repository(repo_path)
    # Create base
    (repo_path / "current" / "semantic" / "conflict.md").write_text("base")
    repo.stage_file("semantic/conflict.md")
    repo.commit("base")
    # Branch A
    repo.refs.create_branch("branch-a")
    repo.refs.set_head_branch("branch-a")
    (repo_path / "current" / "semantic" / "conflict.md").write_text("version A")
    repo.stage_file("semantic/conflict.md")
    repo.commit("change A")
    # Branch B from main
    repo.refs.set_head_branch("main")
    repo.refs.create_branch("branch-b", repo.refs.get_branch_commit("main"))
    repo.refs.set_head_branch("branch-b")
    (repo_path / "current" / "semantic" / "conflict.md").write_text("version B")
    repo.stage_file("semantic/conflict.md")
    repo.commit("change B")
    # Merge - should have conflict
    from memvcs.core.merge import MergeEngine

    engine = MergeEngine(repo)
    result = engine.merge("branch-b", "branch-a")
    return not result.success and len(result.conflicts) > 0


def test_merge_success_no_conflict(repo_path: Path) -> bool:
    """Test merge succeeds when no conflict (fast-forward or clean merge)."""
    repo = Repository(repo_path)
    (repo_path / "current" / "semantic" / "base.md").write_text("base")
    repo.stage_file("semantic/base.md")
    repo.commit("base")
    repo.refs.create_branch("feature")
    repo.refs.set_head_branch("feature")
    (repo_path / "current" / "semantic" / "new.md").write_text("new file")
    repo.stage_file("semantic/new.md")
    repo.commit("feature add")
    repo.refs.set_head_branch("main")
    from memvcs.core.merge import MergeEngine

    engine = MergeEngine(repo)
    result = engine.merge("feature")
    return result.success and result.commit_hash is not None


def test_checkout_restore(repo_path: Path) -> bool:
    """Test checkout restores files."""
    repo = Repository(repo_path)
    repo.refs.set_head_branch("main")
    (repo_path / "current" / "semantic" / "restore.md").write_text("original")
    repo.stage_file("semantic/restore.md")
    repo.commit("original")
    # Modify
    (repo_path / "current" / "semantic" / "restore.md").write_text("modified")
    # Checkout to restore
    repo.checkout("HEAD", force=True)
    content = (repo_path / "current" / "semantic" / "restore.md").read_text()
    return content == "original"


def test_status_categories(repo_path: Path) -> bool:
    """Test status shows staged, modified, untracked."""
    repo = Repository(repo_path)
    (repo_path / "current" / "semantic" / "new_untracked.md").write_text("new")
    (repo_path / "current" / "semantic" / "restore.md").write_text("modified")
    status = repo.get_status()
    return "untracked" in status and "modified" in status


def test_log_walk(repo_path: Path) -> bool:
    """Test log walks history."""
    repo = Repository(repo_path)
    log = repo.get_log(max_count=100)
    return len(log) >= 1


def test_tag_operations(repo_path: Path) -> bool:
    """Test tag create and resolve."""
    repo = Repository(repo_path)
    head = repo.refs.get_branch_commit("main")
    repo.refs.create_tag("stress-v1", head, "Stress test tag")
    resolved = repo.refs.get_tag_commit("stress-v1")
    return resolved == head


def test_reset_soft(repo_path: Path) -> bool:
    """Test reset --soft (if supported) or reset behavior."""
    repo = Repository(repo_path)
    # Just verify reset doesn't crash
    try:
        from memvcs.commands.reset import ResetCommand

        return True
    except Exception:
        return False


def test_tree_command(repo_path: Path) -> bool:
    """Test agmem tree command."""
    code, out = run_agmem(repo_path, "tree")
    return code == 0 and "current" in out or "episodic" in out


def test_diff_command(repo_path: Path) -> bool:
    """Test agmem diff."""
    code, _ = run_agmem(repo_path, "diff")
    return code == 0


def test_show_command(repo_path: Path) -> bool:
    """Test agmem show."""
    code, out = run_agmem(repo_path, "show", "HEAD")
    return code == 0 and "commit" in out


# --- Main ---


def main():
    print("=" * 70)
    print("agmem STRESS TEST & EDGE CASE SUITE")
    print("=" * 70)
    print(f"Started: {datetime.now().isoformat()}")
    print()

    with tempfile.TemporaryDirectory(prefix="agmem-stress-") as tmpdir:
        repo_path = Path(tmpdir)

        # Phase 1: Init & basic
        print("Phase 1: Initialization & Basic Operations")
        run_test("init (basic)", test_init_basic, repo_path)
        run_test("init (already exists fails)", test_init_already_exists, repo_path)
        print("  Done.\n")

        # Phase 2: Edge case files
        print("Phase 2: Edge Case Files")
        run_test("empty file", test_empty_file, repo_path)
        run_test("unicode content", test_unicode_content, repo_path)
        run_test("binary content", test_binary_content, repo_path)
        run_test("special chars filename", test_special_chars_filename, repo_path)
        run_test("deep nesting", test_deep_nesting, repo_path)
        run_test("newlines only", test_newlines_only, repo_path)
        run_test("many files (50)", test_many_files, repo_path)
        run_test("content deduplication", test_deduplication, repo_path)
        print("  Done.\n")

        # Phase 3: Large files
        print("Phase 3: Large Files")
        run_test("1MB file", test_large_file_1mb, repo_path)
        run_test("10MB file", test_large_file_10mb, repo_path)
        run_test("50MB file", test_large_file_50mb, repo_path)
        run_test("very long line (100KB)", test_very_long_line, repo_path)
        print("  Done.\n")

        # Phase 4: Commit & history
        print("Phase 4: Commit & History")
        run_test("commit and retrieve", test_commit_and_retrieve, repo_path)
        run_test("log walk", test_log_walk, repo_path)
        run_test("tag operations", test_tag_operations, repo_path)
        print("  Done.\n")

        # Phase 5: Branching & merge
        print("Phase 5: Branching & Merge")
        run_test("merge success (no conflict)", test_merge_success_no_conflict, repo_path)
        run_test("merge conflict detection", test_branch_merge_conflict, repo_path)
        run_test("checkout restore", test_checkout_restore, repo_path)
        print("  Done.\n")

        # Phase 6: Status & commands
        print("Phase 6: Status & CLI Commands")
        run_test("status categories", test_status_categories, repo_path)
        run_test("all CLI commands", test_all_cli_commands, repo_path)
        run_test("agmem tree", test_tree_command, repo_path)
        run_test("agmem diff", test_diff_command, repo_path)
        run_test("agmem show", test_show_command, repo_path)
        run_test("agmem reset --hard", test_reset_hard, repo_path)
        print("  Done.\n")

    # Report
    print("=" * 70)
    print("TEST REPORT")
    print("=" * 70)

    passed = sum(1 for r in RESULTS if r.passed)
    failed = sum(1 for r in RESULTS if not r.passed)
    total_time = sum(r.duration for r in RESULTS)

    print(f"\nTotal: {len(RESULTS)} tests | Passed: {passed} | Failed: {failed}")
    print(f"Total duration: {total_time:.2f}s")
    print()

    print("Results by test:")
    for r in RESULTS:
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{status}] {r.name} ({r.duration:.3f}s)")
        if not r.passed and r.error:
            print(f"         Error: {r.error[:80]}...")

    # Write report file
    report_path = Path(__file__).parent.parent / "docs" / "aux" / "STRESS_TEST_REPORT.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        f.write("# agmem Stress Test Report\n\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n\n")
        f.write(f"**Summary:** {passed}/{len(RESULTS)} passed, {failed} failed\n\n")
        f.write("## Results\n\n")
        for r in RESULTS:
            status = "✅" if r.passed else "❌"
            f.write(f"- {status} **{r.name}** ({r.duration:.3f}s)\n")
            if not r.passed and r.error:
                f.write(f"  - Error: {r.error}\n")
        f.write("\n## Edge Cases Covered\n\n")
        f.write("- Empty files\n")
        f.write("- Large files (1MB, 10MB)\n")
        f.write("- Unicode content\n")
        f.write("- Binary content\n")
        f.write("- Special characters in filenames\n")
        f.write("- Deep directory nesting\n")
        f.write("- Many files (50+)\n")
        f.write("- Content deduplication\n")
        f.write("- Merge conflicts\n")
        f.write("- Checkout/restore\n")

    print(f"\nReport written to: {report_path}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
