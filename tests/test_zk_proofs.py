"""Tests for zero-knowledge proofs (hash/signature-based)."""

import pytest
import tempfile
from pathlib import Path

from memvcs.core.zk_proofs import (
    prove_keyword_containment,
    prove_memory_freshness,
    verify_proof,
)


class TestKeywordContainment:
    """Test keyword containment prove/verify round-trip."""

    def test_prove_and_verify_keyword(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mem_file = Path(tmpdir) / "test.md"
            mem_file.write_text("Hello world and python programming")
            out_proof = Path(tmpdir) / "proof.json"
            ok = prove_keyword_containment(mem_file, "python", out_proof)
            assert ok is True
            assert out_proof.exists()
            verified = verify_proof(out_proof, "keyword", keyword="python")
            assert verified is True

    def test_verify_keyword_wrong_keyword_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mem_file = Path(tmpdir) / "test.md"
            mem_file.write_text("Hello world and python")
            out_proof = Path(tmpdir) / "proof.json"
            prove_keyword_containment(mem_file, "python", out_proof)
            verified = verify_proof(out_proof, "keyword", keyword="rust")
            assert verified is False

    def test_prove_keyword_not_in_file_returns_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mem_file = Path(tmpdir) / "test.md"
            mem_file.write_text("Hello world")
            out_proof = Path(tmpdir) / "proof.json"
            ok = prove_keyword_containment(mem_file, "python", out_proof)
            assert ok is False


class TestMemoryFreshness:
    """Test memory freshness prove/verify (requires signing key from env)."""

    def test_verify_freshness_with_embedded_public_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mem_file = Path(tmpdir) / "test.md"
            mem_file.write_text("content")
            out_proof = Path(tmpdir) / "proof_fresh.json"
            mem_dir = Path(tmpdir) / ".mem"
            mem_dir.mkdir()
            ok = prove_memory_freshness(mem_file, "2020-01-01T00:00:00Z", out_proof, mem_dir=None)
            if not ok:
                pytest.skip("prove_memory_freshness requires AGMEM_SIGNING_PRIVATE_KEY in env")
            verified = verify_proof(out_proof, "freshness", after_timestamp="2020-01-01T00:00:00Z")
            assert verified is True
