"""
S3/MinIO storage adapter for agmem.

Supports Amazon S3, MinIO, and any S3-compatible storage.
Credentials are resolved from config via env var names only (never stored in config).
"""

import time
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime

try:
    import boto3
    from botocore.exceptions import ClientError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False

from .base import StorageAdapter, StorageError, LockError, FileInfo


def _apply_s3_config(kwargs: Dict[str, Any], config: Optional[Dict[str, Any]]) -> None:
    """Merge S3 options from agmem config into kwargs; credentials from env only."""
    if not config:
        return
    try:
        from memvcs.core.config_loader import get_s3_options_from_config
        opts = get_s3_options_from_config(config)
        for key in ("region", "endpoint_url", "lock_table"):
            if opts.get(key) is not None:
                kwargs[key] = opts[key]
        if opts.get("access_key") is not None and opts.get("secret_key") is not None:
            kwargs["access_key"] = opts["access_key"]
            kwargs["secret_key"] = opts["secret_key"]
    except ImportError:
        pass


class S3StorageAdapter(StorageAdapter):
    """Storage adapter for S3 and S3-compatible storage (MinIO, etc.)."""
    
    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        region: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        lock_table: Optional[str] = None
    ):
        """
        Initialize S3 storage adapter.
        
        Args:
            bucket: S3 bucket name
            prefix: Key prefix for all operations
            region: AWS region
            endpoint_url: Custom endpoint URL (for MinIO)
            access_key: AWS access key (optional, uses default credentials if not provided)
            secret_key: AWS secret key
            lock_table: DynamoDB table for distributed locks (optional)
        """
        if not BOTO3_AVAILABLE:
            raise ImportError("boto3 is required for S3 storage. Install with: pip install agmem[cloud]")
        
        self.bucket = bucket
        self.prefix = prefix.strip('/')
        self.lock_table = lock_table
        self._lock_id = str(uuid.uuid4())  # Unique ID for this instance
        
        # Build S3 client
        client_kwargs = {}
        if region:
            client_kwargs['region_name'] = region
        if endpoint_url:
            client_kwargs['endpoint_url'] = endpoint_url
        if access_key and secret_key:
            client_kwargs['aws_access_key_id'] = access_key
            client_kwargs['aws_secret_access_key'] = secret_key
        
        self.s3 = boto3.client('s3', **client_kwargs)
        
        # DynamoDB for locks (optional)
        if lock_table:
            self.dynamodb = boto3.client('dynamodb', **client_kwargs)
        else:
            self.dynamodb = None
    
    @classmethod
    def from_url(cls, url: str, config: Optional[Dict[str, Any]] = None) -> 'S3StorageAdapter':
        """
        Create adapter from S3 URL. Optional config supplies region, endpoint,
        and env var names for credentials; credentials are resolved from env only.
        
        Args:
            url: S3 URL (s3://bucket/prefix)
            config: Optional agmem config dict (cloud.s3); credentials from env vars
            
        Returns:
            S3StorageAdapter instance
        """
        if not url.startswith('s3://'):
            raise ValueError(f"Invalid S3 URL: {url}")
        path = url[5:]  # Remove 's3://'
        parts = path.split('/', 1)
        bucket = parts[0]
        prefix = parts[1] if len(parts) > 1 else ""
        kwargs: Dict[str, Any] = {"bucket": bucket, "prefix": prefix}
        _apply_s3_config(kwargs, config)
        return cls(**kwargs)
    
    def _key(self, path: str) -> str:
        """Convert relative path to S3 key."""
        if not path:
            return self.prefix
        if self.prefix:
            return f"{self.prefix}/{path}"
        return path
    
    def _path(self, key: str) -> str:
        """Convert S3 key to relative path."""
        if self.prefix and key.startswith(self.prefix + '/'):
            return key[len(self.prefix) + 1:]
        return key
    
    def read_file(self, path: str) -> bytes:
        """Read a file's contents from S3."""
        key = self._key(path)
        try:
            response = self.s3.get_object(Bucket=self.bucket, Key=key)
            return response['Body'].read()
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                raise StorageError(f"File not found: {path}")
            raise StorageError(f"Error reading {path}: {e}")
    
    def write_file(self, path: str, data: bytes) -> None:
        """Write data to S3."""
        key = self._key(path)
        try:
            self.s3.put_object(Bucket=self.bucket, Key=key, Body=data)
        except ClientError as e:
            raise StorageError(f"Error writing {path}: {e}")
    
    def exists(self, path: str) -> bool:
        """Check if a key exists in S3."""
        key = self._key(path)
        try:
            self.s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            # Check if it's a "directory" (has keys with this prefix)
            response = self.s3.list_objects_v2(
                Bucket=self.bucket,
                Prefix=key + '/',
                MaxKeys=1
            )
            return response.get('KeyCount', 0) > 0
    
    def delete(self, path: str) -> bool:
        """Delete an object from S3."""
        key = self._key(path)
        try:
            self.s3.delete_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False
    
    def list_dir(self, path: str = "") -> List[FileInfo]:
        """List contents of a "directory" in S3."""
        prefix = self._key(path)
        if prefix and not prefix.endswith('/'):
            prefix += '/'
        
        result = []
        seen_dirs = set()
        
        try:
            paginator = self.s3.get_paginator('list_objects_v2')
            
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix, Delimiter='/'):
                # Add "directories" (common prefixes)
                for cp in page.get('CommonPrefixes', []):
                    dir_prefix = cp['Prefix'].rstrip('/')
                    dir_name = dir_prefix.split('/')[-1]
                    if dir_name not in seen_dirs:
                        seen_dirs.add(dir_name)
                        result.append(FileInfo(
                            path=self._path(dir_prefix),
                            size=0,
                            is_dir=True
                        ))
                
                # Add files
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    if key == prefix:
                        continue  # Skip the prefix itself
                    
                    result.append(FileInfo(
                        path=self._path(key),
                        size=obj['Size'],
                        modified=obj['LastModified'].isoformat(),
                        is_dir=False
                    ))
        
        except ClientError as e:
            raise StorageError(f"Error listing {path}: {e}")
        
        return result
    
    def makedirs(self, path: str) -> None:
        """
        Create a "directory" in S3.
        
        S3 doesn't have real directories, so this is a no-op.
        Directories are created implicitly when objects are written.
        """
        pass
    
    def is_dir(self, path: str) -> bool:
        """Check if path is a "directory" in S3."""
        key = self._key(path)
        if not key:
            return True  # Root is always a directory
        
        # Check if there are any keys with this prefix
        response = self.s3.list_objects_v2(
            Bucket=self.bucket,
            Prefix=key + '/',
            MaxKeys=1
        )
        return response.get('KeyCount', 0) > 0
    
    def acquire_lock(self, lock_name: str, timeout: int = 30) -> bool:
        """
        Acquire a distributed lock.
        
        Uses DynamoDB if configured, otherwise uses S3 conditional writes.
        """
        if self.dynamodb and self.lock_table:
            return self._acquire_dynamodb_lock(lock_name, timeout)
        else:
            return self._acquire_s3_lock(lock_name, timeout)
    
    def _acquire_dynamodb_lock(self, lock_name: str, timeout: int) -> bool:
        """Acquire lock using DynamoDB."""
        start_time = time.time()
        lock_key = f"{self.prefix}/{lock_name}" if self.prefix else lock_name
        
        while True:
            try:
                # Try to create lock item with conditional write
                self.dynamodb.put_item(
                    TableName=self.lock_table,
                    Item={
                        'LockKey': {'S': lock_key},
                        'LockId': {'S': self._lock_id},
                        'Timestamp': {'N': str(int(time.time()))},
                        'TTL': {'N': str(int(time.time()) + 300)}  # 5 min TTL
                    },
                    ConditionExpression='attribute_not_exists(LockKey)'
                )
                return True
            
            except ClientError as e:
                if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                    # Lock exists, check if it's stale
                    if time.time() - start_time >= timeout:
                        raise LockError(f"Could not acquire lock '{lock_name}' within {timeout}s")
                    time.sleep(0.5)
                else:
                    raise StorageError(f"Error acquiring lock: {e}")
    
    def _acquire_s3_lock(self, lock_name: str, timeout: int) -> bool:
        """Acquire lock using S3 conditional writes."""
        start_time = time.time()
        lock_key = self._key(f".locks/{lock_name}.lock")
        
        while True:
            try:
                # Try to create lock file only if it doesn't exist
                lock_data = f"{self._lock_id}:{int(time.time())}".encode()
                
                # Check if lock exists and is not stale (> 5 minutes old)
                try:
                    response = self.s3.get_object(Bucket=self.bucket, Key=lock_key)
                    existing = response['Body'].read().decode()
                    _, ts = existing.split(':')
                    if int(time.time()) - int(ts) < 300:  # Lock is fresh
                        if time.time() - start_time >= timeout:
                            raise LockError(f"Could not acquire lock '{lock_name}' within {timeout}s")
                        time.sleep(0.5)
                        continue
                except ClientError:
                    pass  # Lock doesn't exist
                
                # Create or overwrite stale lock
                self.s3.put_object(Bucket=self.bucket, Key=lock_key, Body=lock_data)
                
                # Verify we own the lock
                time.sleep(0.1)
                response = self.s3.get_object(Bucket=self.bucket, Key=lock_key)
                if response['Body'].read().decode().startswith(self._lock_id):
                    return True
                
                # Someone else got it
                if time.time() - start_time >= timeout:
                    raise LockError(f"Could not acquire lock '{lock_name}' within {timeout}s")
                time.sleep(0.5)
                
            except ClientError as e:
                raise StorageError(f"Error acquiring lock: {e}")
    
    def release_lock(self, lock_name: str) -> None:
        """Release a distributed lock."""
        if self.dynamodb and self.lock_table:
            self._release_dynamodb_lock(lock_name)
        else:
            self._release_s3_lock(lock_name)
    
    def _release_dynamodb_lock(self, lock_name: str) -> None:
        """Release DynamoDB lock."""
        lock_key = f"{self.prefix}/{lock_name}" if self.prefix else lock_name
        try:
            self.dynamodb.delete_item(
                TableName=self.lock_table,
                Key={'LockKey': {'S': lock_key}},
                ConditionExpression='LockId = :id',
                ExpressionAttributeValues={':id': {'S': self._lock_id}}
            )
        except ClientError:
            pass  # Lock may have expired or been released
    
    def _release_s3_lock(self, lock_name: str) -> None:
        """Release S3 lock."""
        lock_key = self._key(f".locks/{lock_name}.lock")
        try:
            # Only delete if we own the lock
            response = self.s3.get_object(Bucket=self.bucket, Key=lock_key)
            if response['Body'].read().decode().startswith(self._lock_id):
                self.s3.delete_object(Bucket=self.bucket, Key=lock_key)
        except ClientError:
            pass
    
    def is_locked(self, lock_name: str) -> bool:
        """Check if a lock is currently held."""
        if self.dynamodb and self.lock_table:
            lock_key = f"{self.prefix}/{lock_name}" if self.prefix else lock_name
            try:
                response = self.dynamodb.get_item(
                    TableName=self.lock_table,
                    Key={'LockKey': {'S': lock_key}}
                )
                return 'Item' in response
            except ClientError:
                return False
        else:
            lock_key = self._key(f".locks/{lock_name}.lock")
            try:
                response = self.s3.get_object(Bucket=self.bucket, Key=lock_key)
                existing = response['Body'].read().decode()
                _, ts = existing.split(':')
                # Lock is valid if less than 5 minutes old
                return int(time.time()) - int(ts) < 300
            except ClientError:
                return False
