"""
agmem test - Run memory regression tests.
"""

import argparse
from pathlib import Path

from ..commands.base import require_repo
from ..core.test_runner import TestRunner, create_test_template


class TestCommand:
    """Run memory regression tests."""
    
    name = 'test'
    help = 'Run memory regression tests to validate knowledge consistency'
    
    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            '--branch',
            help='Run tests against a specific branch'
        )
        parser.add_argument(
            '--tags',
            nargs='+',
            help='Filter tests by tags'
        )
        parser.add_argument(
            '--init',
            action='store_true',
            help='Initialize tests directory with template'
        )
        parser.add_argument(
            '-v', '--verbose',
            action='store_true',
            help='Show detailed test output'
        )
        parser.add_argument(
            '--fail-fast',
            action='store_true',
            help='Stop on first failure'
        )
    
    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code
        
        # Handle --init
        if args.init:
            return TestCommand._init_tests(repo)
        
        # Try to get vector store
        vector_store = None
        try:
            from ..core.vector_store import VectorStore
            vector_store = VectorStore(repo.root / '.mem')
        except ImportError:
            if args.verbose:
                print("Note: Vector store not available, using text-based tests")
        except Exception as e:
            if args.verbose:
                print(f"Note: Could not initialize vector store: {e}")
        
        # Create test runner
        runner = TestRunner(repo, vector_store)
        
        # Load and check for tests
        tests = runner.load_tests()
        if not tests:
            print("No tests found.")
            print("Create test files in tests/ directory or run 'agmem test --init'")
            return 0
        
        print(f"Running {len(tests)} tests...")
        
        # Run tests
        if args.branch:
            result = runner.run_for_branch(args.branch)
        else:
            result = runner.run_all(tags=args.tags)
        
        # Print results
        print()
        
        if result.failures:
            print("Failed tests:")
            for failure in result.failures:
                critical_marker = " [CRITICAL]" if failure.is_critical else ""
                print(f"  ✗ {failure.test_name}{critical_marker}")
                if args.verbose:
                    print(f"    Query: {failure.query}")
                    print(f"    Expected: {failure.expected}")
                    if failure.actual:
                        print(f"    Got: {failure.actual[:100]}...")
                    print(f"    Error: {failure.message}")
                print()
        
        # Summary
        status = "PASSED" if result.passed else "FAILED"
        critical_failures = [f for f in result.failures if f.is_critical]
        
        print(f"{'='*50}")
        print(f"Results: {result.passed_count}/{result.total_count} tests passed")
        if critical_failures:
            print(f"Critical failures: {len(critical_failures)}")
        print(f"Duration: {result.duration_ms}ms")
        print(f"Status: {status}")
        print(f"{'='*50}")
        
        return 0 if result.passed else 1
    
    @staticmethod
    def _init_tests(repo) -> int:
        """Initialize tests directory with template."""
        tests_dir = repo.root / 'tests'
        tests_dir.mkdir(exist_ok=True)
        
        template_file = tests_dir / 'example_tests.yaml'
        
        if template_file.exists():
            print(f"Test template already exists: {template_file}")
            return 0
        
        template_file.write_text(create_test_template())
        print(f"Created test template: {template_file}")
        print("\nEdit this file to add your memory tests.")
        print("Run 'agmem test' to execute them.")
        
        return 0
