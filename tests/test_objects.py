"""Tests for object storage."""

import pytest
import tempfile
from pathlib import Path

from memvcs.core.objects import ObjectStore, Blob, Tree, TreeEntry, Commit


class TestObjectStore:
    """Test object storage functionality."""
    
    def test_store_and_retrieve_blob(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ObjectStore(Path(tmpdir))
            
            content = b"Hello, agmem!"
            hash_id = store.store(content, 'blob')
            
            # Should be able to retrieve
            retrieved = store.retrieve(hash_id, 'blob')
            assert retrieved == content
    
    def test_deduplication(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ObjectStore(Path(tmpdir))
            
            content = b"Duplicate content"
            hash1 = store.store(content, 'blob')
            hash2 = store.store(content, 'blob')
            
            # Same content should produce same hash
            assert hash1 == hash2
            
            # Should only have one object
            objects = store.list_objects('blob')
            assert len(objects) == 1
    
    def test_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ObjectStore(Path(tmpdir))
            
            content = b"Test content"
            hash_id = store.store(content, 'blob')
            
            assert store.exists(hash_id, 'blob')
            assert not store.exists('invalid', 'blob')


class TestBlob:
    """Test blob objects."""
    
    def test_blob_store_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ObjectStore(Path(tmpdir))
            
            content = b"Test blob content"
            blob = Blob(content=content)
            hash_id = blob.store(store)
            
            loaded = Blob.load(store, hash_id)
            assert loaded is not None
            assert loaded.content == content


class TestTree:
    """Test tree objects."""
    
    def test_tree_store_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ObjectStore(Path(tmpdir))
            
            entries = [
                TreeEntry(mode='100644', obj_type='blob', hash='abc123', name='file1.md', path=''),
                TreeEntry(mode='100644', obj_type='blob', hash='def456', name='file2.md', path=''),
            ]
            tree = Tree(entries=entries)
            hash_id = tree.store(store)
            
            loaded = Tree.load(store, hash_id)
            assert loaded is not None
            assert len(loaded.entries) == 2
            assert loaded.entries[0].name == 'file1.md'


class TestCommit:
    """Test commit objects."""
    
    def test_commit_store_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ObjectStore(Path(tmpdir))
            
            commit = Commit(
                tree='tree_hash',
                parents=['parent_hash'],
                author='Test <test@example.com>',
                timestamp='2026-01-31T00:00:00Z',
                message='Test commit',
                metadata={'test': True}
            )
            hash_id = commit.store(store)
            
            loaded = Commit.load(store, hash_id)
            assert loaded is not None
            assert loaded.message == 'Test commit'
            assert loaded.author == 'Test <test@example.com>'
            assert loaded.parents == ['parent_hash']
