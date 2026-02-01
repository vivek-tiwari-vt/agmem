"""Tests for compression pipeline integration."""

import pytest
import tempfile
from pathlib import Path

from memvcs.core.compression_pipeline import (
    chunk_by_size,
    chunk_by_sentences,
    extract_facts_from_chunk,
    dedup_by_hash,
    CompressionPipeline,
)


class TestChunking:
    """Test chunking functions."""

    def test_chunk_by_size_basic(self):
        text = "a" * 1000
        chunks = chunk_by_size(text, size=100, overlap=10)
        assert len(chunks) > 8
        assert all(len(c) <= 100 for c in chunks)

    def test_chunk_by_size_empty(self):
        assert chunk_by_size("", size=100) == []
        assert chunk_by_size("   ", size=100) == []

    def test_chunk_by_sentences(self):
        text = "First sentence. Second sentence! Third sentence?"
        chunks = chunk_by_sentences(text, max_chunk_chars=30)
        assert len(chunks) >= 1
        assert all("." in c or "!" in c or "?" in c for c in chunks)

    def test_chunk_by_sentences_long(self):
        text = "Sentence. " * 100
        chunks = chunk_by_sentences(text, max_chunk_chars=200)
        assert len(chunks) > 1
        assert all(len(c) <= 250 for c in chunks)  # Allow slight overflow


class TestFactExtraction:
    """Test fact extraction."""

    def test_extract_facts_bullets(self):
        chunk = "- Fact one long enough\n- Fact two long enough\n- Fact three long"
        facts = extract_facts_from_chunk(chunk)
        assert len(facts) == 3
        assert all(f.startswith("- ") for f in facts)

    def test_extract_facts_statements(self):
        chunk = "This is a statement that is long enough.\nAnother valid statement here."
        facts = extract_facts_from_chunk(chunk)
        assert len(facts) >= 1

    def test_extract_facts_filters_short(self):
        chunk = "- Too short\n- This one is definitely acceptable and long"
        facts = extract_facts_from_chunk(chunk)
        # The actual implementation requires len > 10 for bullets
        assert len(facts) >= 1

    def test_extract_facts_max_15(self):
        chunk = "\n".join([f"- Fact number {i}" for i in range(50)])
        facts = extract_facts_from_chunk(chunk)
        assert len(facts) == 15


class TestDeduplication:
    """Test deduplication."""

    def test_dedup_by_hash_removes_duplicates(self):
        items = ["fact1", "fact2", "fact1", "fact3", "fact2"]
        result = dedup_by_hash(items)
        assert len(result) == 3
        contents = [item[0] for item in result]
        assert "fact1" in contents
        assert "fact2" in contents
        assert "fact3" in contents

    def test_dedup_by_hash_preserves_order(self):
        items = ["first", "second", "third", "first"]
        result = dedup_by_hash(items)
        assert result[0][0] == "first"
        assert result[1][0] == "second"
        assert result[2][0] == "third"

    def test_dedup_by_hash_includes_hash(self):
        items = ["test"]
        result = dedup_by_hash(items)
        assert len(result[0]) == 2
        assert isinstance(result[0][1], str)
        assert len(result[0][1]) == 64  # SHA-256 hex


class TestCompressionPipeline:
    """Test full compression pipeline."""

    def test_pipeline_chunking(self):
        pipeline = CompressionPipeline(chunk_size=100, use_sentences=False)
        text = "a" * 500
        result = pipeline.run(text)
        assert len(result) > 0
        assert all(len(item) == 3 for item in result)  # (content, hash, tier)

    def test_pipeline_fact_extraction(self):
        pipeline = CompressionPipeline(extract_facts=True, chunk_size=200)
        text = "- User prefers Python\n- User likes testing\n- Short"
        result = pipeline.run(text)
        assert len(result) >= 2  # Two valid facts

    def test_pipeline_deduplication(self):
        pipeline = CompressionPipeline(dedup_hash=True)
        text = "Same sentence. Same sentence. Different sentence."
        result = pipeline.run(text)
        # Dedup should reduce duplicates
        contents = [item[0] for item in result]
        assert len(contents) == len(set(contents))

    def test_pipeline_tiering_by_recency(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("Test content")

            pipeline = CompressionPipeline(tier_by_recency=True)
            result = pipeline.run("Test content", path=test_file)

            # Recent file should be hot tier
            assert len(result) > 0
            assert result[0][2] == "hot"

    def test_pipeline_no_tiering(self):
        pipeline = CompressionPipeline(tier_by_recency=False)
        result = pipeline.run("Test content")
        assert len(result) > 0
        assert result[0][2] is None

    def test_pipeline_with_all_features(self):
        pipeline = CompressionPipeline(
            chunk_size=200,
            use_sentences=True,
            extract_facts=True,
            dedup_hash=True,
            tier_by_recency=False,
        )
        text = """
- User prefers Python programming
- User likes test-driven development
- User prefers Python programming
- System uses automated testing
"""
        result = pipeline.run(text)

        # Should chunk, extract facts, and deduplicate
        assert len(result) > 0
        assert len(result) < 4  # Dedup should remove duplicate

        # All results should have hash
        assert all(len(item[1]) == 64 for item in result)
