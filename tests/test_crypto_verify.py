"""Tests for cryptographic commit verification (Merkle, signing)."""

import pytest
import tempfile
from pathlib import Path

from memvcs.core.objects import ObjectStore, Tree, TreeEntry, Commit, Blob
from memvcs.core.crypto_verify import (
    _collect_blob_hashes_from_tree,
    build_merkle_tree,
    build_merkle_root_for_commit,
    verify_commit,
    verify_merkle_proof,
    merkle_proof,
)


class TestMerkleTree:
    """Test Merkle tree build and verify."""

    def test_build_merkle_empty(self):
        root = build_merkle_tree([])
        assert root
        assert len(root) == 64

    def test_build_merkle_single(self):
        root = build_merkle_tree(["abc123"])
        assert root
        assert len(root) == 64

    def test_build_merkle_deterministic(self):
        hashes = ["a", "b", "c"]
        r1 = build_merkle_tree(hashes)
        r2 = build_merkle_tree(hashes)
        assert r1 == r2

    def test_merkle_proof_verify(self):
        hashes = ["h1", "h2", "h3"]
        root = build_merkle_tree(hashes)
        proof = merkle_proof(hashes, "h2")
        assert proof is not None
        assert verify_merkle_proof("h2", proof, root)


class TestVerifyCommit:
    """Test commit verification (Merkle root, no signing)."""

    def test_verify_commit_no_merkle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ObjectStore(Path(tmpdir))
            blob = Blob(content=b"x")
            bh = blob.store(store)
            entries = [TreeEntry("100644", "blob", bh, "f", "")]
            tree = Tree(entries=entries)
            th = tree.store(store)
            commit = Commit(
                tree=th,
                parents=[],
                author="Test",
                timestamp="2025-01-01T00:00:00Z",
                message="m",
                metadata={},
            )
            ch = commit.store(store)
            ok, err = verify_commit(store, ch, None, mem_dir=Path(tmpdir))
            assert ok is False
            assert "merkle_root" in (err or "")
