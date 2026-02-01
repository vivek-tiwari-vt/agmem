"""
agmem status - Show working tree status.
"""

import argparse

from ..commands.base import require_repo
from ..core.repository import Repository


class StatusCommand:
    """Show the working tree status."""

    name = "status"
    help = "Show the working tree status"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument("--short", "-s", action="store_true", help="Show short format")
        parser.add_argument("--branch", "-b", action="store_true", help="Show branch information")

    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code

        status = repo.get_status()

        # Show branch info
        branch = status.get("branch")
        head = status.get("head", {})

        if args.short:
            # Short format: XY filename
            for f in status.get("staged", []):
                print(f"A  {f}")
            for f in status.get("modified", []):
                print(f" M {f}")
            for f in status.get("deleted", []):
                print(f" D {f}")
            for f in status.get("untracked", []):
                print(f"?? {f}")
        else:
            # Long format
            if branch:
                print(f"On branch {branch}")
            elif head.get("type") == "commit":
                print(f"HEAD detached at {head['value'][:8]}")

            # Check for commits
            head_commit = repo.get_head_commit()
            if not head_commit:
                print("\nNo commits yet")

            # Staged changes
            staged = status.get("staged", [])
            if staged:
                print(f"\nChanges to be committed:")
                print(f'  (use "agmem reset HEAD <file>..." to unstage)')
                print()
                for f in staged:
                    print(f"        new file:   {f}")
                print()

            # Modified but not staged
            modified = status.get("modified", [])
            if modified:
                print(f"Changes not staged for commit:")
                print(f'  (use "agmem add <file>..." to update what will be committed)')
                print()
                for f in modified:
                    print(f"        modified:   {f}")
                print()

            # Deleted but not staged
            deleted = status.get("deleted", [])
            if deleted:
                print(f"Deleted files:")
                print(f'  (use "agmem add <file>..." to stage deletion)')
                print()
                for f in deleted:
                    print(f"        deleted:    {f}")
                print()

            # Untracked files
            untracked = status.get("untracked", [])
            if untracked:
                print(f"Untracked files:")
                print(f'  (use "agmem add <file>..." to include in what will be committed)')
                print()
                for f in untracked:
                    print(f"        {f}")
                print()

            # Summary
            total_changes = len(staged) + len(modified) + len(deleted) + len(untracked)
            if total_changes == 0:
                if head_commit:
                    print("nothing to commit, working tree clean")
                else:
                    print('nothing to commit (create/copy files and use "agmem add" to track)')

        return 0
