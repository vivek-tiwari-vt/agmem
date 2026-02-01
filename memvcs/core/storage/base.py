"""
Base storage adapter interface for agmem.

Defines the abstract interface that all storage backends must implement.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Iterator
from dataclasses import dataclass
from pathlib import Path


class StorageError(Exception):
    """Base exception for storage operations."""

    pass


class LockError(StorageError):
    """Exception raised when a lock cannot be acquired."""

    pass


@dataclass
class FileInfo:
    """Information about a file in storage."""

    path: str
    size: int
    modified: Optional[str] = None  # ISO 8601 timestamp
    is_dir: bool = False


class StorageAdapter(ABC):
    """
    Abstract base class for storage adapters.

    All storage backends (local filesystem, S3, GCS, etc.) must implement
    this interface to provide consistent access to storage operations.
    """

    @abstractmethod
    def read_file(self, path: str) -> bytes:
        """
        Read a file's contents.

        Args:
            path: Path to the file (relative to storage root)

        Returns:
            File contents as bytes

        Raises:
            StorageError: If file doesn't exist or can't be read
        """
        pass

    @abstractmethod
    def write_file(self, path: str, data: bytes) -> None:
        """
        Write data to a file.

        Args:
            path: Path to the file (relative to storage root)
            data: Data to write

        Raises:
            StorageError: If file can't be written
        """
        pass

    @abstractmethod
    def exists(self, path: str) -> bool:
        """
        Check if a path exists.

        Args:
            path: Path to check

        Returns:
            True if path exists, False otherwise
        """
        pass

    @abstractmethod
    def delete(self, path: str) -> bool:
        """
        Delete a file.

        Args:
            path: Path to the file

        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    def list_dir(self, path: str = "") -> List[FileInfo]:
        """
        List contents of a directory.

        Args:
            path: Directory path (empty for root)

        Returns:
            List of FileInfo objects for directory contents
        """
        pass

    @abstractmethod
    def makedirs(self, path: str) -> None:
        """
        Create directory and any necessary parent directories.

        Args:
            path: Directory path to create
        """
        pass

    @abstractmethod
    def is_dir(self, path: str) -> bool:
        """
        Check if path is a directory.

        Args:
            path: Path to check

        Returns:
            True if path is a directory
        """
        pass

    # Lock management methods

    @abstractmethod
    def acquire_lock(self, lock_name: str, timeout: int = 30) -> bool:
        """
        Acquire a distributed lock.

        Args:
            lock_name: Name of the lock to acquire
            timeout: Maximum seconds to wait for lock

        Returns:
            True if lock acquired successfully

        Raises:
            LockError: If lock cannot be acquired within timeout
        """
        pass

    @abstractmethod
    def release_lock(self, lock_name: str) -> None:
        """
        Release a distributed lock.

        Args:
            lock_name: Name of the lock to release
        """
        pass

    @abstractmethod
    def is_locked(self, lock_name: str) -> bool:
        """
        Check if a lock is currently held.

        Args:
            lock_name: Name of the lock to check

        Returns:
            True if lock is held
        """
        pass

    # Convenience methods (can be overridden for efficiency)

    def read_text(self, path: str, encoding: str = "utf-8") -> str:
        """Read file as text."""
        return self.read_file(path).decode(encoding)

    def write_text(self, path: str, text: str, encoding: str = "utf-8") -> None:
        """Write text to file."""
        self.write_file(path, text.encode(encoding))

    def walk(self, path: str = "") -> Iterator[tuple]:
        """
        Walk through directory tree.

        Yields:
            Tuples of (dirpath, dirnames, filenames)
        """
        contents = self.list_dir(path)

        dirs = []
        files = []

        for item in contents:
            if item.is_dir:
                dirs.append(item.path.split("/")[-1])
            else:
                files.append(item.path.split("/")[-1])

        yield (path, dirs, files)

        for dirname in dirs:
            subpath = f"{path}/{dirname}" if path else dirname
            yield from self.walk(subpath)

    def copy_file(self, src: str, dst: str) -> None:
        """Copy a file within storage."""
        data = self.read_file(src)
        self.write_file(dst, data)

    def move_file(self, src: str, dst: str) -> None:
        """Move a file within storage."""
        self.copy_file(src, dst)
        self.delete(src)


class CachingStorageAdapter(StorageAdapter):
    """
    Storage adapter that caches remote operations locally.

    Used for cloud storage backends to minimize network requests.
    """

    def __init__(self, remote: StorageAdapter, cache_dir: str):
        """
        Initialize caching adapter.

        Args:
            remote: Remote storage adapter
            cache_dir: Local directory for caching
        """
        self.remote = remote
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._dirty: set = set()  # Paths that need to be pushed

    def _cache_path(self, path: str) -> Path:
        """Get local cache path for a remote path."""
        return self.cache_dir / path

    def read_file(self, path: str) -> bytes:
        """Read from cache, fetching from remote if needed."""
        cache_path = self._cache_path(path)

        if not cache_path.exists():
            # Fetch from remote
            data = self.remote.read_file(path)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(data)

        return cache_path.read_bytes()

    def write_file(self, path: str, data: bytes) -> None:
        """Write to cache and mark as dirty."""
        cache_path = self._cache_path(path)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(data)
        self._dirty.add(path)

    def exists(self, path: str) -> bool:
        """Check if path exists in cache or remote."""
        cache_path = self._cache_path(path)
        return cache_path.exists() or self.remote.exists(path)

    def delete(self, path: str) -> bool:
        """Delete from cache and remote."""
        cache_path = self._cache_path(path)
        if cache_path.exists():
            cache_path.unlink()
        self._dirty.discard(path)
        return self.remote.delete(path)

    def list_dir(self, path: str = "") -> List[FileInfo]:
        """List directory from remote."""
        return self.remote.list_dir(path)

    def makedirs(self, path: str) -> None:
        """Create directory in cache."""
        cache_path = self._cache_path(path)
        cache_path.mkdir(parents=True, exist_ok=True)

    def is_dir(self, path: str) -> bool:
        """Check if path is directory."""
        cache_path = self._cache_path(path)
        if cache_path.exists():
            return cache_path.is_dir()
        return self.remote.is_dir(path)

    def acquire_lock(self, lock_name: str, timeout: int = 30) -> bool:
        """Acquire lock on remote."""
        return self.remote.acquire_lock(lock_name, timeout)

    def release_lock(self, lock_name: str) -> None:
        """Release lock on remote."""
        self.remote.release_lock(lock_name)

    def is_locked(self, lock_name: str) -> bool:
        """Check if lock is held on remote."""
        return self.remote.is_locked(lock_name)

    def sync_to_remote(self) -> int:
        """
        Push all dirty files to remote.

        Returns:
            Number of files synced
        """
        count = 0
        for path in list(self._dirty):
            cache_path = self._cache_path(path)
            if cache_path.exists():
                self.remote.write_file(path, cache_path.read_bytes())
                count += 1
            self._dirty.discard(path)
        return count

    def sync_from_remote(self, paths: Optional[List[str]] = None) -> int:
        """
        Pull files from remote to cache.

        Args:
            paths: Specific paths to sync, or None for all

        Returns:
            Number of files synced
        """
        if paths is None:
            # Sync entire remote
            count = 0
            for dirpath, _, filenames in self.remote.walk():
                for filename in filenames:
                    path = f"{dirpath}/{filename}" if dirpath else filename
                    data = self.remote.read_file(path)
                    cache_path = self._cache_path(path)
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    cache_path.write_bytes(data)
                    count += 1
            return count
        else:
            for path in paths:
                data = self.remote.read_file(path)
                cache_path = self._cache_path(path)
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_bytes(data)
            return len(paths)

    def get_dirty_paths(self) -> List[str]:
        """Get list of paths that need to be pushed."""
        return list(self._dirty)

    def clear_cache(self) -> None:
        """Clear the local cache."""
        import shutil

        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._dirty.clear()
