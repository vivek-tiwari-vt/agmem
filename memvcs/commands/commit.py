"""
agmem commit - Save staged changes as a snapshot.
"""

import argparse
from datetime import datetime

from ..commands.base import require_repo
from ..core.schema import SchemaValidator
from ..core.hooks import run_pre_commit_hooks, compute_suggested_importance


class CommitCommand:
    """Create a commit from staged changes."""

    name = "commit"
    help = "Save staged changes as a memory snapshot"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            "-m", "--message", required=True, help="Commit message describing the changes"
        )
        parser.add_argument("--author", help="Override default author")
        parser.add_argument(
            "--no-verify", action="store_true", help="Skip pre-commit hooks and schema validation"
        )
        parser.add_argument("--strict", action="store_true", help="Treat schema warnings as errors")
        parser.add_argument(
            "--run-tests", action="store_true", help="Run memory tests before committing"
        )
        parser.add_argument(
            "--importance",
            type=float,
            metavar="SCORE",
            help="Importance score 0.0-1.0 for recall/decay weighting",
        )

    @staticmethod
    def _get_blob_hash(file_info) -> str:
        """Get blob hash from StagedFile or dict (for hooks that pass either)."""
        if hasattr(file_info, "blob_hash"):
            return file_info.blob_hash
        if isinstance(file_info, dict):
            return file_info.get("blob_hash") or file_info.get("hash") or ""
        return ""

    @staticmethod
    def _validate_staged_files(repo, staged: dict, strict: bool) -> tuple:
        """
        Validate staged files for schema compliance.

        Returns:
            Tuple of (success, validation_results)
        """
        validation_results = {}
        has_errors = False

        for filepath, file_info in staged.items():
            blob_hash = CommitCommand._get_blob_hash(file_info)
            if not blob_hash:
                continue

            # Read content from object store
            from ..core.objects import Blob

            blob = Blob.load(repo.object_store, blob_hash)
            if not blob:
                continue

            try:
                content = blob.content.decode("utf-8")
            except UnicodeDecodeError:
                # Skip binary files
                continue

            # Validate the file
            result = SchemaValidator.validate(content, filepath, strict=strict)
            validation_results[filepath] = result

            if not result.valid:
                has_errors = True

        return not has_errors, validation_results

    @staticmethod
    def _print_validation_results(results: dict) -> None:
        """Print validation results in a readable format."""
        for filepath, result in results.items():
            if not result.valid or result.warnings:
                print(f"\n  {filepath}:")
                for error in result.errors:
                    print(f"    ✗ {error.field}: {error.message}")
                for warning in result.warnings:
                    print(f"    ⚠ {warning.field}: {warning.message}")

    @staticmethod
    def _run_hooks_and_validation(repo, staged: dict, args) -> tuple:
        """Run pre-commit hooks and schema validation. Returns (success, error_code or 0)."""
        hook_result = run_pre_commit_hooks(repo, staged)
        if not hook_result.success:
            print("Pre-commit hook failed:")
            for error in hook_result.errors:
                print(f"  ✗ {error}")
            print("\nUse --no-verify to bypass hooks (not recommended).")
            return False, 1
        valid, results = CommitCommand._validate_staged_files(repo, staged, strict=args.strict)
        if not valid:
            print("Schema validation failed:")
            CommitCommand._print_validation_results(results)
            print("\nFix the errors above or use --no-verify to bypass validation.")
            return False, 1
        if any(r.warnings for r in results.values()):
            print("Schema validation warnings:")
            CommitCommand._print_validation_results(results)
        return True, 0

    @staticmethod
    def _run_memory_tests(repo) -> int:
        """Run memory tests if available. Returns 1 on failure, 0 on success or skip."""
        try:
            from ..core.test_runner import TestRunner

            test_runner = TestRunner(repo)
            test_result = test_runner.run_all()
            if not test_result.passed:
                print("Memory tests failed:")
                for failure in test_result.failures:
                    print(f"  ✗ {failure.test_name}: {failure.message}")
                print("\nFix failing tests before committing.")
                return 1
            print(f"Memory tests passed: {test_result.passed_count}/{test_result.total_count}")
        except ImportError:
            print("Warning: Test runner not available. Skipping tests.")
        return 0

    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code
        staged = repo.staging.get_staged_files()
        if not staged:
            print("Error: No changes staged for commit.")
            print("Run 'agmem add <file>' to stage changes first.")
            return 1
        if not args.no_verify:
            ok, err = CommitCommand._run_hooks_and_validation(repo, staged, args)
            if not ok:
                return err
        if args.run_tests:
            if CommitCommand._run_memory_tests(repo) != 0:
                return 1
        metadata = {"files_changed": len(staged), "timestamp": datetime.utcnow().isoformat() + "Z"}
        # Importance scoring: explicit --importance or auto from heuristics
        if args.importance is not None:
            if not (0.0 <= args.importance <= 1.0):
                print("Error: --importance must be between 0.0 and 1.0")
                return 1
            metadata["importance"] = args.importance
        else:
            suggested = compute_suggested_importance(repo, staged, args.message, metadata)
            metadata["importance"] = suggested
        if args.author:
            config = repo.get_config()
            config["author"]["name"] = args.author
            repo.set_config(config)
        try:
            commit_hash = repo.commit(args.message, metadata)
            print(f"[{repo.refs.get_current_branch() or 'HEAD'} {commit_hash[:8]}] {args.message}")
            print(f"  {len(staged)} file(s) changed")
            return 0
        except Exception as e:
            print(f"Error creating commit: {e}")
            return 1
