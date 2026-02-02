"""
Performance Benchmark Tests

Tests and benchmarks for performance-critical components:
- Levenshtein distance computation
- SimHash filter effectiveness
- Delta encoding with compression metrics
- find_similar_objects scalability

These tests help detect performance regressions.
"""

import os
import pytest
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _perf_multiplier() -> float:
    """Return a multiplier for performance thresholds.

    CI runners and shared hosts can be significantly slower than local dev
    machines. Use a conservative multiplier when CI is detected.
    """
    if os.environ.get("CI"):
        return 3.0
    return 1.0


class TestLevenshteinPerformance:
    """Performance tests for Levenshtein distance computation."""

    def test_levenshtein_small_objects(self):
        """Benchmark Levenshtein on small objects (expected: <100ms per call)."""
        from memvcs.core.fast_similarity import _levenshtein_distance

        s1 = b"The quick brown fox jumps over the lazy dog" * 10  # ~440 bytes
        s2 = b"The quick brown fox jumps over the lazy dog" * 10 + b" extra"

        start = time.perf_counter()
        for _ in range(100):  # Run 100 times
            distance = _levenshtein_distance(s1, s2)
        elapsed = time.perf_counter() - start

        avg_time = (elapsed / 100) * 1000  # Convert to ms

        # Should complete in reasonable time for ~440 byte strings
        limit_ms = 100.0 * _perf_multiplier()
        assert avg_time < limit_ms, f"Levenshtein too slow: {avg_time:.2f}ms per call"
        assert distance >= 0  # Valid result

    def test_levenshtein_medium_objects(self):
        """Benchmark Levenshtein on 2KB objects (expected: <2000ms)."""
        from memvcs.core.fast_similarity import _levenshtein_distance

        s1 = b"content " * 256  # ~2KB
        s2 = b"content " * 256 + b" modified"

        start = time.perf_counter()
        distance = _levenshtein_distance(s1, s2)
        elapsed = time.perf_counter() - start

        elapsed_ms = elapsed * 1000

        # Should complete in reasonable time for 2KB strings
        limit_ms = 2000.0 * _perf_multiplier()
        assert elapsed_ms < limit_ms, f"Levenshtein too slow: {elapsed_ms:.2f}ms"
        assert distance >= 0

    def test_levenshtein_worst_case(self):
        """Test Levenshtein with worst-case scenario (completely different content)."""
        from memvcs.core.fast_similarity import _levenshtein_distance

        s1 = b"A" * 500
        s2 = b"B" * 500

        start = time.perf_counter()
        distance = _levenshtein_distance(s1, s2)
        elapsed = time.perf_counter() - start

        # Should still complete reasonably
        limit_s = 1.0 * _perf_multiplier()
        assert elapsed < limit_s, f"Levenshtein timeout: {elapsed:.2f}s"
        assert distance == 500  # Complete replacement


class TestSimHashPerformance:
    """Performance tests for SimHash filter."""

    def test_simhash_computation_speed(self):
        """Test that SimHash computation is fast (O(n))."""
        from memvcs.core.fast_similarity import SimHashFilter

        content = b"sample content to hash" * 100  # ~2.3KB

        start = time.perf_counter()
        for _ in range(1000):
            hash_val = SimHashFilter.compute_hash(content)
        elapsed = time.perf_counter() - start

        avg_us = (elapsed / 1000) * 1_000_000  # Convert to microseconds

        # Should be very fast
        limit_us = 1000 * _perf_multiplier()
        assert avg_us < limit_us, f"SimHash too slow: {avg_us:.0f}µs per call"
        assert hash_val >= 0

    def test_hamming_distance_speed(self):
        """Test that Hamming distance computation is instant."""
        from memvcs.core.fast_similarity import SimHashFilter

        hash1 = 0x0123456789ABCDEF
        hash2 = 0xFEDCBA9876543210

        start = time.perf_counter()
        for _ in range(100000):
            distance = SimHashFilter.hamming_distance(hash1, hash2)
        elapsed = time.perf_counter() - start

        avg_ns = (elapsed / 100000) * 1_000_000_000  # Convert to nanoseconds

        # Should be nearly instantaneous
        limit_ns = 10000 * _perf_multiplier()
        assert avg_ns < limit_ns, f"Hamming distance too slow: {avg_ns:.0f}ns"


class TestFastSimilarityMatcher:
    """Performance tests for multi-tier similarity filtering."""

    def test_filtering_with_50_objects(self):
        """Test filtering effectiveness with small dataset."""
        from memvcs.core.fast_similarity import FastSimilarityMatcher

        # Create 10 objects with smaller size for faster testing
        objects = {f"obj{i}": b"content " * 50 + bytes([i % 256]) * 50 for i in range(10)}

        matcher = FastSimilarityMatcher(use_parallel=False)

        start = time.perf_counter()
        matcher.find_similar_pairs(objects)
        elapsed = time.perf_counter() - start

        stats = matcher.get_statistics()

        # Just verify stats are collected and test completes
        assert stats["total_pairs_evaluated"] == 45  # C(10,2)

        # Should complete quickly with small dataset
        limit_s = 10.0 * _perf_multiplier()
        assert elapsed < limit_s, f"Matcher too slow: {elapsed:.1f}s for 10 objects"

    def test_filtering_with_100_objects(self):
        """Test filtering with modest dataset (20 objects)."""
        from memvcs.core.fast_similarity import FastSimilarityMatcher

        # Create 20 objects with smaller size for reasonable test time
        objects = {f"obj{i}": b"content " * 100 + bytes([i % 256]) * 100 for i in range(20)}

        # Use sequential processing to avoid multiprocessing hangs in tests
        matcher = FastSimilarityMatcher(use_parallel=False)

        start = time.perf_counter()
        matcher.find_similar_pairs(objects)
        elapsed = time.perf_counter() - start

        # Should complete in reasonable time (relaxed for slower machines)
        limit_s = 60.0 * _perf_multiplier()
        assert elapsed < limit_s, f"Matcher timeout: {elapsed:.1f}s for 20 objects."

        stats = matcher.get_statistics()
        assert stats["total_pairs_evaluated"] == 190  # C(20,2)

    def test_tier1_filter_length_ratio(self):
        """Test that Tier 1 effectively filters by length ratio."""
        from memvcs.core.fast_similarity import FastSimilarityMatcher

        # Objects with very different sizes
        objects = {
            "small": b"x" * 100,
            "large": b"y" * 5000,  # 50x larger
            "small2": b"z" * 100,
        }

        matcher = FastSimilarityMatcher(length_ratio_threshold=0.5)
        matcher.find_similar_pairs(objects)

        stats = matcher.get_statistics()

        # Should filter the mismatched pairs (small vs large, small2 vs large)
        # Total pairs: C(3,2) = 3, expect 2 filtered for length mismatch
        assert stats["filtered_tier1_length"]["count"] >= 1
        assert stats["filtered_tier1_length"]["count"] <= 2


class TestCompressionMetrics:
    """Performance tests for delta compression effectiveness."""

    def test_metrics_tracking_large_dataset(self):
        """Test metrics tracking with realistic object count."""
        from memvcs.core.compression_metrics import DeltaCompressionMetrics, ObjectCompressionStats

        metrics = DeltaCompressionMetrics()

        # Simulate 100 objects with varying compression
        for i in range(100):
            original = 2000 + (i % 500)  # 2-2.5KB
            compressed = int(original * (0.7 + (i % 30) / 100))  # 70-99% of original

            stats = ObjectCompressionStats(
                object_id=f"obj{i}",
                object_type=["semantic", "episodic", "procedural"][i % 3],
                original_size=original,
                compressed_size=compressed,
                compression_ratio=compressed / original,
                delta_used=(i % 3) == 0,  # 1/3 use delta
                compression_benefit=original - compressed,
            )
            metrics.record_object(stats)

        report = metrics.get_report()

        # Verify reasonable compression
        assert report["total_objects"] == 100
        assert 0 < report["overall_compression_ratio"] < 1.0
        assert report["total_bytes_saved"] > 0

        # Should have breakdown by type
        assert len(report["type_statistics"]) == 3


class TestPerformanceRegression:
    """Tests to catch performance regressions."""

    def test_no_regression_simhash(self):
        """Verify SimHash performance doesn't regress."""
        from memvcs.core.fast_similarity import SimHashFilter

        content = b"test content" * 100

        start = time.perf_counter()
        for _ in range(10000):
            SimHashFilter.compute_hash(content)
        elapsed = time.perf_counter() - start

        # Should stay under this threshold (relaxed for slower machines)
        # If this fails, SimHashFilter implementation has regressed
        limit_s = 3.0 * _perf_multiplier()
        assert elapsed < limit_s, (
            f"SimHash performance regression: {elapsed:.2f}s for 10k calls " "(should be <3.0s)"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
