"""
agmem fsck - File system consistency check.
"""

import argparse
from pathlib import Path

from ..commands.base import require_repo


class FsckCommand:
    """Check and repair repository consistency."""

    name = "fsck"
    help = "Check and repair repository consistency (remove dangling vectors)"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Show what would be done without making changes"
        )
        parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
        parser.add_argument(
            "--fix",
            action="store_true",
            help="Actually remove dangling entries (required to make changes)",
        )

    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code

        print("Running file system consistency check...")

        issues_found = 0
        issues_fixed = 0

        # Check vector store for dangling entries
        try:
            from ..core.vector_store import VectorStore

            vs = VectorStore(repo.root / ".mem")

            vector_issues, vector_fixed = FsckCommand._check_vectors(
                repo, vs, args.dry_run, args.verbose, args.fix
            )
            issues_found += vector_issues
            issues_fixed += vector_fixed
        except ImportError:
            if args.verbose:
                print("Vector store not available, skipping vector check")
        except Exception as e:
            print(f"Warning: Vector store check failed: {e}")

        # Check object store integrity
        obj_issues, obj_fixed = FsckCommand._check_objects(
            repo, args.dry_run, args.verbose, args.fix
        )
        issues_found += obj_issues
        issues_fixed += obj_fixed

        # Check refs integrity
        ref_issues, ref_fixed = FsckCommand._check_refs(repo, args.dry_run, args.verbose, args.fix)
        issues_found += ref_issues
        issues_fixed += ref_fixed

        # Cryptographic verification (Merkle + signature)
        crypto_issues = FsckCommand._check_crypto(repo, args.verbose)
        issues_found += crypto_issues

        # Print summary
        print()
        print("=" * 40)
        print("FSCK Summary")
        print("=" * 40)
        print(f"Issues found: {issues_found}")

        if args.fix:
            print(f"Issues fixed: {issues_fixed}")
        elif issues_found > 0:
            print("\nRun with --fix to repair issues")

        if issues_found == 0:
            print("Repository is healthy!")

        return 0 if issues_found == 0 else 1

    @staticmethod
    def _check_vectors(repo, vs, dry_run: bool, verbose: bool, fix: bool) -> tuple:
        """Check for dangling vector entries."""
        print("\nChecking vector store...")

        current_dir = repo.root / "current"
        entries = vs.get_all_entries()

        dangling = []

        for entry in entries:
            path = entry["path"]
            full_path = current_dir / path

            if not full_path.exists():
                dangling.append(entry)
                if verbose:
                    print(f"  Dangling: {path} (rowid: {entry['rowid']})")

        if dangling:
            print(f"  Found {len(dangling)} dangling vector entries")

            if fix and not dry_run:
                fixed = 0
                for entry in dangling:
                    if vs.delete_entry(entry["rowid"]):
                        fixed += 1
                print(f"  Removed {fixed} dangling entries")
                return len(dangling), fixed
            elif dry_run:
                print("  (dry-run: no changes made)")
        else:
            print("  Vector store is consistent")

        return len(dangling), 0

    @staticmethod
    def _check_objects(repo, dry_run: bool, verbose: bool, fix: bool) -> tuple:
        """Check object store integrity."""
        print("\nChecking object store...")

        issues = 0

        # Check if all referenced blobs exist
        for obj_type in ["blob", "tree", "commit", "tag"]:
            obj_dir = repo.root / ".mem" / "objects" / obj_type
            if not obj_dir.exists():
                continue

            for prefix_dir in obj_dir.iterdir():
                if not prefix_dir.is_dir():
                    continue
                for obj_file in prefix_dir.iterdir():
                    try:
                        # Try to read and decompress
                        import zlib

                        compressed = obj_file.read_bytes()
                        zlib.decompress(compressed)
                    except Exception as e:
                        issues += 1
                        if verbose:
                            hash_id = prefix_dir.name + obj_file.name
                            print(f"  Corrupted {obj_type}: {hash_id[:8]}...")

        if issues == 0:
            print("  Object store is consistent")
        else:
            print(f"  Found {issues} corrupted objects")

        return issues, 0  # Object repair not implemented

    @staticmethod
    def _check_refs(repo, dry_run: bool, verbose: bool, fix: bool) -> tuple:
        """Check refs integrity."""
        print("\nChecking refs...")

        issues = 0

        # Check if HEAD points to valid commit
        head = repo.refs.get_head()
        if head["type"] == "branch":
            branch_commit = repo.refs.get_branch_commit(head["value"])
            if not branch_commit:
                issues += 1
                if verbose:
                    print(f"  HEAD branch '{head['value']}' has no commit")
            elif not repo.object_store.exists(branch_commit, "commit"):
                issues += 1
                if verbose:
                    print(f"  HEAD points to missing commit: {branch_commit[:8]}")
        elif head["type"] == "detached":
            if not repo.object_store.exists(head["value"], "commit"):
                issues += 1
                if verbose:
                    print(f"  Detached HEAD points to missing commit")

        # Check all branches
        branches = repo.refs.list_branches()
        for branch in branches:
            commit_hash = repo.refs.get_branch_commit(branch)
            if commit_hash and not repo.object_store.exists(commit_hash, "commit"):
                issues += 1
                if verbose:
                    print(f"  Branch '{branch}' points to missing commit")

        if issues == 0:
            print("  Refs are consistent")
        else:
            print(f"  Found {issues} ref issues")

        return issues, 0

    @staticmethod
    def _check_crypto(repo, verbose: bool) -> int:
        """Verify Merkle/signature on branch tips. Returns number of issues."""
        print("\nChecking commit signatures...")
        try:
            from ..core.crypto_verify import verify_commit, load_public_key
        except ImportError:
            if verbose:
                print("  Crypto verification not available")
            return 0
        issues = 0
        pub = load_public_key(repo.mem_dir)
        for branch in repo.refs.list_branches():
            ch = repo.refs.get_branch_commit(branch)
            if not ch:
                continue
            ok, err = verify_commit(
                repo.object_store, ch, public_key_pem=pub, mem_dir=repo.mem_dir
            )
            if not ok:
                issues += 1
                if verbose:
                    print(f"  {branch} ({ch[:8]}): {err}")
        if issues == 0:
            print("  Commit signatures consistent")
        else:
            print(f"  Found {issues} commit(s) with verification issues")
        return issues
