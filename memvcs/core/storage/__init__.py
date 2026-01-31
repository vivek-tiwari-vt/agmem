"""
Storage adapters for agmem.

Provides abstraction layer for different storage backends.
"""

from typing import Optional

from .base import StorageAdapter, StorageError, LockError
from .local import LocalStorageAdapter

__all__ = [
    'StorageAdapter',
    'StorageError',
    'LockError',
    'LocalStorageAdapter',
]

# Try to import optional cloud adapters
try:
    from .s3 import S3StorageAdapter
    __all__.append('S3StorageAdapter')
except ImportError:
    pass

try:
    from .gcs import GCSStorageAdapter
    __all__.append('GCSStorageAdapter')
except ImportError:
    pass


def get_adapter(url: str, config: Optional[dict] = None) -> StorageAdapter:
    """
    Get the appropriate storage adapter for a URL.
    
    Args:
        url: Storage URL (file://, s3://, gs://)
        config: Optional agmem config dict (from load_agmem_config). Used for
            S3/GCS credentials and options; credentials resolved from env only.
        
    Returns:
        Appropriate StorageAdapter instance
        
    Raises:
        ValueError: If URL scheme is not supported
    """
    if url.startswith('file://'):
        path = url[7:]  # Remove 'file://' prefix
        return LocalStorageAdapter(path)
    
    elif url.startswith('s3://'):
        try:
            from .s3 import S3StorageAdapter
            return S3StorageAdapter.from_url(url, config=config)
        except ImportError:
            raise ImportError(
                "S3 storage requires boto3. Install with: pip install agmem[cloud]"
            )
    
    elif url.startswith('gs://'):
        try:
            from .gcs import GCSStorageAdapter
            return GCSStorageAdapter.from_url(url, config=config)
        except ImportError:
            raise ImportError(
                "GCS storage requires google-cloud-storage. Install with: pip install agmem[cloud]"
            )
    
    else:
        # Assume local path
        return LocalStorageAdapter(url)
