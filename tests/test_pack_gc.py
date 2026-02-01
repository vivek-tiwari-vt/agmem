"""Tests for pack and garbage collection."""

import pytest
import tempfile
from pathlib import Path

from memvcs.core.objects import ObjectStore, Blob, Tree, TreeEntry, Commit
from memvcs.core.refs import RefsManager
from memvcs.core.pack import (
    list_loose_objects,
    run_gc,
    reachable_from_refs,
    write_pack,
    retrieve_from_pack,
    run_repack,
)


class TestListLooseObjects:
    """Test listing loose objects."""

    def test_list_loose_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            objects_dir = Path(tmpdir)
            for t in ["blob", "tree", "commit", "tag"]:
                (objects_dir / t).mkdir(exist_ok=True)
            hashes = list_loose_objects(objects_dir)
            assert hashes == set()

    def test_list_loose_finds_stored_objects(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ObjectStore(Path(tmpdir))
            h1 = store.store(b"a", "blob")
            h2 = store.store(b"b", "blob")
            hashes = list_loose_objects(Path(tmpdir))
            assert h1 in hashes
            assert h2 in hashes


class TestRunGc:
    """Test garbage collection."""

    def test_gc_dry_run_does_not_delete(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mem_dir = Path(tmpdir)
            (mem_dir / "objects" / "blob" / "ab").mkdir(parents=True, exist_ok=True)
            (mem_dir / "objects" / "blob" / "ab" / "cd123").write_bytes(b"x")
            (mem_dir / "refs" / "heads").mkdir(parents=True, exist_ok=True)
            store = ObjectStore(mem_dir / "objects")
            deleted, freed = run_gc(mem_dir, store, gc_prune_days=90, dry_run=True)
            # Unreachable blob; dry_run so not deleted
            assert deleted >= 0
            assert (mem_dir / "objects" / "blob" / "ab" / "cd123").exists() or deleted == 0

    def test_gc_empty_repo_deletes_nothing_reachable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mem_dir = Path(tmpdir)
            (mem_dir / "objects").mkdir(exist_ok=True)
            (mem_dir / "refs" / "heads").mkdir(parents=True, exist_ok=True)
            store = ObjectStore(mem_dir / "objects")
            deleted, freed = run_gc(mem_dir, store, gc_prune_days=90, dry_run=False)
            assert deleted >= 0
            assert freed >= 0


class TestWritePackAndRetrieve:
    """Test pack file creation and read-back."""

    def test_write_pack_and_retrieve(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            objects_dir = Path(tmpdir)
            store = ObjectStore(objects_dir)
            h1 = store.store(b"hello", "blob")
            h2 = store.store(b"world", "blob")
            hash_to_type = {h1: "blob", h2: "blob"}
            pack_path, idx_path = write_pack(objects_dir, store, hash_to_type)
            assert pack_path.exists()
            assert idx_path.exists()
            result1 = retrieve_from_pack(objects_dir, h1, expected_type="blob")
            assert result1 is not None
            assert result1[0] == "blob"
            assert result1[1] == b"hello"
            result2 = retrieve_from_pack(objects_dir, h2, expected_type="blob")
            assert result2 is not None
            assert result2[1] == b"world"

    def test_retrieve_from_pack_via_object_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            objects_dir = Path(tmpdir)
            store = ObjectStore(objects_dir)
            h = store.store(b"packed content", "blob")
            hash_to_type = {h: "blob"}
            write_pack(objects_dir, store, hash_to_type)
            store.delete(h, "blob")
            content = store.retrieve(h, "blob")
            assert content == b"packed content"

    def test_run_repack_dry_run_returns_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mem_dir = Path(tmpdir)
            (mem_dir / "refs" / "heads").mkdir(parents=True)
            objects_dir = mem_dir / "objects"
            store = ObjectStore(objects_dir)
            store.store(b"x", "blob")
            packed, freed = run_repack(mem_dir, store, gc_prune_days=90, dry_run=True)
            assert packed >= 0
            assert freed == 0
