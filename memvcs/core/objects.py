"""
Object storage system for agmem.

Implements Git-style content-addressable storage with blob, tree, and commit objects.
"""

import hashlib
import json
import os
import zlib
from pathlib import Path
from typing import Optional, Dict, List, Any, Union
from dataclasses import dataclass, asdict
from datetime import datetime


def _valid_object_hash(hash_id: str) -> bool:
    """Return True if hash_id is safe for object paths (hex, 4-64 chars)."""
    if not hash_id or len(hash_id) < 4 or len(hash_id) > 64:
        return False
    return all(c in "0123456789abcdef" for c in hash_id.lower())


class ObjectStore:
    """Content-addressable object storage system."""

    def __init__(self, objects_dir: Path, encryptor: Optional[Any] = None):
        self.objects_dir = Path(objects_dir)
        self._encryptor = encryptor
        self._ensure_directories()

    def _ensure_directories(self):
        """Create object storage directories."""
        for obj_type in ["blob", "tree", "commit", "tag"]:
            (self.objects_dir / obj_type).mkdir(parents=True, exist_ok=True)

    def _get_object_path(self, hash_id: str, obj_type: str) -> Path:
        """Get storage path for an object. Validates hash_id to prevent path traversal."""
        if not _valid_object_hash(hash_id):
            raise ValueError(f"Invalid object hash: {hash_id!r}")
        prefix = hash_id[:2]
        suffix = hash_id[2:]
        return self.objects_dir / obj_type / prefix / suffix

    def _compute_hash(self, content: bytes, obj_type: str) -> str:
        """Compute SHA-256 hash of content with type header."""
        header = f"{obj_type} {len(content)}\0".encode()
        full_content = header + content
        return hashlib.sha256(full_content).hexdigest()

    def store(self, content: bytes, obj_type: str) -> str:
        """
        Store content and return its hash ID.

        Args:
            content: Raw bytes to store
            obj_type: Type of object ('blob', 'tree', 'commit', 'tag')

        Returns:
            SHA-256 hash ID of stored object
        """
        hash_id = self._compute_hash(content, obj_type)
        obj_path = self._get_object_path(hash_id, obj_type)

        # Don't store if already exists (deduplication)
        if obj_path.exists():
            return hash_id

        # Create directory if needed
        obj_path.parent.mkdir(parents=True, exist_ok=True)

        # Compress and optionally encrypt
        header = f"{obj_type} {len(content)}\0".encode()
        full_content = header + content
        compressed = zlib.compress(full_content)
        if self._encryptor:
            try:
                compressed = self._encryptor.encrypt_payload(compressed)
            except ValueError:
                pass  # no key; store plain compressed (legacy behavior)
        obj_path.write_bytes(compressed)
        return hash_id

    def retrieve(self, hash_id: str, obj_type: str) -> Optional[bytes]:
        """
        Retrieve content by hash ID (loose object or pack).

        Args:
            hash_id: SHA-256 hash of the object
            obj_type: Type of object

        Returns:
            Raw bytes content or None if not found
        """
        obj_path = self._get_object_path(hash_id, obj_type)

        if obj_path.exists():
            raw = obj_path.read_bytes()
            # Optionally decrypt (iv+tag minimum 12+16 bytes)
            if self._encryptor and len(raw) >= 12 + 16:
                try:
                    raw = self._encryptor.decrypt_payload(raw)
                except Exception:
                    pass  # legacy plain compressed
            full_content = zlib.decompress(raw)
            null_idx = full_content.index(b"\0")
            content = full_content[null_idx + 1 :]
            return content

        # Try pack file when loose object missing
        try:
            from .pack import retrieve_from_pack

            result = retrieve_from_pack(self.objects_dir, hash_id, expected_type=obj_type)
            if result is not None:
                return result[1]
        except Exception:
            pass
        return None

    def exists(self, hash_id: str, obj_type: str) -> bool:
        """Check if an object exists (loose or pack). Returns False for invalid hash (no raise)."""
        if not _valid_object_hash(hash_id):
            return False
        obj_path = self._get_object_path(hash_id, obj_type)
        if obj_path.exists():
            return True
        try:
            from .pack import retrieve_from_pack

            return retrieve_from_pack(self.objects_dir, hash_id, expected_type=obj_type) is not None
        except Exception:
            return False

    def delete(self, hash_id: str, obj_type: str) -> bool:
        """Delete an object. Returns True if deleted, False if not found."""
        obj_path = self._get_object_path(hash_id, obj_type)
        if obj_path.exists():
            obj_path.unlink()
            # Clean up empty parent directories
            if not any(obj_path.parent.iterdir()):
                obj_path.parent.rmdir()
            return True
        return False

    def list_objects(self, obj_type: str) -> List[str]:
        """List all objects of a given type."""
        obj_dir = self.objects_dir / obj_type
        if not obj_dir.exists():
            return []

        hashes = []
        for prefix_dir in obj_dir.iterdir():
            if prefix_dir.is_dir():
                for suffix_file in prefix_dir.iterdir():
                    hash_id = prefix_dir.name + suffix_file.name
                    hashes.append(hash_id)
        return hashes

    def get_size(self, hash_id: str, obj_type: str) -> int:
        """Get the compressed size of an object."""
        obj_path = self._get_object_path(hash_id, obj_type)
        if obj_path.exists():
            return obj_path.stat().st_size
        return 0


@dataclass
class Blob:
    """Blob object for storing raw memory content."""

    content: bytes

    def store(self, store: ObjectStore) -> str:
        """Store this blob and return its hash."""
        return store.store(self.content, "blob")

    @staticmethod
    def load(store: ObjectStore, hash_id: str) -> Optional["Blob"]:
        """Load a blob from storage."""
        content = store.retrieve(hash_id, "blob")
        if content is not None:
            return Blob(content=content)
        return None


@dataclass
class TreeEntry:
    """Entry in a tree object."""

    mode: str  # '100644' for file, '040000' for directory
    obj_type: str  # 'blob' or 'tree'
    hash: str
    name: str
    path: str = ""  # Relative path within tree


@dataclass
class Tree:
    """Tree object for storing directory structure."""

    entries: List[TreeEntry]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "type": "tree",
            "entries": [
                {"mode": e.mode, "type": e.obj_type, "hash": e.hash, "name": e.name, "path": e.path}
                for e in self.entries
            ],
        }

    def to_bytes(self) -> bytes:
        """Serialize to bytes."""
        return json.dumps(self.to_dict(), sort_keys=True).encode()

    def store(self, store: ObjectStore) -> str:
        """Store this tree and return its hash."""
        return store.store(self.to_bytes(), "tree")

    @staticmethod
    def load(store: ObjectStore, hash_id: str) -> Optional["Tree"]:
        """Load a tree from storage."""
        content = store.retrieve(hash_id, "tree")
        if content is None:
            return None

        data = json.loads(content)
        entries = [
            TreeEntry(
                mode=e["mode"],
                obj_type=e["type"],
                hash=e["hash"],
                name=e["name"],
                path=e.get("path", ""),
            )
            for e in data.get("entries", [])
        ]
        return Tree(entries=entries)

    def get_entry(self, name: str) -> Optional[TreeEntry]:
        """Get an entry by name."""
        for entry in self.entries:
            if entry.name == name:
                return entry
        return None


@dataclass
class Commit:
    """Commit object for storing memory snapshots."""

    tree: str  # Hash of tree object
    parents: List[str]  # Hashes of parent commits
    author: str
    timestamp: str
    message: str
    metadata: Dict[str, Any]  # Additional metadata

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "type": "commit",
            "tree": self.tree,
            "parents": self.parents,
            "author": self.author,
            "timestamp": self.timestamp,
            "message": self.message,
            "metadata": self.metadata,
        }

    def to_bytes(self) -> bytes:
        """Serialize to bytes."""
        return json.dumps(self.to_dict(), sort_keys=True).encode()

    def store(self, store: ObjectStore) -> str:
        """Store this commit and return its hash."""
        return store.store(self.to_bytes(), "commit")

    @staticmethod
    def load(store: ObjectStore, hash_id: str) -> Optional["Commit"]:
        """Load a commit from storage."""
        content = store.retrieve(hash_id, "commit")
        if content is None:
            return None

        data = json.loads(content)
        return Commit(
            tree=data["tree"],
            parents=data.get("parents", []),
            author=data["author"],
            timestamp=data["timestamp"],
            message=data["message"],
            metadata=data.get("metadata", {}),
        )

    def short_hash(self, store: ObjectStore) -> str:
        """Get short hash for display."""
        full_hash = self.store(store)
        return full_hash[:8]


@dataclass
class Tag:
    """Tag object for marking specific commits."""

    name: str
    commit_hash: str
    message: str
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "type": "tag",
            "name": self.name,
            "commit_hash": self.commit_hash,
            "message": self.message,
            "timestamp": self.timestamp,
        }

    def to_bytes(self) -> bytes:
        """Serialize to bytes."""
        return json.dumps(self.to_dict(), sort_keys=True).encode()

    def store(self, store: ObjectStore) -> str:
        """Store this tag and return its hash."""
        return store.store(self.to_bytes(), "tag")

    @staticmethod
    def load(store: ObjectStore, hash_id: str) -> Optional["Tag"]:
        """Load a tag from storage."""
        content = store.retrieve(hash_id, "tag")
        if content is None:
            return None

        data = json.loads(content)
        return Tag(
            name=data["name"],
            commit_hash=data["commit_hash"],
            message=data["message"],
            timestamp=data["timestamp"],
        )
