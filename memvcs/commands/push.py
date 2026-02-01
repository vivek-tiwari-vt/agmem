"""
agmem push - Push memory to remote with auto-rebase support.
"""

import argparse
from pathlib import Path


class MemoryConflictError(Exception):
    """Exception raised when push fails due to conflicts."""

    pass


class PushCommand:
    """Push memory repository to remote with auto-rebase."""

    name = "push"
    help = "Push memory to remote repository"

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
            help="Branch to push (default: current)",
        )
        parser.add_argument(
            "--force",
            "-f",
            action="store_true",
            help="Force push (WARNING: may overwrite remote changes)",
        )
        parser.add_argument(
            "--no-rebase",
            action="store_true",
            help="Don't attempt auto-rebase on conflicts",
        )

    @staticmethod
    def execute(args) -> int:
        from memvcs.commands.base import require_repo
        from memvcs.core.remote import Remote
        from memvcs.core.merge import MergeEngine

        repo, code = require_repo()
        if code != 0:
            return code

        remote = Remote(repo.root, args.remote)
        remote_url = remote.get_remote_url()

        if not remote_url:
            print(f"Error: Remote '{args.remote}' has no URL.")
            print(f"Set with: agmem remote add {args.remote} <url>")
            return 1

        # Get current branch
        branch = args.branch or repo.refs.get_current_branch()
        if not branch:
            print("Error: Not on a branch and no branch specified")
            return 1

        # Force push warning
        if args.force:
            print("WARNING: Force push may overwrite remote changes!")
            local_hash = repo.refs.get_branch_commit(branch)
            try:
                msg = remote.push(branch=branch)
                print(msg)
                return 0
            except ValueError as e:
                print(f"Error: {e}")
                return 1

        # Auto-rebase workflow
        if not args.no_rebase:
            # Fetch remote state
            try:
                print(f"Fetching from {args.remote}...")
                remote.fetch()
            except Exception as e:
                print(f"Note: Could not fetch remote ({e}), attempting direct push...")

            # Check if we're behind remote
            local_hash = repo.refs.get_branch_commit(branch)
            remote_branch = f"{args.remote}/{branch}"
            remote_hash = repo.resolve_ref(remote_branch)

            if remote_hash and remote_hash != local_hash:
                # Check if we can fast-forward or need rebase
                merge_engine = MergeEngine(repo)
                ancestor = merge_engine.find_common_ancestor(local_hash, remote_hash)

                if ancestor == local_hash:
                    # We're behind - need to pull first
                    print("Local is behind remote. Pull first with: agmem pull")
                    return 1

                elif ancestor != remote_hash:
                    # Diverged - need to merge/rebase
                    print("Local and remote have diverged.")
                    print("Attempting auto-merge...")

                    try:
                        result = merge_engine.merge(remote_branch)

                        if result.success:
                            print(f"Auto-merged with {remote_branch}")
                            # Update local hash after merge
                            local_hash = repo.refs.get_branch_commit(branch)
                        else:
                            print("Auto-merge failed with conflicts:")
                            for conflict in result.conflicts:
                                print(f"  - {conflict.path}")
                            print("\nResolve conflicts, commit, and try again.")
                            print("Or use --force to overwrite (not recommended).")
                            raise MemoryConflictError(result.message)

                    except MemoryConflictError:
                        return 1
                    except Exception as e:
                        print(f"Merge failed: {e}")
                        print("Use --no-rebase to skip auto-merge or --force to overwrite")
                        return 1

        # Push
        try:
            msg = remote.push(branch=branch)
            print(msg)
            return 0
        except ValueError as e:
            error_msg = str(e)
            if "non-fast-forward" in error_msg.lower() or "rejected" in error_msg.lower():
                print("Push rejected: remote has changes you don't have.")
                print("Run 'agmem pull' first, or use --force to overwrite.")
                return 1
            print(f"Error: {e}")
            return 1
