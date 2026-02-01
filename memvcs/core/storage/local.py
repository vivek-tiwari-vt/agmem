"""
Local filesystem storage adapter for agmem.
"""

import os
import time
import fcntl
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from .base import StorageAdapter, StorageError, LockError, FileInfo


class LocalStorageAdapter(StorageAdapter):
    """Storage adapter for local filesystem."""

    def __init__(self, root_path: str):
        """
        Initialize local storage adapter.

        Args:
            root_path: Root directory for storage
        """
        self.root = Path(root_path).resolve()
        self._locks: dict = {}  # Active lock file handles

    def _resolve_path(self, path: str) -> Path:
        """Resolve a relative path to absolute path within root."""
        if not path:
            return self.root
        resolved = (self.root / path).resolve()
        # Security check: ensure path is within root
        if not str(resolved).startswith(str(self.root)):
            raise StorageError(f"Path '{path}' is outside storage root")
        return resolved

    def read_file(self, path: str) -> bytes:
        """Read a file's contents."""
        resolved = self._resolve_path(path)
        try:
            return resolved.read_bytes()
        except FileNotFoundError:
            raise StorageError(f"File not found: {path}")
        except IOError as e:
            raise StorageError(f"Error reading file {path}: {e}")

    def write_file(self, path: str, data: bytes) -> None:
        """Write data to a file."""
        resolved = self._resolve_path(path)
        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_bytes(data)
        except IOError as e:
            raise StorageError(f"Error writing file {path}: {e}")

    def exists(self, path: str) -> bool:
        """Check if a path exists."""
        resolved = self._resolve_path(path)
        return resolved.exists()

    def delete(self, path: str) -> bool:
        """Delete a file."""
        resolved = self._resolve_path(path)
        try:
            if resolved.exists():
                if resolved.is_dir():
                    resolved.rmdir()
                else:
                    resolved.unlink()
                return True
            return False
        except IOError as e:
            raise StorageError(f"Error deleting {path}: {e}")

    def list_dir(self, path: str = "") -> List[FileInfo]:
        """List contents of a directory."""
        resolved = self._resolve_path(path)

        if not resolved.exists():
            return []

        if not resolved.is_dir():
            raise StorageError(f"Not a directory: {path}")

        result = []
        for item in resolved.iterdir():
            try:
                stat = item.stat()
                rel_path = str(item.relative_to(self.root))

                result.append(
                    FileInfo(
                        path=rel_path,
                        size=stat.st_size if not item.is_dir() else 0,
                        modified=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        is_dir=item.is_dir(),
                    )
                )
            except IOError:
                # Skip files we can't stat
                continue

        return result

    def makedirs(self, path: str) -> None:
        """Create directory and any necessary parent directories."""
        resolved = self._resolve_path(path)
        resolved.mkdir(parents=True, exist_ok=True)

    def is_dir(self, path: str) -> bool:
        """Check if path is a directory."""
        resolved = self._resolve_path(path)
        return resolved.is_dir()

    def acquire_lock(self, lock_name: str, timeout: int = 30) -> bool:
        """
        Acquire a file-based lock.

        Uses fcntl for POSIX systems.
        """
        lock_path = self.root / ".locks" / f"{lock_name}.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        start_time = time.time()

        while True:
            try:
                # Open or create lock file
                lock_file = open(lock_path, "w")

                # Try to acquire exclusive lock
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

                # Write our PID to the lock file
                lock_file.write(str(os.getpid()))
                lock_file.flush()

                # Keep handle open to maintain lock
                self._locks[lock_name] = lock_file
                return True

            except (IOError, OSError):
                # Lock is held by another process
                if time.time() - start_time >= timeout:
                    raise LockError(f"Could not acquire lock '{lock_name}' within {timeout}s")
                time.sleep(0.1)

    def release_lock(self, lock_name: str) -> None:
        """Release a file-based lock."""
        if lock_name in self._locks:
            lock_file = self._locks.pop(lock_name)
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                lock_file.close()
            except (IOError, OSError):
                pass

            # Try to remove lock file
            lock_path = self.root / ".locks" / f"{lock_name}.lock"
            try:
                lock_path.unlink()
            except (IOError, OSError):
                pass

    def is_locked(self, lock_name: str) -> bool:
        """Check if a lock is currently held."""
        lock_path = self.root / ".locks" / f"{lock_name}.lock"

        if not lock_path.exists():
            return False

        try:
            # Try to acquire lock briefly
            with open(lock_path, "w") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            return False  # Lock is free
        except (IOError, OSError):
            return True  # Lock is held

    def get_root(self) -> Path:
        """Get the root path of this storage."""
        return self.root
