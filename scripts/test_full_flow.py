#!/usr/bin/env python3
"""
Full-flow test for agmem: exercises all commands and shows knowledge graph.

Run from project root: python3 scripts/test_full_flow.py
Uses a temporary directory unless --use-current is passed (then uses ./current).
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


def run_agmem(cwd: Path, *args: str) -> tuple[int, str]:
    """Run agmem CLI; return (exit_code, combined stdout+stderr)."""
    cmd = [sys.executable, "-m", "memvcs.cli"] + list(args)
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=30)
    out = (r.stdout or "") + (r.stderr or "")
    return r.returncode, out.strip()


def main() -> int:
    ap = argparse.ArgumentParser(description="Test full agmem flow and graph")
    ap.add_argument("--use-current", action="store_true", help="Use ./current (existing repo) instead of temp dir")
    ap.add_argument("--verbose", "-v", action="store_true", help="Print each command output")
    args = ap.parse_args()

    if args.use_current:
        root = Path(__file__).resolve().parent.parent
        if not (root / ".mem").exists():
            print("Error: --use-current requires an existing repo (run agmem init first)")
            return 1
        cwd = root
        print("Using existing repo at", cwd)
    else:
        root = Path(tempfile.mkdtemp(prefix="agmem_test_"))
        cwd = root
        print("Using temp repo at", cwd)

    failures = []
    steps = []

    def step(name: str, *cli_args: str, optional_ok: bool = False) -> bool:
        code, out = run_agmem(cwd, *cli_args)
        steps.append((name, cli_args, code, out))
        if args.verbose:
            print(f"\n--- {name} ---")
            print(out)
        if code != 0 and not optional_ok:
            failures.append((name, code, out))
            return False
        return True

    # --- Repo setup (only if not using current) ---
    if not args.use_current:
        if not step("init", "init"):
            print("Init failed")
            return 1
        # Create memory files with wikilinks for graph
        current = cwd / "current"
        (current / "episodic").mkdir(parents=True, exist_ok=True)
        (current / "semantic").mkdir(parents=True, exist_ok=True)
        (current / "procedural").mkdir(parents=True, exist_ok=True)
        (current / "episodic" / "session1.md").write_text(
            "## Session 1\n\nReferences: [[user-preferences]] and [[coding-workflow]].\n"
        )
        (current / "semantic" / "user-preferences.md").write_text(
            "## User Preferences\n\nSee [[session1]] for context.\n"
        )
        (current / "procedural" / "coding-workflow.md").write_text(
            "## Workflow\n\nRelated: [[user-preferences]].\n"
        )
        if not step("add", "add", "."):
            return 1
        if not step("commit", "commit", "-m", "Initial memory snapshot"):
            return 1

    # --- Core commands ---
    step("status", "status")
    step("log", "log", "-n", "5")
    step("log oneline", "log", "--oneline", "-n", "3")
    step("branch list", "branch")
    step("branch create", "branch", "feature/test-branch", optional_ok=True)  # Git-style name; skip if exists
    step("checkout", "checkout", "main")  # back to main
    step("show HEAD", "show", "HEAD")
    step("diff", "diff")
    step("tree", "tree")
    step("tag", "tag", "v0.1-test", optional_ok=True)  # may fail if tag exists
    step("reflog", "reflog", "HEAD", "-n", "5")
    step("search", "search", "user", optional_ok=True)
    step("fsck", "fsck", optional_ok=True)
    step("blame", "blame", "semantic/user-preferences.md", optional_ok=True)

    # --- Stash (optional) ---
    (cwd / "current" / "episodic" / "wip.md").write_text("WIP content")
    step("stash", "stash", "push", "-m", "test stash", optional_ok=True)
    step("stash list", "stash", "list", optional_ok=True)
    step("stash pop", "stash", "pop", optional_ok=True)

    # --- Knowledge graph ---
    print("\n" + "=" * 60)
    print("KNOWLEDGE GRAPH FEATURE (agmem graph)")
    print("=" * 60)
    code, graph_out = run_agmem(cwd, "graph", "--no-similarity")  # no vector store needed
    print(graph_out)
    if code != 0:
        failures.append(("graph", code, graph_out))
    else:
        # Also export D3 format to a file
        code2, _ = run_agmem(cwd, "graph", "--format", "d3", "--output", str(cwd / "graph_d3.json"))
        if code2 == 0:
            print("\n(Exported D3 graph to graph_d3.json)")

    # --- Summary ---
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    if failures:
        print("Failed steps:")
        for name, code, out in failures:
            print(f"  - {name} (exit {code})")
            if out and len(out) < 200:
                print(f"    {out}")
        return 1
    print("All exercised commands completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
