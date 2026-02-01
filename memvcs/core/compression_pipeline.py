"""
Enhanced semantic compression pipeline for agmem (#11).

Multi-stage: chunk -> fact extraction -> dedup -> embed -> tiered storage.
Hybrid retrieval (keyword + vector) is in memvcs.retrieval.strategies.HybridStrategy.
"""

import hashlib
import re
from pathlib import Path
from typing import List, Optional, Tuple, Any

from .constants import MEMORY_TYPES

CHUNK_SIZE_DEFAULT = 512
CHUNK_OVERLAP = 64
DEDUP_HASH_ALGO = "sha256"
TIER_HOT_DAYS = 7


def chunk_by_size(text: str, size: int = CHUNK_SIZE_DEFAULT, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Split text into chunks by character size with optional overlap."""
    if not text or size <= 0:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap if end < len(text) else len(text)
    return chunks


def chunk_by_sentences(text: str, max_chunk_chars: int = 512) -> List[str]:
    """Split text into chunks by sentence boundaries, up to max_chunk_chars per chunk."""
    if not text:
        return []
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current = []
    current_len = 0
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if current_len + len(s) + 1 <= max_chunk_chars:
            current.append(s)
            current_len += len(s) + 1
        else:
            if current:
                chunks.append(" ".join(current))
            current = [s]
            current_len = len(s) + 1
    if current:
        chunks.append(" ".join(current))
    return chunks


def extract_facts_from_chunk(chunk: str) -> List[str]:
    """Extract fact-like lines (bullets or short statements). Reuse distiller logic in callers if needed."""
    facts = []
    for line in chunk.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- ") and len(line) > 10:
            facts.append(line)
        elif len(line) > 20 and len(line) < 300 and not line.startswith("```"):
            facts.append(line)
    return facts[:15]


def dedup_by_hash(items: List[str]) -> List[Tuple[str, str]]:
    """Return (item, hash_hex) for unique items by content hash. Order preserved, first occurrence kept."""
    seen_hashes = set()
    result = []
    for item in items:
        h = hashlib.new(DEDUP_HASH_ALGO, item.encode()).hexdigest()
        if h not in seen_hashes:
            seen_hashes.add(h)
            result.append((item, h))
    return result


def dedup_by_similarity_threshold(
    items: List[str], vector_store: Any, threshold: float = 0.95
) -> List[str]:
    """Filter items by embedding similarity; keep first of clusters above threshold. Requires vector_store."""
    if not items or vector_store is None:
        return items
    try:
        embeddings = vector_store.embed(items)
        kept = [items[0]]
        for i in range(1, len(items)):
            sims = [vector_store.similarity(embeddings[i], vector_store.embed([kept[j]])[0]) for j in range(len(kept))]
            if not any(s >= threshold for s in sims):
                kept.append(items[i])
        return kept
    except Exception:
        return items


class CompressionPipeline:
    """
    Multi-stage compression: chunk -> optional fact extraction -> dedup -> optional embed -> tiered storage.
    Wire to vector_store and retrieval for hybrid recall.
    """

    def __init__(
        self,
        chunk_size: int = CHUNK_SIZE_DEFAULT,
        use_sentences: bool = True,
        extract_facts: bool = False,
        dedup_hash: bool = True,
        vector_store: Optional[Any] = None,
        tier_by_recency: bool = True,
    ):
        self.chunk_size = chunk_size
        self.use_sentences = use_sentences
        self.extract_facts = extract_facts
        self.dedup_hash = dedup_hash
        self.vector_store = vector_store
        self.tier_by_recency = tier_by_recency

    def chunk(self, text: str) -> List[str]:
        """Chunk text by size or sentences."""
        if self.use_sentences:
            return chunk_by_sentences(text, max_chunk_chars=self.chunk_size)
        return chunk_by_size(text, size=self.chunk_size)

    def run(self, text: str, path: Optional[Path] = None) -> List[Tuple[str, str, Optional[str]]]:
        """
        Run pipeline: chunk -> optional fact extraction -> dedup.
        Returns list of (content, content_hash, tier) where tier is "hot" or "cold" or None.
        """
        chunks = self.chunk(text)
        if self.extract_facts:
            facts = []
            for c in chunks:
                facts.extend(extract_facts_from_chunk(c))
            chunks = facts if facts else chunks
        if self.dedup_hash:
            chunk_tuples = dedup_by_hash(chunks)
        else:
            chunk_tuples = [(c, hashlib.new(DEDUP_HASH_ALGO, c.encode()).hexdigest()) for c in chunks]
        tier = None
        if self.tier_by_recency and path and path.exists():
            try:
                mtime = path.stat().st_mtime
                from datetime import datetime, timezone
                age_days = (datetime.now(timezone.utc).timestamp() - mtime) / 86400
                tier = "hot" if age_days <= TIER_HOT_DAYS else "cold"
            except Exception:
                pass
        return [(c, h, tier) for c, h in chunk_tuples]
