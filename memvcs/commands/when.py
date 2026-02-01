"""
agmem when - Find when a specific fact was learned.
"""

import argparse
from pathlib import Path

from ..commands.base import require_repo
from ..core.objects import Commit, Tree, Blob


class WhenCommand:
    """Find when a fact was learned in memory history."""

    name = "when"
    help = "Find when a specific fact was learned"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            "fact",
            nargs="?",
            help="Fact or text to search for (e.g., 'user prefers dark mode')",
        )
        parser.add_argument(
            "--file",
            "-f",
            help="Limit search to specific file (e.g., semantic/preferences.md)",
        )
        parser.add_argument(
            "--limit",
            "-n",
            type=int,
            default=10,
            help="Max commits to report (default: 10)",
        )

    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code

        if not args.fact:
            print("Error: Fact to search for is required.")
            print('Usage: agmem when "fact to find" [--file path]')
            return 1

        fact_lower = args.fact.lower()
        file_filter = args.file.replace("current/", "").lstrip("/") if args.file else None

        # Walk commit history from HEAD
        head = repo.refs.get_head()
        commit_hash = (
            repo.refs.get_branch_commit(head["value"])
            if head["type"] == "branch"
            else head.get("value")
        )

        found = []
        seen = set()
        while commit_hash and len(found) < args.limit:
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

            # Check each file in tree
            for entry in tree.entries:
                path = entry.path + "/" + entry.name if entry.path else entry.name
                if file_filter and path != file_filter:
                    continue
                if entry.obj_type != "blob":
                    continue
                blob = Blob.load(repo.object_store, entry.hash)
                if not blob:
                    continue
                try:
                    content = blob.content.decode("utf-8", errors="replace")
                except Exception:
                    continue
                if fact_lower in content.lower():
                    found.append(
                        {
                            "commit": commit_hash,
                            "path": path,
                            "timestamp": commit.timestamp,
                            "author": commit.author,
                            "message": commit.message,
                        }
                    )
                    break  # One match per commit

            commit_hash = commit.parents[0] if commit.parents else None

        if not found:
            scope = f" in {file_filter}" if file_filter else ""
            print(f'No commits found containing "{args.fact}"{scope}')
            return 0

        print(f'Fact "{args.fact}" found in {len(found)} commit(s):')
        print()
        for i, m in enumerate(found, 1):
            print(f"[{i}] {m['commit'][:8]} {m['timestamp']} - {m['path']}")
            print(f"    {m['message'][:60]}")
            print()
        return 0
