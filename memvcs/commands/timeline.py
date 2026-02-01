"""
agmem timeline - Show evolution of a specific memory file over time.
"""

import argparse
from pathlib import Path

from ..commands.base import require_repo
from ..core.objects import Commit, Tree, Blob


class TimelineCommand:
    """Show evolution of a memory file (blame-style over time)."""

    name = "timeline"
    help = "Show evolution of a specific memory file over time"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            "file",
            help="File to show timeline for (path relative to current/)",
        )
        parser.add_argument(
            "--limit",
            "-n",
            type=int,
            default=20,
            help="Max commits to show (default: 20)",
        )

    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code

        filepath = args.file.replace("current/", "").lstrip("/")

        # Walk commit history
        head = repo.refs.get_head()
        commit_hash = (
            repo.refs.get_branch_commit(head["value"])
            if head["type"] == "branch"
            else head.get("value")
        )

        history = []
        seen = set()
        while commit_hash and len(history) < args.limit:
            if commit_hash in seen:
                break
            seen.add(commit_hash)

            commit = Commit.load(repo.object_store, commit_hash)
            if not commit:
                break

            tree = repo.get_commit_tree(commit_hash)
            if not tree:
                commit_hash = commit.parents[0] if commit.parents else None
                continue

            blob_hash = None
            for entry in tree.entries:
                path = entry.path + "/" + entry.name if entry.path else entry.name
                if path == filepath:
                    blob_hash = entry.hash
                    break

            if blob_hash:
                blob = Blob.load(repo.object_store, blob_hash)
                content = blob.content.decode("utf-8", errors="replace") if blob else ""
                history.append(
                    {
                        "commit": commit_hash,
                        "timestamp": commit.timestamp,
                        "author": commit.author,
                        "message": commit.message,
                        "content": content,
                    }
                )

            commit_hash = commit.parents[0] if commit.parents else None

        if not history:
            print(f"File {filepath} not found in commit history.")
            return 1

        print(f"Timeline for {filepath}:")
        print("=" * 60)
        for i, h in enumerate(history):
            print(f"\n[{i + 1}] {h['commit'][:8]} {h['timestamp']}")
            print(f"    {h['author']}")
            print(f"    {h['message'][:70]}")
            if i > 0 and history[i - 1]["content"] != h["content"]:
                prev_content = history[i - 1]["content"].encode()
                curr_content = h["content"].encode()
                # Simple line diff
                prev_lines = prev_content.splitlines()
                curr_lines = curr_content.splitlines()
                for j, (a, b) in enumerate(zip(prev_lines, curr_lines)):
                    if a != b:
                        print(f"    ... (changed at line {j + 1})")
                        break
                else:
                    if len(prev_lines) != len(curr_lines):
                        print(f"    ... (lines changed: {len(prev_lines)} -> {len(curr_lines)})")
            print()

        return 0
