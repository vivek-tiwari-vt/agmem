"""
agmem checkout - Switch branches or restore files.
"""

import argparse

from ..commands.base import require_repo
from ..core.repository import Repository


class CheckoutCommand:
    """Switch branches or restore working tree files."""

    name = "checkout"
    help = "Switch branches or restore working tree files"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument("ref", help="Branch, tag, or commit to checkout")
        parser.add_argument("-b", action="store_true", help="Create and checkout a new branch")
        parser.add_argument(
            "--force", "-f", action="store_true", help="Force checkout (discard local changes)"
        )

    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code

        # Create and checkout new branch
        if args.b:
            branch_name = args.ref

            # Check if branch already exists
            if repo.refs.branch_exists(branch_name):
                print(f"Error: A branch named '{branch_name}' already exists.")
                return 1

            # Get current HEAD commit
            head = repo.refs.get_head()
            if head["type"] == "branch":
                current_commit = repo.refs.get_branch_commit(head["value"])
            else:
                current_commit = head["value"]

            # Create branch
            if not repo.refs.create_branch(branch_name, current_commit):
                print(f"Error: Could not create branch '{branch_name}'")
                return 1

            # Switch to new branch
            try:
                repo.refs.set_head_branch(branch_name)
                print(f"Switched to a new branch '{branch_name}'")
                return 0
            except Exception as e:
                print(f"Error switching to branch: {e}")
                return 1

        # Regular checkout
        ref = args.ref

        # Check if it's a branch
        is_branch = repo.refs.branch_exists(ref)

        try:
            commit_hash = repo.checkout(ref, force=args.force)

            if is_branch:
                print(f"Switched to branch '{ref}'")
            else:
                # Check if it's a tag
                if repo.refs.tag_exists(ref):
                    print(f"Note: checking out '{ref}'.")
                    print()
                    print(
                        "You are in 'detached HEAD' state. You can look around, make experimental"
                    )
                    print(
                        "changes and commit them, and you can discard any commits you make in this"
                    )
                    print("state without impacting any branches by switching back to a branch.")
                else:
                    print(f"Note: checking out '{commit_hash[:8]}'.")
                    print()
                    print("You are in 'detached HEAD' state.")

            return 0

        except ValueError as e:
            print(f"Error: {e}")
            return 1
        except Exception as e:
            print(f"Error during checkout: {e}")
            return 1
