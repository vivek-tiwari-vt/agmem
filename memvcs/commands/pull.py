"""
agmem pull - Pull memory from remote.
"""

import argparse
from pathlib import Path


class PullCommand:
    """Pull memory from remote repository."""

    name = "pull"
    help = "Pull memory from remote repository"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            "remote",
            nargs="?",
            default="origin",
            help="Remote name (default: origin)",
        )
        parser.add_argument(
            "branch",
            nargs="?",
            help="Branch to pull (default: all)",
        )

    @staticmethod
    def execute(args) -> int:
        from memvcs.commands.base import require_repo
        from memvcs.core.remote import Remote

        repo, code = require_repo()
        if code != 0:
            return code

        remote = Remote(repo.root, args.remote)
        if not remote.get_remote_url():
            print(
                f"Error: Remote '{args.remote}' has no URL. Set with: agmem remote add {args.remote} <url>"
            )
            return 1

        try:
            msg = remote.fetch(branch=args.branch)
            print(msg)
            # Merge fetched refs into current branch
            current_branch = repo.refs.get_current_branch()
            if current_branch is not None:
                remote_ref = f"{args.remote}/{current_branch}"
                remote_hash = repo.resolve_ref(remote_ref)
                if remote_hash:
                    from memvcs.core.merge import MergeEngine

                    merge_engine = MergeEngine(repo)
                    try:
                        result = merge_engine.merge(remote_ref)
                        if result.success:
                            print(f"Merged {remote_ref} into {current_branch}.")
                        else:
                            print("Merge had conflicts. Resolve and commit.")
                    except Exception as e:
                        print(f"Merge note: {e}")
            return 0
        except ValueError as e:
            print(f"Error: {e}")
            return 1
