"""
agmem branch - List, create, or delete branches.
"""

import argparse

from ..commands.base import require_repo
from ..core.repository import Repository


class BranchCommand:
    """Manage branches."""

    name = "branch"
    help = "List, create, or delete branches"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument("name", nargs="?", help="Branch name to create or delete")
        parser.add_argument("--delete", "-d", action="store_true", help="Delete a branch")
        parser.add_argument(
            "--force", "-D", action="store_true", help="Force delete a branch (even if not merged)"
        )
        parser.add_argument("--list", "-l", action="store_true", help="List all branches")
        parser.add_argument(
            "--all", "-a", action="store_true", help="List all branches including remote"
        )
        parser.add_argument("start_point", nargs="?", help="Commit to start the new branch from")

    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code

        if args.list or (not args.name and not args.delete):
            return BranchCommand._list_branches(repo)

        if args.delete or args.force:
            if not args.name:
                print("Error: Branch name required for deletion")
                return 1

            current = repo.refs.get_current_branch()
            if args.name == current:
                print(f"Error: Cannot delete current branch '{args.name}'")
                print("Switch to another branch first.")
                return 1

            if repo.refs.delete_branch(args.name):
                print(f"Deleted branch {args.name}")
                return 0
            print(f"Error: Branch '{args.name}' not found")
            return 1

        if args.name:
            if repo.refs.branch_exists(args.name):
                print(f"Error: A branch named '{args.name}' already exists.")
                return 1

            start_commit = None
            if args.start_point:
                start_commit = repo.resolve_ref(args.start_point)
                if not start_commit:
                    print(f"Error: Not a valid object name: '{args.start_point}'")
                    return 1

            if repo.refs.create_branch(args.name, start_commit):
                print(f"Created branch {args.name}")
                head = repo.refs.get_head()
                if head.get("type") == "branch":
                    print(f"  (based on {head['value']})")
                return 0
            print(f"Error: Could not create branch '{args.name}'")
            return 1

        return 0

    @staticmethod
    def _list_branches(repo) -> int:
        """List all branches with current branch marked."""
        branches = repo.refs.list_branches()
        current = repo.refs.get_current_branch()
        if not branches:
            print("No branches yet.")
            return 0
        for branch in branches:
            prefix = "* " if branch == current else "  "
            print(f"{prefix}{branch}")
        return 0
