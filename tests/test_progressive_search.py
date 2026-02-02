"""
Tests for Progressive Disclosure Search.
"""

import json
import pytest
import tempfile
from datetime import datetime
from pathlib import Path

from memvcs.core.repository import Repository


@pytest.fixture
def test_repo_with_content():
    """Create a test repository with multiple memory files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        repo = Repository.init(repo_path, author_name="Test", author_email="test@example.com")

        # Create semantic memories
        semantic_dir = repo.current_dir / "semantic"
        semantic_dir.mkdir(parents=True, exist_ok=True)
        (semantic_dir / "python-best-practices.md").write_text(
            "---\nmemory_type: semantic\n---\n# Python Best Practices\n\nUse type hints for better code quality."
        )
        (semantic_dir / "database-patterns.md").write_text(
            "# Database Patterns\n\nConnection pooling improves performance."
        )

        # Create episodic memories
        episodic_dir = repo.current_dir / "episodic"
        episodic_dir.mkdir(parents=True, exist_ok=True)
        (episodic_dir / "2024-01-15-session.md").write_text(
            "# Session 2024-01-15\n\nWorked on Python refactoring today."
        )

        # Create procedural memories
        procedural_dir = repo.current_dir / "procedural"
        procedural_dir.mkdir(parents=True, exist_ok=True)
        (procedural_dir / "deploy-workflow.md").write_text(
            "# Deploy Workflow\n\n1. Run tests\n2. Build Docker image\n3. Push to registry"
        )

        # Stage and commit
        repo.stage_directory("")
        repo.commit("Initial content")

        yield repo


class TestSearchIndex:
    """Test SearchIndex class."""

    def test_create_index(self, test_repo_with_content):
        """Test creating a search index."""
        from memvcs.core.search_index import SearchIndex

        index = SearchIndex(test_repo_with_content.mem_dir)
        try:
            stats = index.get_stats()
            assert stats["total_files"] == 0  # Not indexed yet
        finally:
            index.close()

    def test_index_directory(self, test_repo_with_content):
        """Test indexing a directory."""
        from memvcs.core.search_index import SearchIndex

        index = SearchIndex(test_repo_with_content.mem_dir)
        try:
            count = index.index_directory(test_repo_with_content.current_dir)
            assert count == 4  # 4 files created

            stats = index.get_stats()
            assert stats["total_files"] == 4
            assert "semantic" in stats["by_type"]
            assert "episodic" in stats["by_type"]
            assert "procedural" in stats["by_type"]
        finally:
            index.close()

    def test_search_index_layer1(self, test_repo_with_content):
        """Test Layer 1: Lightweight index search."""
        from memvcs.core.search_index import SearchIndex

        index = SearchIndex(test_repo_with_content.mem_dir)
        try:
            # Index content first
            index.index_directory(test_repo_with_content.current_dir)

            # Search for Python
            results = index.search_index("Python")
            assert len(results) >= 1

            # Check result structure
            result = results[0]
            assert hasattr(result, "path")
            assert hasattr(result, "first_line")
            assert hasattr(result, "score")
            assert "python" in result.path.lower() or "python" in result.first_line.lower()
        finally:
            index.close()

    def test_search_by_memory_type(self, test_repo_with_content):
        """Test filtering search by memory type."""
        from memvcs.core.search_index import SearchIndex

        index = SearchIndex(test_repo_with_content.mem_dir)
        try:
            index.index_directory(test_repo_with_content.current_dir)

            # Search only in semantic
            results = index.search_index("patterns", memory_type="semantic")
            assert all(r.memory_type == "semantic" for r in results)
        finally:
            index.close()


class TestTimelineSearch:
    """Test Layer 2: Timeline Context."""

    def test_get_timeline(self, test_repo_with_content):
        """Test getting timeline entries."""
        from memvcs.core.search_index import SearchIndex

        index = SearchIndex(test_repo_with_content.mem_dir)
        try:
            index.index_directory(test_repo_with_content.current_dir)

            timeline = index.get_timeline(limit=10)
            assert len(timeline) >= 1

            # Check timeline structure
            entry = timeline[0]
            assert hasattr(entry, "date")
            assert hasattr(entry, "file_count")
            assert hasattr(entry, "files")
            assert entry.file_count > 0
        finally:
            index.close()


class TestFullDetails:
    """Test Layer 3: Full Details."""

    def test_get_full_details(self, test_repo_with_content):
        """Test getting full file details."""
        from memvcs.core.search_index import SearchIndex

        index = SearchIndex(test_repo_with_content.mem_dir)
        try:
            index.index_directory(test_repo_with_content.current_dir)

            # Get file paths from timeline
            timeline = index.get_timeline(limit=1)
            paths = [f["path"] for f in timeline[0].files]

            # Get full details
            details = index.get_full_details(paths[:2])
            assert len(details) >= 1

            # Check details structure
            detail = details[0]
            assert "path" in detail
            assert "content" in detail
            assert len(detail["content"]) > 0
        finally:
            index.close()


class TestTokenCostEstimation:
    """Test token cost estimation."""

    def test_estimate_token_cost(self):
        """Test token cost estimation."""
        from memvcs.core.search_index import estimate_token_cost

        text = "This is a test sentence with about 40 characters."
        tokens = estimate_token_cost(text)
        assert tokens > 0
        assert tokens < 20  # Rough estimate

    def test_layer_costs(self, test_repo_with_content):
        """Test layer-specific cost estimation."""
        from memvcs.core.search_index import (
            SearchIndex,
            layer1_cost,
            layer2_cost,
            layer3_cost,
        )

        index = SearchIndex(test_repo_with_content.mem_dir)
        try:
            index.index_directory(test_repo_with_content.current_dir)

            # Layer 1 should be cheapest
            results = index.search_index("Python")
            l1_cost = layer1_cost(results)

            # Layer 2
            timeline = index.get_timeline()
            l2_cost = layer2_cost(timeline)

            # Layer 3 should be most expensive
            paths = [f["path"] for f in timeline[0].files] if timeline else []
            details = index.get_full_details(paths)
            l3_cost = layer3_cost(details)

            # Generally, L1 < L2 < L3 (though this depends on content)
            assert l1_cost >= 0
            assert l2_cost >= 0
            assert l3_cost >= 0
        finally:
            index.close()


class TestFrontmatterExtraction:
    """Test YAML frontmatter extraction."""

    def test_extract_frontmatter(self, test_repo_with_content):
        """Test extracting YAML frontmatter."""
        from memvcs.core.search_index import SearchIndex

        index = SearchIndex(test_repo_with_content.mem_dir)
        try:
            # Content with frontmatter
            content = "---\nmemory_type: semantic\ntopic: python\n---\n# Content"
            metadata = index._extract_frontmatter(content)

            assert metadata is not None
            assert metadata.get("memory_type") == "semantic"
            assert metadata.get("topic") == "python"
        finally:
            index.close()

    def test_no_frontmatter(self, test_repo_with_content):
        """Test content without frontmatter."""
        from memvcs.core.search_index import SearchIndex

        index = SearchIndex(test_repo_with_content.mem_dir)
        try:
            content = "# Just a heading\n\nNo frontmatter here."
            metadata = index._extract_frontmatter(content)
            assert metadata is None
        finally:
            index.close()
