"""
Staging area for agmem.

Manages the index of files staged for commit.
"""

import json
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, asdict


@dataclass
class StagedFile:
    """Represents a file in the staging area."""
    path: str  # Relative path from current/
    blob_hash: str
    mode: int = 0o100644  # Regular file


def _path_under_root(relative_path: str, root: Path) -> Optional[Path]:
    """
    Resolve relative_path under root and ensure it stays inside root.
    Returns the resolved Path or None if path escapes root (path traversal).
    """
    try:
        resolved = (root / relative_path).resolve()
        resolved.relative_to(root.resolve())
        return resolved
    except ValueError:
        return None


class StagingArea:
    """Manages the staging area for memory commits."""
    
    def __init__(self, mem_dir: Path):
        self.mem_dir = Path(mem_dir)
        self.staging_dir = self.mem_dir / 'staging'
        self.index_file = self.mem_dir / 'index.json'
        self._index: Dict[str, StagedFile] = {}
        self._load_index()
    
    def _load_index(self):
        """Load the staging index from disk."""
        if self.index_file.exists():
            try:
                data = json.loads(self.index_file.read_text())
                for path, info in data.items():
                    if _path_under_root(path, self.staging_dir) is None:
                        continue
                    self._index[path] = StagedFile(
                        path=path,
                        blob_hash=info['blob_hash'],
                        mode=info.get('mode', 0o100644)
                    )
            except (json.JSONDecodeError, KeyError):
                self._index = {}
    
    def _save_index(self):
        """Save the staging index to disk."""
        data = {
            path: {
                'blob_hash': sf.blob_hash,
                'mode': sf.mode
            }
            for path, sf in self._index.items()
        }
        self.index_file.write_text(json.dumps(data, indent=2))
    
    def add(self, filepath: str, blob_hash: str, content: bytes, mode: int = 0o100644):
        """
        Add a file to the staging area.
        
        Args:
            filepath: Relative path from current/
            blob_hash: Hash of the blob object
            content: File content bytes
            mode: File mode (default 0o100644 for regular file)
            
        Raises:
            ValueError: If filepath escapes staging directory (path traversal)
        """
        staging_path = _path_under_root(filepath, self.staging_dir)
        if staging_path is None:
            raise ValueError(f"Path escapes staging area: {filepath}")
        
        self._index[filepath] = StagedFile(
            path=filepath,
            blob_hash=blob_hash,
            mode=mode
        )
        
        staging_path.parent.mkdir(parents=True, exist_ok=True)
        staging_path.write_bytes(content)
        
        self._save_index()
    
    def remove(self, filepath: str) -> bool:
        """
        Remove a file from the staging area.
        
        Returns:
            True if file was in staging, False otherwise
        """
        if filepath in self._index:
            del self._index[filepath]
            
            staging_path = _path_under_root(filepath, self.staging_dir)
            if staging_path is not None and staging_path.exists():
                staging_path.unlink()
                # Clean up empty directories
                self._cleanup_empty_dirs(staging_path.parent)
            
            self._save_index()
            return True
        return False
    
    def _cleanup_empty_dirs(self, dir_path: Path):
        """Remove empty directories up to staging root."""
        try:
            while dir_path != self.staging_dir:
                if dir_path.exists() and not any(dir_path.iterdir()):
                    dir_path.rmdir()
                    dir_path = dir_path.parent
                else:
                    break
        except OSError:
            pass
    
    def get_staged_files(self) -> Dict[str, StagedFile]:
        """Get all staged files."""
        return dict(self._index)
    
    def is_staged(self, filepath: str) -> bool:
        """Check if a file is staged."""
        return filepath in self._index
    
    def get_blob_hash(self, filepath: str) -> Optional[str]:
        """Get the blob hash for a staged file."""
        if filepath in self._index:
            return self._index[filepath].blob_hash
        return None
    
    def clear(self):
        """Clear the entire staging area."""
        self._index = {}
        
        # Remove staging directory contents
        if self.staging_dir.exists():
            shutil.rmtree(self.staging_dir)
            self.staging_dir.mkdir(parents=True, exist_ok=True)
        
        # Remove index file
        if self.index_file.exists():
            self.index_file.unlink()
    
    def get_status(self) -> Dict[str, List[str]]:
        """
        Get staging status.
        
        Returns:
            Dict with 'staged', 'modified', 'deleted', 'untracked' lists
        """
        staged = list(self._index.keys())
        
        return {
            'staged': staged,
            'modified': [],  # TODO: Compare with working directory
            'deleted': [],   # TODO: Check if files were deleted
            'untracked': []  # TODO: Find untracked files
        }
    
    def get_tree_entries(self) -> List[Dict]:
        """
        Get tree entries for creating a tree object.
        
        Returns:
            List of entry dictionaries for Tree creation
        """
        entries = []
        for path, sf in self._index.items():
            entries.append({
                'mode': oct(sf.mode)[2:],  # Convert to string like '100644'
                'type': 'blob',
                'hash': sf.blob_hash,
                'name': Path(path).name,
                'path': str(Path(path).parent) if str(Path(path).parent) != '.' else ''
            })
        return entries
    
    def diff_with_head(self, repo) -> Dict[str, Dict]:
        """
        Compare staging area with HEAD commit.
        
        Returns:
            Dict mapping file paths to change info
        """
        changes = {}
        
        # Get HEAD tree
        head_commit = repo.get_head_commit()
        if head_commit:
            head_tree_bytes = repo.object_store.retrieve(head_commit.tree, 'tree')
            if head_tree_bytes:
                head_data = json.loads(head_tree_bytes.decode('utf-8'))
                head_entries = {e['path'] + '/' + e['name'] if e['path'] else e['name']: e 
                               for e in head_data.get('entries', [])}
        else:
            head_entries = {}
        
        # Compare with staging
        for path, sf in self._index.items():
            if path in head_entries:
                if head_entries[path]['hash'] != sf.blob_hash:
                    changes[path] = {'status': 'modified', 'blob_hash': sf.blob_hash}
            else:
                changes[path] = {'status': 'added', 'blob_hash': sf.blob_hash}
        
        # Check for deleted files
        for path in head_entries:
            if path not in self._index:
                changes[path] = {'status': 'deleted'}
        
        return changes
