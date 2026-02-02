"""
Fast similarity matching with tiered filtering.

Solves O(n²×m²) performance bottleneck in delta encoding by filtering
candidates before expensive Levenshtein distance computation.

Three-tier approach:
1. Length-ratio filter: O(1) - skip if sizes differ >50%
2. SimHash filter: O(n) - skip if approximate similarity below threshold
3. Levenshtein distance: O(n×m) - only for candidates passing tiers 1-2
4. Parallel processing: Multiprocessing for tier 3 across multiple cores

With 100 objects × 2KB each, filters typically eliminate 90%+ of pairs
before expensive distance computation, reducing 40B operations to <100M.
"""

import hashlib
from typing import Dict, List, Tuple, Optional, Set, Any
from multiprocessing import Pool, cpu_count
from functools import partial
import math


class SimHashFilter:
    """Fast approximate similarity using SimHash.

    SimHash creates a 64-bit fingerprint of content that:
    - Changes minimally for similar content
    - Computes in O(n) time
    - Allows Hamming distance for approximate matching

    Papers: "Detecting Near-Duplicates for Web Crawling" (Charikar, 2002)
    """

    @staticmethod
    def compute_hash(content: bytes, hash_bits: int = 64) -> int:
        """Compute SimHash fingerprint for content.

        Args:
            content: Bytes to hash
            hash_bits: Number of bits in fingerprint (default 64)

        Returns:
            SimHash fingerprint as integer
        """
        if not content:
            return 0

        # Initialize fingerprint vector
        fingerprint = [0] * hash_bits

        # Process content in 64-byte chunks
        chunk_size = 64
        for i in range(0, len(content), chunk_size):
            chunk = content[i : i + chunk_size]
            # Hash each chunk
            h = hashlib.sha256(chunk).digest()
            # Map hash bits to fingerprint
            for bit_idx in range(hash_bits):
                byte_idx = bit_idx // 8
                bit_pos = bit_idx % 8
                if byte_idx < len(h):
                    if (h[byte_idx] >> bit_pos) & 1:
                        fingerprint[bit_idx] += 1
                    else:
                        fingerprint[bit_idx] -= 1

        # Convert fingerprint to integer
        result = 0
        for i, v in enumerate(fingerprint):
            if v > 0:
                result |= 1 << i

        return result

    @staticmethod
    def hamming_distance(hash1: int, hash2: int) -> int:
        """Compute Hamming distance between two SimHash fingerprints.

        Args:
            hash1: First SimHash fingerprint
            hash2: Second SimHash fingerprint

        Returns:
            Hamming distance (0-64)
        """
        xor = hash1 ^ hash2
        distance = 0
        while xor:
            distance += xor & 1
            xor >>= 1
        return distance


class FastSimilarityMatcher:
    """Multi-tier similarity matching with progressive filtering.

    Tiers:
    1. Length-ratio filter (O(1)): Skip if object sizes differ >50%
    2. SimHash filter (O(n)): Skip if Hamming distance indicates dissimilarity
    3. Levenshtein distance (O(n×m)): Only for candidates passing tiers 1-2
    4. Parallel processing: Use multiprocessing for tier 3 across CPU cores

    Usage:
        matcher = FastSimilarityMatcher(
            length_ratio_threshold=0.5,
            simhash_threshold=15,  # Hamming distance
            min_similarity=0.8
        )
        similar_pairs = matcher.find_similar_pairs(objects_dict)
    """

    def __init__(
        self,
        length_ratio_threshold: float = 0.5,
        simhash_threshold: int = 15,
        min_similarity: float = 0.8,
        use_parallel: bool = True,
        max_workers: Optional[int] = None,
    ):
        """Initialize the similarity matcher.

        Args:
            length_ratio_threshold: Skip if |len(a) - len(b)| / max(len(a), len(b)) > threshold
            simhash_threshold: Skip if SimHash Hamming distance > threshold
            min_similarity: Minimum Levenshtein similarity required (0.0-1.0)
            use_parallel: Whether to use multiprocessing for tier 3
            max_workers: Max worker processes (defaults to CPU count)
        """
        self.length_ratio_threshold = length_ratio_threshold
        self.simhash_threshold = simhash_threshold
        self.min_similarity = min_similarity
        self.use_parallel = use_parallel
        self.max_workers = max_workers or cpu_count()

        # Statistics for debugging/reporting
        self.stats = {
            "total_pairs": 0,
            "filtered_tier1": 0,  # Length ratio
            "filtered_tier2": 0,  # SimHash
            "evaluated_tier3": 0,  # Levenshtein
            "matches_found": 0,
        }

    def find_similar_pairs(self, objects: Dict[str, bytes]) -> List[Tuple[str, str, float]]:
        """Find similar object pairs using tiered filtering.

        Args:
            objects: Dict mapping object_id -> content (bytes)

        Returns:
            List of (id1, id2, similarity_score) tuples, sorted by similarity (descending)
        """
        self.stats = {
            "total_pairs": 0,
            "filtered_tier1": 0,
            "filtered_tier2": 0,
            "evaluated_tier3": 0,
            "matches_found": 0,
        }

        if len(objects) < 2:
            return []

        object_ids = list(objects.keys())
        similar_pairs: List[Tuple[str, str, float]] = []

        # Pre-compute SimHash for all objects (tier 2 pre-computation)
        simhash_cache = {oid: SimHashFilter.compute_hash(objects[oid]) for oid in object_ids}

        # Generate candidate pairs
        candidates_for_tier3 = []

        for i in range(len(object_ids)):
            for j in range(i + 1, len(object_ids)):
                id1, id2 = object_ids[i], object_ids[j]
                content1, content2 = objects[id1], objects[id2]

                self.stats["total_pairs"] += 1

                # Tier 1: Length-ratio filter
                if not self._pass_length_filter(len(content1), len(content2)):
                    self.stats["filtered_tier1"] += 1
                    continue

                # Tier 2: SimHash filter
                hash1 = simhash_cache[id1]
                hash2 = simhash_cache[id2]
                if not self._pass_simhash_filter(hash1, hash2):
                    self.stats["filtered_tier2"] += 1
                    continue

                # Tier 3: These candidates need Levenshtein distance
                candidates_for_tier3.append((id1, id2, content1, content2))

        # Tier 3: Levenshtein distance (parallel if enabled)
        self.stats["evaluated_tier3"] = len(candidates_for_tier3)

        if not candidates_for_tier3:
            return []

        if self.use_parallel and len(candidates_for_tier3) > 1:
            similar_pairs = self._evaluate_tier3_parallel(candidates_for_tier3)
        else:
            similar_pairs = self._evaluate_tier3_serial(candidates_for_tier3)

        # Sort by similarity (highest first)
        similar_pairs.sort(key=lambda x: x[2], reverse=True)
        self.stats["matches_found"] = len(similar_pairs)

        return similar_pairs

    def _pass_length_filter(self, len1: int, len2: int) -> bool:
        """Check if two objects pass the length-ratio filter (tier 1).

        Args:
            len1: Length of first object
            len2: Length of second object

        Returns:
            True if objects should be compared further, False if filtered out
        """
        if len1 == 0 or len2 == 0:
            return len1 == len2

        max_len = max(len1, len2)
        min_len = min(len1, len2)
        ratio = 1.0 - (min_len / max_len)

        return ratio <= self.length_ratio_threshold

    def _pass_simhash_filter(self, hash1: int, hash2: int) -> bool:
        """Check if two objects pass the SimHash filter (tier 2).

        Args:
            hash1: SimHash fingerprint of first object
            hash2: SimHash fingerprint of second object

        Returns:
            True if objects should be compared further, False if filtered out
        """
        distance = SimHashFilter.hamming_distance(hash1, hash2)
        # Lower Hamming distance = more similar
        return distance <= self.simhash_threshold

    def _evaluate_tier3_serial(
        self, candidates: List[Tuple[str, str, bytes, bytes]]
    ) -> List[Tuple[str, str, float]]:
        """Evaluate candidates using Levenshtein distance (serial).

        Args:
            candidates: List of (id1, id2, content1, content2) tuples

        Returns:
            List of (id1, id2, similarity_score) tuples where similarity >= min_similarity
        """
        results = []
        for id1, id2, content1, content2 in candidates:
            similarity = self._levenshtein_similarity(content1, content2)
            if similarity >= self.min_similarity:
                results.append((id1, id2, similarity))
        return results

    def _evaluate_tier3_parallel(
        self, candidates: List[Tuple[str, str, bytes, bytes]]
    ) -> List[Tuple[str, str, float]]:
        """Evaluate candidates using Levenshtein distance (parallel).

        Args:
            candidates: List of (id1, id2, content1, content2) tuples

        Returns:
            List of (id1, id2, similarity_score) tuples where similarity >= min_similarity
        """
        # Process pairs in parallel
        with Pool(processes=self.max_workers) as pool:
            results = pool.map(
                partial(
                    _compute_similarity_worker,
                    min_similarity=self.min_similarity,
                ),
                candidates,
            )

        # Filter out None results (pairs that didn't meet minimum similarity)
        return [r for r in results if r is not None]

    @staticmethod
    def _levenshtein_similarity(s1: bytes, s2: bytes) -> float:
        """Compute Levenshtein similarity (0.0-1.0).

        Similarity = 1.0 - (distance / max_length)

        Args:
            s1: First byte sequence
            s2: Second byte sequence

        Returns:
            Similarity score (0.0 = completely different, 1.0 = identical)
        """
        distance = _levenshtein_distance(s1, s2)
        max_len = max(len(s1), len(s2))
        if max_len == 0:
            return 1.0
        return 1.0 - (distance / max_len)

    def get_statistics(self) -> Dict[str, Any]:
        """Get filtering statistics.

        Returns:
            Dict with tier-by-tier breakdown of filtering effectiveness
        """
        total = self.stats["total_pairs"]
        tier1_pct = (self.stats["filtered_tier1"] / total * 100) if total > 0 else 0
        tier2_pct = (self.stats["filtered_tier2"] / total * 100) if total > 0 else 0

        return {
            "total_pairs_evaluated": total,
            "filtered_tier1_length": {
                "count": self.stats["filtered_tier1"],
                "percentage": tier1_pct,
            },
            "filtered_tier2_simhash": {
                "count": self.stats["filtered_tier2"],
                "percentage": tier2_pct,
            },
            "evaluated_tier3_levenshtein": {
                "count": self.stats["evaluated_tier3"],
                "percentage": ((self.stats["evaluated_tier3"] / total * 100) if total > 0 else 0),
            },
            "matches_found": self.stats["matches_found"],
        }

    def log_statistics(self, logger=None) -> None:
        """Log filtering statistics for debugging."""
        stats = self.get_statistics()
        output = [
            "Similarity Matching Statistics",
            "=" * 50,
            f"Total pairs evaluated: {stats['total_pairs_evaluated']}",
            f"Filtered (Tier 1 - Length): {stats['filtered_tier1_length']['count']} ({stats['filtered_tier1_length']['percentage']:.1f}%)",
            f"Filtered (Tier 2 - SimHash): {stats['filtered_tier2_simhash']['count']} ({stats['filtered_tier2_simhash']['percentage']:.1f}%)",
            f"Evaluated (Tier 3 - Levenshtein): {stats['evaluated_tier3_levenshtein']['count']} ({stats['evaluated_tier3_levenshtein']['percentage']:.1f}%)",
            f"Similar pairs found: {stats['matches_found']}",
            "=" * 50,
        ]
        full_output = "\n".join(output)
        if logger:
            logger.info(full_output)
        else:
            print(full_output)


def _levenshtein_distance(s1: bytes, s2: bytes) -> int:
    """Compute Levenshtein distance between two byte sequences.

    O(n×m) time complexity. Optimized for common cases.

    Args:
        s1: First byte sequence
        s2: Second byte sequence

    Returns:
        Edit distance (minimum edits to transform s1 to s2)
    """
    if len(s1) < len(s2):
        s1, s2 = s2, s1

    if len(s2) == 0:
        return len(s1)

    # Use only two rows for space optimization
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev[j + 1] + 1
            deletions = curr[j] + 1
            substitutions = prev[j] + (c1 != c2)
            curr.append(min(insertions, deletions, substitutions))
        prev = curr

    return prev[-1]


def _compute_similarity_worker(
    candidate: Tuple[str, str, bytes, bytes],
    min_similarity: float,
) -> Optional[Tuple[str, str, float]]:
    """Worker function for parallel Levenshtein computation.

    Args:
        candidate: (id1, id2, content1, content2) tuple
        min_similarity: Minimum similarity threshold

    Returns:
        (id1, id2, similarity) if similarity >= min_similarity, else None
    """
    id1, id2, content1, content2 = candidate
    similarity = FastSimilarityMatcher._levenshtein_similarity(content1, content2)

    if similarity >= min_similarity:
        return (id1, id2, similarity)
    return None
