"""Edge case and stress tests for agmem."""

import os
import tempfile
from pathlib import Path

import pytest

from memvcs.core.objects import ObjectStore, Blob, Tree, TreeEntry, Commit
from memvcs.core.repository import Repository
from memvcs.core.merge import MergeEngine
from memvcs.core.constants import MEMORY_TYPES


class TestObjectStoreEdgeCases:
    """Edge cases for object storage."""

    def test_store_empty_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ObjectStore(Path(tmpdir))
            hash_id = store.store(b"", "blob")
            assert hash_id is not None
            retrieved = store.retrieve(hash_id, "blob")
            assert retrieved == b""

    def test_store_nonexistent_retrieve_returns_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ObjectStore(Path(tmpdir))
            result = store.retrieve("a" * 64, "blob")
            assert result is None

    def test_list_objects_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ObjectStore(Path(tmpdir))
            blobs = store.list_objects("blob")
            assert blobs == []

    def test_store_unicode_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ObjectStore(Path(tmpdir))
            content = "日本語 🎉 émojis 中文".encode("utf-8")
            hash_id = store.store(content, "blob")
            retrieved = store.retrieve(hash_id, "blob")
            assert retrieved == content

    def test_store_binary_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ObjectStore(Path(tmpdir))
            content = bytes(range(256))
            hash_id = store.store(content, "blob")
            retrieved = store.retrieve(hash_id, "blob")
            assert retrieved == content

    def test_object_store_uses_singular_directories(self):
        """Verify objects are stored in blob/, tree/, commit/ (not plural)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ObjectStore(Path(tmpdir))
            store.store(b"x", "blob")
            blob_dir = store.objects_dir / "blob"
            assert blob_dir.exists()
            blobs_dir = store.objects_dir / "blobs"
            assert not blobs_dir.exists()


class TestRepositoryEdgeCases:
    """Edge cases for repository operations."""

    def test_stage_nonexistent_file_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(Path(tmpdir))
            with pytest.raises(FileNotFoundError):
                repo.stage_file("nonexistent.md")

    def test_commit_empty_staging_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(Path(tmpdir))
            with pytest.raises(ValueError, match="No changes staged"):
                repo.commit("Empty commit")

    def test_checkout_invalid_ref_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(Path(tmpdir))
            (repo.current_dir / "semantic" / "f.md").write_text("x")
            repo.stage_file("semantic/f.md")
            repo.commit("Initial")
            with pytest.raises(ValueError, match="Reference not found"):
                repo.checkout("nonexistent-branch-xyz")

    def test_checkout_with_staged_changes_raises_without_force(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(Path(tmpdir))
            (repo.current_dir / "semantic" / "f.md").write_text("x")
            repo.stage_file("semantic/f.md")
            repo.commit("Initial")
            repo.refs.create_branch("other")
            (repo.current_dir / "semantic" / "f.md").write_text("y")
            repo.stage_file("semantic/f.md")
            with pytest.raises(ValueError, match="uncommitted changes"):
                repo.checkout("other")

    def test_merge_successful_fast_forward(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(Path(tmpdir))
            (repo.current_dir / "semantic" / "a.md").write_text("base")
            repo.stage_file("semantic/a.md")
            repo.commit("Base")
            repo.refs.create_branch("feature")
            repo.refs.set_head_branch("feature")
            (repo.current_dir / "semantic" / "b.md").write_text("new")
            repo.stage_file("semantic/b.md")
            repo.commit("Feature")
            repo.refs.set_head_branch("main")
            engine = MergeEngine(repo)
            result = engine.merge("feature")
            assert result.success
            assert result.commit_hash is not None

    def test_stash_create_and_pop(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(Path(tmpdir))
            (repo.current_dir / "semantic" / "f.md").write_text("x")
            repo.stage_file("semantic/f.md")
            repo.commit("Initial")
            (repo.current_dir / "semantic" / "f.md").write_text("modified")
            stash_hash = repo.stash_create("WIP")
            assert stash_hash is not None
            content_before = (repo.current_dir / "semantic" / "f.md").read_text()
            assert content_before == "x"
            popped = repo.stash_pop(0)
            assert popped is not None
            content_after = (repo.current_dir / "semantic" / "f.md").read_text()
            assert content_after == "modified"

    def test_stash_create_nothing_returns_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(Path(tmpdir))
            (repo.current_dir / "semantic" / "f.md").write_text("x")
            repo.stage_file("semantic/f.md")
            repo.commit("Initial")
            stash_hash = repo.stash_create()
            assert stash_hash is None

    def test_tree_entries_with_nested_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ObjectStore(Path(tmpdir) / "objects")
            entries = [
                TreeEntry(
                    mode="100644",
                    obj_type="blob",
                    hash="a" * 64,
                    name="file.md",
                    path="episodic/a/b",
                ),
            ]
            tree = Tree(entries=entries)
            hash_id = tree.store(store)
            loaded = Tree.load(store, hash_id)
            assert loaded.entries[0].path == "episodic/a/b"
            assert loaded.entries[0].name == "file.md"


class TestInitEdgeCases:
    """Edge cases for repository initialization."""

    def test_init_creates_all_memory_types(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(Path(tmpdir))
            for mem_type in MEMORY_TYPES:
                assert (repo.current_dir / mem_type).exists()
                assert (repo.current_dir / mem_type).is_dir()

    def test_init_twice_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Repository.init(Path(tmpdir))
            with pytest.raises(ValueError, match="already exists"):
                Repository.init(Path(tmpdir))


class TestStageDirectoryEdgeCases:
    """Edge cases for stage_directory."""

    def test_stage_directory_includes_all_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(Path(tmpdir))
            (repo.current_dir / "semantic" / "a.md").write_text("a")
            (repo.current_dir / "semantic" / "b.md").write_text("b")
            staged = repo.stage_directory("semantic")
            assert "semantic/a.md" in staged
            assert "semantic/b.md" in staged
            assert len(staged) == 2
