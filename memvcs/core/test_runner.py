"""
Test runner for agmem memory tests.

Implements CI/CD-style testing for agent memory to prevent hallucinated facts
from corrupting the knowledge base.
"""

import os
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


@dataclass
class TestCase:
    """A single test case for memory validation."""

    name: str
    query: str
    expected_fact: str
    confidence_threshold: float = 0.7
    required: bool = False  # If True, blocks commit on failure
    tags: List[str] = field(default_factory=list)


@dataclass
class TestFailure:
    """Represents a failed test."""

    test_name: str
    query: str
    expected: str
    actual: Optional[str]
    message: str
    is_critical: bool = False


@dataclass
class TestResult:
    """Result of running memory tests."""

    passed: bool
    total_count: int
    passed_count: int
    failed_count: int
    failures: List[TestFailure] = field(default_factory=list)
    duration_ms: int = 0


class TestRunner:
    """
    Runner for memory regression tests.

    Tests are defined in YAML files in the tests/ directory of the memory repo.
    """

    def __init__(self, repo, vector_store=None):
        """
        Initialize test runner.

        Args:
            repo: Repository instance
            vector_store: Optional VectorStore for semantic search tests
        """
        self.repo = repo
        self.vector_store = vector_store
        self.tests_dir = repo.root / "tests"

    def load_tests(self) -> List[TestCase]:
        """
        Load all test cases from the tests/ directory.

        Returns:
            List of TestCase objects
        """
        tests = []

        if not self.tests_dir.exists():
            return tests

        for test_file in self.tests_dir.glob("**/*.yaml"):
            tests.extend(self._load_test_file(test_file))

        for test_file in self.tests_dir.glob("**/*.yml"):
            tests.extend(self._load_test_file(test_file))

        for test_file in self.tests_dir.glob("**/*.json"):
            tests.extend(self._load_json_test_file(test_file))

        return tests

    def _load_test_file(self, path: Path) -> List[TestCase]:
        """Load tests from a YAML file."""
        if not YAML_AVAILABLE:
            return []

        try:
            with open(path) as f:
                data = yaml.safe_load(f)

            if not data or "tests" not in data:
                return []

            tests = []
            file_name = path.stem

            for i, test_data in enumerate(data["tests"]):
                name = test_data.get("name", f"{file_name}_{i}")
                tests.append(
                    TestCase(
                        name=name,
                        query=test_data["query"],
                        expected_fact=test_data["expected_fact"],
                        confidence_threshold=test_data.get("confidence_threshold", 0.7),
                        required=test_data.get("required", False),
                        tags=test_data.get("tags", []),
                    )
                )

            return tests

        except Exception as e:
            print(f"Warning: Failed to load test file {path}: {e}")
            return []

    def _load_json_test_file(self, path: Path) -> List[TestCase]:
        """Load tests from a JSON file."""
        try:
            with open(path) as f:
                data = json.load(f)

            if not data:
                return []

            # Support both array of tests and object with 'tests' key
            if isinstance(data, list):
                test_list = data
            elif "tests" in data:
                test_list = data["tests"]
            else:
                return []

            tests = []
            file_name = path.stem

            for i, test_data in enumerate(test_list):
                name = test_data.get("name", f"{file_name}_{i}")
                tests.append(
                    TestCase(
                        name=name,
                        query=test_data["query"],
                        expected_fact=test_data["expected_fact"],
                        confidence_threshold=test_data.get("confidence_threshold", 0.7),
                        required=test_data.get("required", False),
                        tags=test_data.get("tags", []),
                    )
                )

            return tests

        except Exception as e:
            print(f"Warning: Failed to load test file {path}: {e}")
            return []

    def run_test(self, test: TestCase) -> Optional[TestFailure]:
        """
        Run a single test case.

        Returns:
            TestFailure if test failed, None if passed
        """
        # If we have a vector store, use semantic search
        if self.vector_store:
            return self._run_semantic_test(test)
        else:
            # Fall back to simple text matching
            return self._run_text_test(test)

    def _run_semantic_test(self, test: TestCase) -> Optional[TestFailure]:
        """Run test using semantic search."""
        try:
            results = self.vector_store.search(test.query, k=5)

            if not results:
                return TestFailure(
                    test_name=test.name,
                    query=test.query,
                    expected=test.expected_fact,
                    actual=None,
                    message="No results found for query",
                    is_critical=test.required,
                )

            # Check if any result contains the expected fact
            for result in results:
                content = result.get("content", "")
                similarity = result.get("similarity", 0)

                if similarity >= test.confidence_threshold:
                    # Use simple string matching as judge
                    if self._fact_matches(test.expected_fact, content):
                        return None  # Test passed

            # No matching result found
            best_result = results[0] if results else {}
            return TestFailure(
                test_name=test.name,
                query=test.query,
                expected=test.expected_fact,
                actual=best_result.get("content", "")[:200],
                message=f"Expected fact not found in top results (best similarity: {best_result.get('similarity', 0):.2f})",
                is_critical=test.required,
            )

        except Exception as e:
            return TestFailure(
                test_name=test.name,
                query=test.query,
                expected=test.expected_fact,
                actual=None,
                message=f"Error running semantic test: {e}",
                is_critical=test.required,
            )

    def _run_text_test(self, test: TestCase) -> Optional[TestFailure]:
        """Run test using simple text search through memory files."""
        try:
            current_dir = self.repo.root / "current"

            if not current_dir.exists():
                return TestFailure(
                    test_name=test.name,
                    query=test.query,
                    expected=test.expected_fact,
                    actual=None,
                    message="No current/ directory found",
                    is_critical=test.required,
                )

            # Search through all memory files
            for memory_file in current_dir.glob("**/*.md"):
                try:
                    content = memory_file.read_text()
                    if self._fact_matches(test.expected_fact, content):
                        return None  # Test passed
                except Exception:
                    continue

            return TestFailure(
                test_name=test.name,
                query=test.query,
                expected=test.expected_fact,
                actual=None,
                message="Expected fact not found in any memory file",
                is_critical=test.required,
            )

        except Exception as e:
            return TestFailure(
                test_name=test.name,
                query=test.query,
                expected=test.expected_fact,
                actual=None,
                message=f"Error running text test: {e}",
                is_critical=test.required,
            )

    def _fact_matches(self, expected: str, content: str) -> bool:
        """
        Check if expected fact is present in content.

        Uses case-insensitive substring matching.
        For more sophisticated matching, this could use an LLM judge.
        """
        expected_lower = expected.lower()
        content_lower = content.lower()

        # Direct substring match
        if expected_lower in content_lower:
            return True

        # Check if all key words are present
        key_words = expected_lower.split()
        if len(key_words) > 2:
            matches = sum(1 for word in key_words if word in content_lower)
            if matches >= len(key_words) * 0.8:  # 80% of words match
                return True

        return False

    def run_all(self, tags: Optional[List[str]] = None) -> TestResult:
        """
        Run all tests.

        Args:
            tags: Optional list of tags to filter tests

        Returns:
            TestResult with overall results
        """
        start_time = datetime.now()
        tests = self.load_tests()

        # Filter by tags if specified
        if tags:
            tests = [t for t in tests if any(tag in t.tags for tag in tags)]

        failures = []
        passed_count = 0

        for test in tests:
            failure = self.run_test(test)
            if failure:
                failures.append(failure)
            else:
                passed_count += 1

        duration = (datetime.now() - start_time).total_seconds() * 1000

        # Check if any critical tests failed
        critical_failures = [f for f in failures if f.is_critical]
        passed = len(critical_failures) == 0

        return TestResult(
            passed=passed,
            total_count=len(tests),
            passed_count=passed_count,
            failed_count=len(failures),
            failures=failures,
            duration_ms=int(duration),
        )

    def run_for_branch(self, branch: str) -> TestResult:
        """
        Run tests against a specific branch.

        Creates a temporary vector store with only the branch's data.

        Args:
            branch: Branch name to test

        Returns:
            TestResult
        """
        # For now, just run normal tests
        # TODO: Implement branch-specific testing with temporary vector store
        return self.run_all()


def create_test_template() -> str:
    """Create a template test file."""
    return """# Memory Tests
# Tests are run with 'agmem test' to validate memory consistency

tests:
  - name: "example_test"
    query: "What is the main purpose of this project?"
    expected_fact: "version control for agent memory"
    confidence_threshold: 0.7
    required: false
    tags:
      - "core"
      - "basics"

  # Add more tests below:
  # - name: "test_name"
  #   query: "Your query here"
  #   expected_fact: "Expected answer"
  #   required: true  # Set to true for critical tests that block commits
"""
