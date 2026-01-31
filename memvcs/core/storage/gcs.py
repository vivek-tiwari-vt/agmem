"""
Google Cloud Storage adapter for agmem.
"""

import time
import uuid
from typing import List, Optional
from datetime import datetime

try:
    from google.cloud import storage
    from google.cloud.exceptions import NotFound
    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False

from .base import StorageAdapter, StorageError, LockError, FileInfo


class GCSStorageAdapter(StorageAdapter):
    """Storage adapter for Google Cloud Storage."""
    
    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        project: Optional[str] = None,
        credentials_path: Optional[str] = None
    ):
        """
        Initialize GCS storage adapter.
        
        Args:
            bucket: GCS bucket name
            prefix: Key prefix for all operations
            project: GCP project ID
            credentials_path: Path to service account JSON file
        """
        if not GCS_AVAILABLE:
            raise ImportError(
                "google-cloud-storage is required for GCS. "
                "Install with: pip install agmem[cloud]"
            )
        
        self.bucket_name = bucket
        self.prefix = prefix.strip('/')
        self._lock_id = str(uuid.uuid4())
        
        # Build client
        if credentials_path:
            self.client = storage.Client.from_service_account_json(credentials_path)
        elif project:
            self.client = storage.Client(project=project)
        else:
            self.client = storage.Client()
        
        self.bucket = self.client.bucket(bucket)
    
    @classmethod
    def from_url(cls, url: str) -> 'GCSStorageAdapter':
        """
        Create adapter from GCS URL.
        
        Args:
            url: GCS URL (gs://bucket/prefix)
            
        Returns:
            GCSStorageAdapter instance
        """
        if not url.startswith('gs://'):
            raise ValueError(f"Invalid GCS URL: {url}")
        
        path = url[5:]  # Remove 'gs://'
        parts = path.split('/', 1)
        bucket = parts[0]
        prefix = parts[1] if len(parts) > 1 else ""
        
        return cls(bucket=bucket, prefix=prefix)
    
    def _key(self, path: str) -> str:
        """Convert relative path to GCS key."""
        if not path:
            return self.prefix
        if self.prefix:
            return f"{self.prefix}/{path}"
        return path
    
    def _path(self, key: str) -> str:
        """Convert GCS key to relative path."""
        if self.prefix and key.startswith(self.prefix + '/'):
            return key[len(self.prefix) + 1:]
        return key
    
    def read_file(self, path: str) -> bytes:
        """Read a file's contents from GCS."""
        key = self._key(path)
        blob = self.bucket.blob(key)
        
        try:
            return blob.download_as_bytes()
        except NotFound:
            raise StorageError(f"File not found: {path}")
        except Exception as e:
            raise StorageError(f"Error reading {path}: {e}")
    
    def write_file(self, path: str, data: bytes) -> None:
        """Write data to GCS."""
        key = self._key(path)
        blob = self.bucket.blob(key)
        
        try:
            blob.upload_from_string(data)
        except Exception as e:
            raise StorageError(f"Error writing {path}: {e}")
    
    def exists(self, path: str) -> bool:
        """Check if a key exists in GCS."""
        key = self._key(path)
        blob = self.bucket.blob(key)
        
        if blob.exists():
            return True
        
        # Check if it's a "directory"
        prefix = key + '/' if key else ''
        blobs = list(self.bucket.list_blobs(prefix=prefix, max_results=1))
        return len(blobs) > 0
    
    def delete(self, path: str) -> bool:
        """Delete an object from GCS."""
        key = self._key(path)
        blob = self.bucket.blob(key)
        
        try:
            blob.delete()
            return True
        except NotFound:
            return False
        except Exception as e:
            raise StorageError(f"Error deleting {path}: {e}")
    
    def list_dir(self, path: str = "") -> List[FileInfo]:
        """List contents of a "directory" in GCS."""
        prefix = self._key(path)
        if prefix and not prefix.endswith('/'):
            prefix += '/'
        
        result = []
        seen_dirs = set()
        
        try:
            # List with delimiter to get "directories"
            blobs = self.bucket.list_blobs(prefix=prefix, delimiter='/')
            
            # Process blobs (files)
            for blob in blobs:
                if blob.name == prefix:
                    continue
                
                result.append(FileInfo(
                    path=self._path(blob.name),
                    size=blob.size or 0,
                    modified=blob.updated.isoformat() if blob.updated else None,
                    is_dir=False
                ))
            
            # Process prefixes (directories)
            for dir_prefix in blobs.prefixes:
                dir_name = dir_prefix.rstrip('/').split('/')[-1]
                if dir_name not in seen_dirs:
                    seen_dirs.add(dir_name)
                    result.append(FileInfo(
                        path=self._path(dir_prefix.rstrip('/')),
                        size=0,
                        is_dir=True
                    ))
        
        except Exception as e:
            raise StorageError(f"Error listing {path}: {e}")
        
        return result
    
    def makedirs(self, path: str) -> None:
        """Create a "directory" in GCS (no-op, directories are implicit)."""
        pass
    
    def is_dir(self, path: str) -> bool:
        """Check if path is a "directory" in GCS."""
        key = self._key(path)
        if not key:
            return True  # Root is always a directory
        
        # Check if there are any keys with this prefix
        prefix = key + '/'
        blobs = list(self.bucket.list_blobs(prefix=prefix, max_results=1))
        return len(blobs) > 0
    
    def acquire_lock(self, lock_name: str, timeout: int = 30) -> bool:
        """
        Acquire a distributed lock using GCS.
        
        Uses generation-based conditional updates for lock safety.
        """
        start_time = time.time()
        lock_key = self._key(f".locks/{lock_name}.lock")
        blob = self.bucket.blob(lock_key)
        
        while True:
            try:
                # Check if lock exists and is not stale
                if blob.exists():
                    blob.reload()
                    existing = blob.download_as_string().decode()
                    parts = existing.split(':')
                    if len(parts) == 2:
                        _, ts = parts
                        if int(time.time()) - int(ts) < 300:  # Lock is fresh
                            if time.time() - start_time >= timeout:
                                raise LockError(
                                    f"Could not acquire lock '{lock_name}' within {timeout}s"
                                )
                            time.sleep(0.5)
                            continue
                
                # Create/overwrite lock
                lock_data = f"{self._lock_id}:{int(time.time())}"
                blob.upload_from_string(lock_data)
                
                # Verify we own the lock
                time.sleep(0.1)
                blob.reload()
                content = blob.download_as_string().decode()
                if content.startswith(self._lock_id):
                    return True
                
                # Someone else got it
                if time.time() - start_time >= timeout:
                    raise LockError(f"Could not acquire lock '{lock_name}' within {timeout}s")
                time.sleep(0.5)
                
            except NotFound:
                # Lock doesn't exist, try to create it
                try:
                    lock_data = f"{self._lock_id}:{int(time.time())}"
                    blob.upload_from_string(lock_data)
                    return True
                except Exception:
                    if time.time() - start_time >= timeout:
                        raise LockError(f"Could not acquire lock '{lock_name}' within {timeout}s")
                    time.sleep(0.5)
            except Exception as e:
                raise StorageError(f"Error acquiring lock: {e}")
    
    def release_lock(self, lock_name: str) -> None:
        """Release a distributed lock."""
        lock_key = self._key(f".locks/{lock_name}.lock")
        blob = self.bucket.blob(lock_key)
        
        try:
            # Only delete if we own the lock
            if blob.exists():
                content = blob.download_as_string().decode()
                if content.startswith(self._lock_id):
                    blob.delete()
        except Exception:
            pass  # Ignore errors on release
    
    def is_locked(self, lock_name: str) -> bool:
        """Check if a lock is currently held."""
        lock_key = self._key(f".locks/{lock_name}.lock")
        blob = self.bucket.blob(lock_key)
        
        try:
            if not blob.exists():
                return False
            
            content = blob.download_as_string().decode()
            parts = content.split(':')
            if len(parts) == 2:
                _, ts = parts
                # Lock is valid if less than 5 minutes old
                return int(time.time()) - int(ts) < 300
            return False
        except Exception:
            return False
