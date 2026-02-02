"""
Delta encoding for pack files.

Compress similar objects using delta encoding. For objects with similar content,
store the first in full and subsequent ones as deltas (differences).

This can achieve 5-10x compression improvement for highly similar content
(common in agent episodic logs, semantic consolidations, etc).
"""

import hashlib
from collections import defaultdict
from typing import List, Tuple, Dict, Optional

from memvcs.core.fast_similarity import FastSimilarityMatcher


def levenshtein_distance(s1: bytes, s2: bytes) -> int:
    """
    Compute Levenshtein distance between two byte sequences.
    Returns edit distance (insertions, deletions, substitutions).
    """
    if len(s1) < len(s2):
        s1, s2 = s2, s1

    if len(s2) == 0:
        return len(s1)

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


def content_similarity(data1: bytes, data2: bytes) -> float:
    """
    Calculate similarity between two byte sequences (0.0 to 1.0).
    Based on Levenshtein distance normalized by max length.
    """
    if not data1 or not data2:
        return 0.0

    distance = levenshtein_distance(data1, data2)
    max_len = max(len(data1), len(data2))

    if max_len == 0:
        return 1.0

    return 1.0 - (distance / max_len)


def find_similar_objects(
    objects: Dict[str, bytes],
    similarity_threshold: float = 0.7,
    min_size: int = 100,
) -> List[List[str]]:
    """
    Group objects by similarity.

    Returns list of groups, where each group is a list of object hashes
    sorted by size (smallest first - best compression base).
    Only includes objects >= min_size.

    Args:
        objects: dict of hash_id -> content
        similarity_threshold: minimum similarity (0.0-1.0) to group
        min_size: minimum object size to consider for delta

    Returns:
        List of similarity groups, each sorted by size ascending
    """
    candidates = {h: content for h, content in objects.items() if len(content) >= min_size}

    if len(candidates) < 2:
        return []

    use_parallel = len(candidates) > 10
    max_len = max(len(content) for content in candidates.values())
    simhash_threshold = 64 if max_len < 256 else 15
    matcher = FastSimilarityMatcher(
        length_ratio_threshold=0.5,
        simhash_threshold=simhash_threshold,
        min_similarity=similarity_threshold,
        use_parallel=use_parallel,
        max_workers=None,
    )

    similar_pairs = matcher.find_similar_pairs(candidates)
    if not similar_pairs:
        return []

    graph: Dict[str, set] = defaultdict(set)
    for id1, id2, _score in similar_pairs:
        graph[id1].add(id2)
        graph[id2].add(id1)

    groups: List[List[str]] = []
    visited = set()

    for node in graph:
        if node in visited:
            continue
        stack = [node]
        component = []
        visited.add(node)

        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in graph[current]:
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                stack.append(neighbor)

        if len(component) > 1:
            component.sort(key=lambda h: len(candidates[h]))
            groups.append(component)

    return groups


def compute_delta(base: bytes, target: bytes) -> bytes:
    """
    Compute delta from base to target using simple run-length + offset encoding.

    Format:
    - 0x00: Copy op   - next 4 bytes = offset in base, next 4 bytes = length
    - 0x01: Insert op - next 4 bytes = length, then <length> bytes of data
    - 0x02: End marker

    This is NOT the most efficient delta algorithm but simple and effective
    for similar objects. Production code could use bsdiff, xdelta3, etc.
    """
    from difflib import SequenceMatcher

    matcher = SequenceMatcher(None, base, target)
    matching_blocks = matcher.get_matching_blocks()

    delta = bytearray()
    target_pos = 0

    for block in matching_blocks:
        base_start, target_start, size = block.a, block.b, block.size

        # Insert any unmapped target bytes before this block
        if target_start > target_pos:
            insert_len = target_start - target_pos
            insert_data = target[target_pos:target_start]
            delta.append(0x01)  # Insert op
            delta.extend(insert_len.to_bytes(4, "big"))
            delta.extend(insert_data)

        # Copy block from base
        if size > 0:
            delta.append(0x00)  # Copy op
            delta.extend(base_start.to_bytes(4, "big"))
            delta.extend(size.to_bytes(4, "big"))

        target_pos = target_start + size

    # Insert any remaining target bytes
    if target_pos < len(target):
        insert_len = len(target) - target_pos
        insert_data = target[target_pos:]
        delta.append(0x01)  # Insert op
        delta.extend(insert_len.to_bytes(4, "big"))
        delta.extend(insert_data)

    delta.append(0x02)  # End marker

    return bytes(delta)


def apply_delta(base: bytes, delta: bytes) -> bytes:
    """Apply delta to base to reconstruct target."""
    result = bytearray()
    pos = 0

    while pos < len(delta):
        op = delta[pos]
        pos += 1

        if op == 0x00:  # Copy op
            if pos + 8 > len(delta):
                break
            offset = int.from_bytes(delta[pos : pos + 4], "big")
            length = int.from_bytes(delta[pos + 4 : pos + 8], "big")
            pos += 8
            result.extend(base[offset : offset + length])

        elif op == 0x01:  # Insert op
            if pos + 4 > len(delta):
                break
            length = int.from_bytes(delta[pos : pos + 4], "big")
            pos += 4
            if pos + length > len(delta):
                break
            result.extend(delta[pos : pos + length])
            pos += length

        elif op == 0x02:  # End marker
            break

    return bytes(result)


def estimate_delta_compression(base: bytes, target: bytes, delta: bytes) -> Tuple[int, float]:
    """
    Estimate compression achieved by delta.

    Returns (original_size, ratio) where ratio = 1.0 is no compression,
    ratio = 0.5 means delta is 50% of original target size.
    """
    original_size = len(target)
    delta_size = len(delta)

    if original_size == 0:
        return (0, 0.0)

    ratio = delta_size / original_size
    return (original_size, ratio)


class DeltaCache:
    """
    Cache deltas between similar objects.

    Tracks base->target relationships and stores pre-computed deltas
    to avoid recomputation.
    """

    def __init__(self):
        self.deltas: Dict[Tuple[str, str], bytes] = {}  # (base_hash, target_hash) -> delta
        self.bases: Dict[str, bytes] = {}  # target_hash -> base_hash (reconstruction path)

    def add_delta(self, base_hash: str, target_hash: str, delta: bytes):
        """Register a delta relationship."""
        self.deltas[(base_hash, target_hash)] = delta
        self.bases[target_hash] = base_hash

    def get_delta(self, base_hash: str, target_hash: str) -> Optional[bytes]:
        """Retrieve cached delta."""
        return self.deltas.get((base_hash, target_hash))

    def get_base(self, target_hash: str) -> Optional[str]:
        """Get the base hash for a target."""
        return self.bases.get(target_hash)

    def estimate_total_savings(self, objects: Dict[str, int]) -> Tuple[int, int]:
        """
        Estimate total size savings from all deltas.

        Returns (original_total, compressed_total).

        Args:
            objects: dict of hash_id -> original_size
        """
        original_total = sum(objects.values())
        compressed_total = 0

        for (base_hash, target_hash), delta in self.deltas.items():
            # Target stored as delta instead of full copy
            compressed_total += len(delta)

        # Add all non-delta objects
        all_objects = set(objects.keys())
        delta_targets = set(self.bases.keys())
        non_delta = all_objects - delta_targets
        for obj_hash in non_delta:
            compressed_total += objects.get(obj_hash, 0)

        return (original_total, compressed_total)
