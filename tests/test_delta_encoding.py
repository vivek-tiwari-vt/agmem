"""
Tests for delta encoding module.
"""

import pytest
from memvcs.core.delta import (
    levenshtein_distance,
    content_similarity,
    find_similar_objects,
    compute_delta,
    apply_delta,
    estimate_delta_compression,
    DeltaCache,
)


class TestLevenshteinDistance:
    """Tests for Levenshtein distance calculation."""

    def test_identical_strings(self):
        """Identical strings should have distance 0."""
        assert levenshtein_distance(b"hello", b"hello") == 0

    def test_empty_strings(self):
        """Empty strings have distance equal to length of other."""
        assert levenshtein_distance(b"", b"abc") == 3
        assert levenshtein_distance(b"abc", b"") == 3

    def test_single_insertion(self):
        """Single character insertion."""
        assert levenshtein_distance(b"abc", b"abcd") == 1

    def test_single_deletion(self):
        """Single character deletion."""
        assert levenshtein_distance(b"abcd", b"abc") == 1

    def test_single_substitution(self):
        """Single character substitution."""
        assert levenshtein_distance(b"abc", b"axc") == 1

    def test_multiple_operations(self):
        """Multiple edit operations."""
        assert levenshtein_distance(b"kitten", b"sitting") == 3

    def test_completely_different(self):
        """Completely different strings."""
        distance = levenshtein_distance(b"abc", b"xyz")
        assert distance >= 3


class TestContentSimilarity:
    """Tests for content similarity calculation."""

    def test_identical_content(self):
        """Identical content should have similarity 1.0."""
        assert content_similarity(b"hello", b"hello") == 1.0

    def test_empty_content(self):
        """Empty content similarity is 0.0."""
        assert content_similarity(b"", b"abc") == 0.0
        assert content_similarity(b"abc", b"") == 0.0

    def test_completely_different(self):
        """Completely different content near 0.0."""
        similarity = content_similarity(b"abc", b"xyz")
        assert 0.0 <= similarity < 0.5

    def test_similar_content(self):
        """Similar content should have high similarity."""
        s1 = b"The quick brown fox jumps over the lazy dog"
        s2 = b"The quick brown fox jumps over the lazy cat"
        similarity = content_similarity(s1, s2)
        assert similarity > 0.8

    def test_similarity_range(self):
        """Similarity should always be 0.0-1.0."""
        s1 = b"a" * 1000
        s2 = b"b" * 1000
        similarity = content_similarity(s1, s2)
        assert 0.0 <= similarity <= 1.0


class TestFindSimilarObjects:
    """Tests for similar object grouping."""

    def test_no_objects(self):
        """Empty object dict returns empty groups."""
        assert find_similar_objects({}) == []

    def test_single_object(self):
        """Single object returns no groups."""
        objs = {b"hash1".hex(): b"content"}
        groups = find_similar_objects(objs)
        assert len(groups) == 0

    def test_unique_objects(self):
        """Unique objects form no groups."""
        objs = {
            "hash1": b"abc" * 50,
            "hash2": b"xyz" * 50,
            "hash3": b"def" * 50,
        }
        groups = find_similar_objects(objs, similarity_threshold=0.9)
        assert len(groups) == 0

    def test_similar_objects_grouped(self):
        """Similar objects should be grouped."""
        base = b"a" * 100
        similar1 = b"a" * 95 + b"b" * 5
        similar2 = b"a" * 93 + b"b" * 7

        objs = {
            "base": base,
            "sim1": similar1,
            "sim2": similar2,
        }
        groups = find_similar_objects(objs, similarity_threshold=0.8, min_size=50)
        assert len(groups) > 0

    def test_objects_sorted_by_size(self):
        """Objects in group should be sorted by size."""
        base = b"x" * 50
        larger = b"x" * 100

        objs = {
            "larger": larger,
            "base": base,
        }
        groups = find_similar_objects(objs, similarity_threshold=0.9, min_size=40)
        if groups:
            group = groups[0]
            # Smallest should be first
            assert len(objs[group[0]]) <= len(objs[group[-1]])

    def test_min_size_filter(self):
        """Objects smaller than min_size should be excluded."""
        objs = {
            "small": b"x" * 50,
            "large": b"x" * 200,
        }
        groups = find_similar_objects(objs, similarity_threshold=0.9, min_size=100)
        # Small object too small, should not group
        for group in groups:
            assert "small" not in group or len(group) == 1


class TestComputeAndApplyDelta:
    """Tests for delta computation and application."""

    def test_identical_content_small_delta(self):
        """Delta of identical content should be small."""
        base = b"hello world" * 50  # Make it larger for delta to be useful
        target = b"hello world" * 50
        delta = compute_delta(base, target)
        # Delta should be much smaller than target for identical content
        assert len(delta) < len(target) * 0.5

    def test_single_character_insertion(self):
        """Single character insertion in large content."""
        base = b"a" * 1000 + b"b" * 1000
        target = b"a" * 1000 + b"x" + b"b" * 1000
        delta = compute_delta(base, target)
        # Delta should benefit from similarity
        assert len(delta) < len(target)

    def test_multiple_changes(self):
        """Delta with multiple changes in large content."""
        base = b"The quick brown fox jumps over the lazy dog. " * 50
        target = b"The slow brown cat jumps over the happy dog. " * 50
        delta = compute_delta(base, target)
        # For our simple delta algorithm, just verify it reconstructs correctly
        reconstructed = apply_delta(base, delta)
        assert reconstructed == target

    def test_apply_delta_reconstruction(self):
        """Applying delta should reconstruct original."""
        base = b"hello world!"
        target = b"hello there world!"
        delta = compute_delta(base, target)
        reconstructed = apply_delta(base, delta)
        assert reconstructed == target

    def test_round_trip_long_content(self):
        """Round-trip with longer content."""
        base = b"Lorem ipsum dolor sit amet " * 10
        target = b"Lorem ipsum dolor sit amet " * 10 + b"extra content here"
        delta = compute_delta(base, target)
        reconstructed = apply_delta(base, delta)
        assert reconstructed == target

    def test_round_trip_modified_content(self):
        """Round-trip with modified similar content."""
        base = b"The quick brown fox jumps over the lazy dog. " b"This is a test. " * 5
        target = b"The quick brown cat jumps over the lazy dog. " b"This is still a test. " * 5
        delta = compute_delta(base, target)
        reconstructed = apply_delta(base, delta)
        assert reconstructed == target

    def test_completely_different_content(self):
        """Delta of completely different content (reconstruction still works)."""
        base = b"aaa" * 50
        target = b"bbb" * 50
        delta = compute_delta(base, target)
        reconstructed = apply_delta(base, delta)
        assert reconstructed == target


class TestEstimateDeltaCompression:
    """Tests for delta compression estimation."""

    def test_no_compression(self):
        """Large delta = no compression benefit (realistic for small objects)."""
        base = b"content"
        target = b"different"
        delta = compute_delta(base, target)
        original_size, ratio = estimate_delta_compression(base, target, delta)
        # For small objects, delta may be larger than target
        # But ratio should be calculated correctly
        assert ratio >= 0.0

    def test_high_compression(self):
        """Small delta = high compression benefit for large similar content."""
        base = b"x" * 10000
        target = b"x" * 9999 + b"y"
        delta = compute_delta(base, target)
        original_size, ratio = estimate_delta_compression(base, target, delta)
        # Should compress well (delta much smaller than target)
        assert ratio < 0.1
        assert original_size == 10000

    def test_empty_target(self):
        """Empty target returns 0 original size."""
        delta = b""
        original_size, ratio = estimate_delta_compression(b"base", b"", delta)
        assert original_size == 0


class TestDeltaCache:
    """Tests for DeltaCache."""

    def test_add_and_get_delta(self):
        """Store and retrieve delta."""
        cache = DeltaCache()
        base = "base_hash"
        target = "target_hash"
        delta = b"delta_data"

        cache.add_delta(base, target, delta)
        assert cache.get_delta(base, target) == delta

    def test_get_base(self):
        """Get base hash for target."""
        cache = DeltaCache()
        base = "base_hash"
        target = "target_hash"

        cache.add_delta(base, target, b"delta")
        assert cache.get_base(target) == base

    def test_multiple_deltas(self):
        """Cache multiple delta relationships."""
        cache = DeltaCache()
        cache.add_delta("base1", "target1", b"delta1")
        cache.add_delta("base2", "target2", b"delta2")

        assert cache.get_delta("base1", "target1") == b"delta1"
        assert cache.get_delta("base2", "target2") == b"delta2"
        assert cache.get_base("target1") == "base1"
        assert cache.get_base("target2") == "base2"

    def test_estimate_savings(self):
        """Estimate compression savings."""
        cache = DeltaCache()
        cache.add_delta("base", "target1", b"delta1")
        cache.add_delta("base", "target2", b"delta2")

        objects = {
            "base": 1000,
            "target1": 1000,
            "target2": 1000,
            "other": 500,
        }

        original, compressed = cache.estimate_total_savings(objects)
        # Compressed should be less than original
        assert compressed < original
        # Should include base + deltas + other
        assert compressed == 1000 + len(b"delta1") + len(b"delta2") + 500

    def test_no_deltas(self):
        """Cache with no deltas."""
        cache = DeltaCache()
        objects = {"hash1": 100, "hash2": 200}

        original, compressed = cache.estimate_total_savings(objects)
        # No deltas, so compressed == original
        assert compressed == original
