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
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Accept conditionally trusted remote commits without prompting",
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
                    from memvcs.core.crypto_verify import verify_commit_optional
                    verify_commit_optional(
                        repo.object_store, remote_hash, mem_dir=repo.mem_dir, strict=False
                    )
                    # Trust check: block or require confirmation for untrusted/conditional
                    from memvcs.core.objects import Commit
                    from memvcs.core.trust import find_verifying_key, get_trust_level
                    remote_commit = Commit.load(repo.object_store, remote_hash)
                    if remote_commit and remote_commit.metadata:
                        key_pem = find_verifying_key(repo.mem_dir, remote_commit.metadata)
                        if key_pem is not None:
                            level = get_trust_level(repo.mem_dir, key_pem)
                            if level == "untrusted":
                                print(f"Pull blocked: remote commit signed by untrusted key.")
                                return 1
                            if level == "conditional" and not getattr(args, "yes", False):
                                print("Remote commit from conditionally trusted key. Use --yes to merge.")
                                return 1
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
