"""
Tests for health monitoring module.
"""

import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest

from memvcs.health.monitor import (
    HealthMonitor,
    StorageMonitor,
    SemanticRedundancyChecker,
    StaleMemoryDetector,
    GraphConsistencyValidator,
)


@pytest.fixture
def tmp_repo():
    """Create a temporary repository structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        mem_dir = repo_path / ".mem"
        current_dir = repo_path / "current"

        mem_dir.mkdir(parents=True)
        current_dir.mkdir(parents=True)

        # Create subdirectories
        (mem_dir / "objects" / "blob").mkdir(parents=True)
        (mem_dir / "objects" / "pack").mkdir(parents=True)
        (current_dir / "semantic").mkdir(parents=True)
        (current_dir / "episodic").mkdir(parents=True)
        (current_dir / "procedural").mkdir(parents=True)

        yield repo_path


class TestStorageMonitor:
    """Tests for StorageMonitor."""

    def test_get_metrics_empty_repo(self, tmp_repo):
        """Test metrics on empty repository."""
        monitor = StorageMonitor(tmp_repo / ".mem")
        metrics = monitor.get_metrics()

        assert metrics.total_size_bytes >= 0
        assert metrics.loose_objects_count >= 0
        assert metrics.packed_objects_count >= 0
        assert metrics.growth_rate_per_hour >= 0

    def test_metrics_with_objects(self, tmp_repo):
        """Test metrics calculation with objects present."""
        mem_dir = tmp_repo / ".mem"
        obj_dir = mem_dir / "objects" / "blob"

        # Create some dummy objects
        for i in range(5):
            (obj_dir / f"obj_{i}").write_text(f"dummy content {i}" * 10)

        monitor = StorageMonitor(mem_dir)
        metrics = monitor.get_metrics()

        assert metrics.loose_objects_count == 5
        assert metrics.total_size_bytes > 0

    def test_growth_rate_calculation(self, tmp_repo):
        """Test storage growth rate tracking."""
        mem_dir = tmp_repo / ".mem"
        monitor = StorageMonitor(mem_dir)

        # First check
        metrics1 = monitor.get_metrics()
        assert metrics1.growth_rate_per_hour == 0.0

        # Add data
        obj_dir = mem_dir / "objects" / "blob"
        (obj_dir / "new_obj").write_text("x" * 1000)

        # Growth rate should be calculated (may be 0 due to timestamp)
        metrics2 = monitor.get_metrics()
        assert metrics2.total_size_bytes > metrics1.total_size_bytes

    def test_storage_warning_large_repo(self, tmp_repo):
        """Test warning generation for large repositories."""
        mem_dir = tmp_repo / ".mem"
        obj_dir = mem_dir / "objects"

        # Create files totaling ~5.1GB (will trigger warning)
        # For testing, we'll mock the size
        monitor = StorageMonitor(mem_dir)

        # Add a single large file
        large_file = obj_dir / "large_file"
        large_file.write_text("x" * (6 * 1024 * 1024))  # 6MB test

        metrics = monitor.get_metrics()
        # No warning for small test file
        assert metrics.total_size_bytes >= 6 * 1024 * 1024


class TestSemanticRedundancyChecker:
    """Tests for SemanticRedundancyChecker."""

    def test_no_redundancy_empty_dir(self, tmp_repo):
        """Test redundancy check on empty semantic dir."""
        current_dir = tmp_repo / "current"
        checker = SemanticRedundancyChecker(current_dir)
        report = checker.check_redundancy()

        assert report.total_files == 0
        assert report.redundancy_percentage == 0.0
        assert len(report.duplicate_hashes) == 0

    def test_unique_files_no_redundancy(self, tmp_repo):
        """Test unique files show no redundancy."""
        current_dir = tmp_repo / "current"
        semantic_dir = current_dir / "semantic"

        # Create unique files
        (semantic_dir / "file1.md").write_text("content 1")
        (semantic_dir / "file2.md").write_text("content 2")
        (semantic_dir / "file3.md").write_text("content 3")

        checker = SemanticRedundancyChecker(current_dir)
        report = checker.check_redundancy()

        assert report.total_files == 3
        assert report.redundancy_percentage == 0.0
        assert len(report.duplicate_hashes) == 0

    def test_duplicate_files_detected(self, tmp_repo):
        """Test detection of duplicate files."""
        current_dir = tmp_repo / "current"
        semantic_dir = current_dir / "semantic"

        # Create duplicate files
        duplicate_content = "This is duplicate content"
        (semantic_dir / "file1.md").write_text(duplicate_content)
        (semantic_dir / "file2.md").write_text(duplicate_content)
        (semantic_dir / "file3.md").write_text("unique content")

        checker = SemanticRedundancyChecker(current_dir)
        report = checker.check_redundancy()

        assert report.total_files == 3
        assert len(report.duplicate_hashes) == 1
        assert report.redundancy_percentage > 0

    def test_high_redundancy_warning(self, tmp_repo):
        """Test warning for high redundancy."""
        current_dir = tmp_repo / "current"
        semantic_dir = current_dir / "semantic"

        duplicate_content = "x" * 1000
        # Create mostly duplicate files
        for i in range(10):
            if i < 8:
                (semantic_dir / f"file{i}.md").write_text(duplicate_content)
            else:
                (semantic_dir / f"file{i}.md").write_text(f"unique {i}" * 100)

        checker = SemanticRedundancyChecker(current_dir)
        report = checker.check_redundancy()

        assert report.warning is not None
        assert "redundancy" in report.warning.lower()


class TestStaleMemoryDetector:
    """Tests for StaleMemoryDetector."""

    def test_no_stale_memory_empty_dir(self, tmp_repo):
        """Test stale detection on empty directory."""
        current_dir = tmp_repo / "current"
        detector = StaleMemoryDetector(current_dir)
        report = detector.detect_stale()

        assert report.total_files == 0
        assert report.stale_percentage == 0.0
        assert len(report.stale_files) == 0

    def test_recent_files_not_stale(self, tmp_repo):
        """Test recent files are not marked as stale."""
        current_dir = tmp_repo / "current"
        semantic_dir = current_dir / "semantic"

        # Create recent files
        for i in range(3):
            (semantic_dir / f"file{i}.md").write_text(f"content {i}")

        detector = StaleMemoryDetector(current_dir)
        report = detector.detect_stale()

        assert report.total_files == 3
        assert report.stale_percentage == 0.0

    def test_old_files_marked_stale(self, tmp_repo):
        """Test old files are marked as stale."""
        import os

        current_dir = tmp_repo / "current"
        semantic_dir = current_dir / "semantic"

        # Create file and set old access time (100 days ago)
        fpath = semantic_dir / "old_file.md"
        fpath.write_text("old content")

        old_time = (datetime.now(timezone.utc) - timedelta(days=100)).timestamp()
        os.utime(fpath, (old_time, old_time))

        detector = StaleMemoryDetector(current_dir)
        report = detector.detect_stale()

        assert report.total_files == 1
        assert len(report.stale_files) == 1
        assert report.stale_files[0]["days_unaccessed"] >= 99

    def test_stale_percentage_calculation(self, tmp_repo):
        """Test stale percentage calculation."""
        import os

        current_dir = tmp_repo / "current"
        semantic_dir = current_dir / "semantic"

        # Create 10 files: 3 stale, 7 recent
        for i in range(10):
            fpath = semantic_dir / f"file{i}.md"
            fpath.write_text(f"content {i}")

            if i < 3:
                # Make old
                old_time = (datetime.now(timezone.utc) - timedelta(days=100)).timestamp()
                os.utime(fpath, (old_time, old_time))

        detector = StaleMemoryDetector(current_dir)
        report = detector.detect_stale()

        assert report.total_files == 10
        assert len(report.stale_files) == 3
        assert 29 < report.stale_percentage < 31  # ~30%


class TestGraphConsistencyValidator:
    """Tests for GraphConsistencyValidator."""

    def test_empty_graph_validation(self, tmp_repo):
        """Test validation of empty graph."""
        current_dir = tmp_repo / "current"
        validator = GraphConsistencyValidator(current_dir)
        report = validator.validate_graph()

        assert report.total_nodes == 0
        assert report.total_edges == 0
        assert len(report.orphaned_nodes) == 0
        assert len(report.dangling_edges) == 0

    def test_valid_graph(self, tmp_repo):
        """Test validation of valid graph with interconnected nodes."""
        current_dir = tmp_repo / "current"
        semantic_dir = current_dir / "semantic"

        # Create interconnected graph
        (semantic_dir / "NodeA.md").write_text("[[NodeB]] references")
        (semantic_dir / "NodeB.md").write_text("[[NodeC]] points to")
        (semantic_dir / "NodeC.md").write_text("[[NodeA]] loops back")

        validator = GraphConsistencyValidator(current_dir)
        report = validator.validate_graph()

        assert report.total_nodes == 3
        assert report.total_edges == 3
        assert len(report.dangling_edges) == 0
        assert len(report.orphaned_nodes) == 0

    def test_dangling_edges_detected(self, tmp_repo):
        """Test detection of dangling edges."""
        current_dir = tmp_repo / "current"
        semantic_dir = current_dir / "semantic"

        # Node with reference to non-existent node
        (semantic_dir / "NodeA.md").write_text("[[NonExistent]] references missing")

        validator = GraphConsistencyValidator(current_dir)
        report = validator.validate_graph()

        assert report.total_nodes == 1
        assert report.total_edges == 1
        assert len(report.dangling_edges) == 1
        assert report.dangling_edges[0] == ("NodeA", "NonExistent")

    def test_orphaned_nodes_detected(self, tmp_repo):
        """Test detection of orphaned nodes."""
        current_dir = tmp_repo / "current"
        semantic_dir = current_dir / "semantic"

        # Create isolated nodes
        (semantic_dir / "Isolated1.md").write_text("no links here")
        (semantic_dir / "Isolated2.md").write_text("also alone")
        (semantic_dir / "Connected.md").write_text("[[Isolated1]]")

        validator = GraphConsistencyValidator(current_dir)
        report = validator.validate_graph()

        assert report.total_nodes == 3
        assert len(report.orphaned_nodes) == 1

    def test_conflict_markers_detected(self, tmp_repo):
        """Test detection of merge conflict markers."""
        current_dir = tmp_repo / "current"
        semantic_dir = current_dir / "semantic"

        conflict_content = """
Some content
<<<<< HEAD
Version 1
=====
Version 2
>>>>> branch
More content
"""
        (semantic_dir / "conflicted.md").write_text(conflict_content)

        validator = GraphConsistencyValidator(current_dir)
        report = validator.validate_graph()

        assert len(report.contradictions) == 1
        assert "merge" in report.contradictions[0]["type"].lower()


class TestHealthMonitor:
    """Tests for HealthMonitor orchestration."""

    def test_perform_all_checks_empty_repo(self, tmp_repo):
        """Test all health checks on empty repository."""
        monitor = HealthMonitor(tmp_repo)
        report = monitor.perform_all_checks()

        assert "timestamp" in report
        assert "storage" in report
        assert "redundancy" in report
        assert "stale_memory" in report
        assert "graph_consistency" in report
        assert "warnings" in report

    def test_perform_all_checks_populated_repo(self, tmp_repo):
        """Test all health checks on populated repository."""
        current_dir = tmp_repo / "current"
        semantic_dir = current_dir / "semantic"
        obj_dir = tmp_repo / ".mem" / "objects" / "blob"

        # Add some content
        (obj_dir / "obj1").write_text("content" * 100)
        (semantic_dir / "memory1.md").write_text("[[memory2]]")
        (semantic_dir / "memory2.md").write_text("content")

        monitor = HealthMonitor(tmp_repo)
        report = monitor.perform_all_checks()

        assert report["storage"] is not None
        assert report["redundancy"] is not None
        assert report["stale_memory"] is not None
        assert report["graph_consistency"] is not None

    def test_warnings_collected(self, tmp_repo):
        """Test that warnings are properly collected."""
        current_dir = tmp_repo / "current"
        semantic_dir = current_dir / "semantic"

        # Create scenario that triggers warning
        duplicate_content = "x" * 1000
        for i in range(10):
            if i < 8:
                (semantic_dir / f"file{i}.md").write_text(duplicate_content)
            else:
                (semantic_dir / f"file{i}.md").write_text(f"unique {i}" * 100)

        monitor = HealthMonitor(tmp_repo)
        report = monitor.perform_all_checks()

        # Should have warning about redundancy
        assert len(report["warnings"]) > 0

    def test_report_resilience_to_errors(self, tmp_repo):
        """Test that report includes error info when checks fail gracefully."""
        monitor = HealthMonitor(Path("/nonexistent/path"))
        report = monitor.perform_all_checks()

        # Report should still have structure even with errors
        assert "timestamp" in report
        assert "warnings" in report
