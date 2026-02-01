"""
agmem merge - Join two or more development histories together.
"""

import argparse

from ..commands.base import require_repo
from ..core.merge import MergeEngine
from ..core.repository import Repository


class MergeCommand:
    """Merge branches."""

    name = "merge"
    help = "Join two or more development histories together"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument("branch", help="Branch to merge into current branch")
        parser.add_argument("-m", "--message", help="Merge commit message")
        parser.add_argument(
            "--no-commit", action="store_true", help="Perform merge but do not commit"
        )
        parser.add_argument("--abort", action="store_true", help="Abort the current merge")
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Accept conditionally trusted branch commits without prompting",
        )

    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code

        # Abort merge
        if args.abort:
            # TODO: Implement merge abort
            print("Merge abort not yet implemented")
            return 0

        # Check if we're on a branch
        current_branch = repo.refs.get_current_branch()
        if not current_branch:
            print("Error: Not currently on any branch.")
            print("Cannot merge when HEAD is detached.")
            return 1

        # Check if trying to merge current branch
        if args.branch == current_branch:
            print(f"Error: Cannot merge '{args.branch}' into itself")
            return 1

        # Check if branch exists
        if not repo.refs.branch_exists(args.branch):
            print(f"Error: Branch '{args.branch}' not found.")
            return 1

        # Trust check for branch tip (may be from another agent)
        other_commit_hash = repo.refs.get_branch_commit(args.branch)
        if other_commit_hash:
            from ..core.objects import Commit
            from ..core.trust import find_verifying_key, get_trust_level
            other_commit = Commit.load(repo.object_store, other_commit_hash)
            if other_commit and other_commit.metadata:
                key_pem = find_verifying_key(repo.mem_dir, other_commit.metadata)
                if key_pem is not None:
                    level = get_trust_level(repo.mem_dir, key_pem)
                    if level == "untrusted":
                        print(f"Merge blocked: branch '{args.branch}' signed by untrusted key.")
                        return 1
                    if level == "conditional" and not getattr(args, "yes", False):
                        print("Branch signed by conditionally trusted key. Use --yes to merge.")
                        return 1

        # Perform merge
        engine = MergeEngine(repo)
        result = engine.merge(args.branch, message=args.message)

        if result.success:
            print(f"Merge successful: {result.message}")
            if result.commit_hash:
                print(f"  Commit: {result.commit_hash[:8]}")
            try:
                from ..core.audit import append_audit
                append_audit(repo.mem_dir, "merge", {"branch": args.branch, "commit": result.commit_hash})
            except Exception:
                pass
            return 0
        else:
            print(f"Merge failed: {result.message}")

            if result.conflicts:
                # Persist conflicts for agmem resolve
                try:
                    import json
                    merge_dir = repo.mem_dir / "merge"
                    merge_dir.mkdir(parents=True, exist_ok=True)
                    conflicts_data = [
                        {
                            "path": c.path,
                            "message": c.message,
                            "memory_type": getattr(c, "memory_type", None),
                            "payload": getattr(c, "payload", None),
                            "ours_content": c.ours_content,
                            "theirs_content": c.theirs_content,
                            "base_content": c.base_content,
                        }
                        for c in result.conflicts
                    ]
                    (merge_dir / "conflicts.json").write_text(json.dumps(conflicts_data, indent=2))
                except Exception:
                    pass
                print()
                print("Conflicts:")
                for conflict in result.conflicts:
                    print(f"  {conflict.path}")
                print()
                print("Resolve conflicts with 'agmem resolve' or edit files and run 'agmem commit'.")

            return 1
