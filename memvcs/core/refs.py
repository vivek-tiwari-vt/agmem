"""
Reference management for agmem.

Manages HEAD, branches, tags, stash, and reflog.
"""

import os
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime

# Minimum length for partial commit hash; full SHA-256 hex is 64 chars
COMMIT_HASH_MIN_LEN = 4
COMMIT_HASH_MAX_LEN = 64
COMMIT_HASH_HEX_CHARS = set('0123456789abcdef')


def _safe_ref_name(name: str) -> bool:
    """Return True if name is safe for single-component ref (reflog, HEAD file). No slashes."""
    if not name or name in ('.', '..'):
        return False
    if '/' in name or '\\' in name or '\0' in name:
        return False
    return True


def _ref_path_under_root(name: str, base_dir: Path) -> bool:
    """Return True if name is a valid ref name and (base_dir / name) stays under base_dir (Git-style)."""
    if not name or name in ('.', '..') or '\0' in name or '\\' in name:
        return False
    try:
        resolved = (base_dir / name).resolve()
        base_resolved = base_dir.resolve()
        return resolved == base_resolved or base_resolved in resolved.parents
    except (ValueError, RuntimeError):
        return False


def _valid_commit_hash(candidate: str) -> bool:
    """Return True if candidate looks like a commit hash (hex, within length)."""
    if not candidate or len(candidate) < COMMIT_HASH_MIN_LEN or len(candidate) > COMMIT_HASH_MAX_LEN:
        return False
    return all(c in COMMIT_HASH_HEX_CHARS for c in candidate.lower())


class RefsManager:
    """Manages references (HEAD, branches, tags)."""
    
    def __init__(self, mem_dir: Path):
        self.mem_dir = Path(mem_dir)
        self.refs_dir = self.mem_dir / 'refs'
        self.heads_dir = self.refs_dir / 'heads'
        self.tags_dir = self.refs_dir / 'tags'
        self.remotes_dir = self.refs_dir / 'remotes'
        self.head_file = self.mem_dir / 'HEAD'
        self.stash_file = self.mem_dir / 'stash'
        self.reflog_dir = self.mem_dir / 'logs'
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Create reference directories."""
        self.heads_dir.mkdir(parents=True, exist_ok=True)
        self.tags_dir.mkdir(parents=True, exist_ok=True)
        self.remotes_dir.mkdir(parents=True, exist_ok=True)
    
    def init_head(self, branch_name: str = 'main'):
        """Initialize HEAD to point to a branch."""
        if not _ref_path_under_root(branch_name, self.heads_dir):
            raise ValueError(f"Invalid branch name: {branch_name!r}")
        self.head_file.write_text(f'ref: refs/heads/{branch_name}\n')
        branch_file = self.heads_dir / branch_name
        if not branch_file.exists():
            branch_file.parent.mkdir(parents=True, exist_ok=True)
            branch_file.write_text('')
    
    def get_head(self) -> Dict[str, str]:
        """
        Get current HEAD reference.
        
        Returns:
            Dict with 'type' ('branch' or 'commit') and 'value'
        """
        if not self.head_file.exists():
            return {'type': 'branch', 'value': 'main'}
        
        content = self.head_file.read_text().strip()
        
        if content.startswith('ref: '):
            # Points to a branch (e.g. refs/heads/main or refs/heads/feature/test)
            ref_path = content[5:].strip()
            branch_name = ref_path[len('refs/heads/'):] if ref_path.startswith('refs/heads/') else ref_path.split('/')[-1]
            return {'type': 'branch', 'value': branch_name}
        elif content:
            # Detached HEAD - points directly to commit
            return {'type': 'commit', 'value': content}
        
        return {'type': 'branch', 'value': 'main'}
    
    def set_head_branch(self, branch_name: str):
        """Set HEAD to point to a branch."""
        if not _ref_path_under_root(branch_name, self.heads_dir):
            raise ValueError(f"Invalid branch name: {branch_name!r}")
        self.head_file.write_text(f'ref: refs/heads/{branch_name}\n')
    
    def set_head_detached(self, commit_hash: str):
        """Set HEAD to point directly to a commit (detached)."""
        self.head_file.write_text(f'{commit_hash}\n')
    
    def get_branch_commit(self, branch_name: str) -> Optional[str]:
        """Get the commit hash for a branch."""
        if not _ref_path_under_root(branch_name, self.heads_dir):
            return None
        branch_file = self.heads_dir / branch_name
        if branch_file.exists():
            content = branch_file.read_text().strip()
            return content if content else None
        return None
    
    def set_branch_commit(self, branch_name: str, commit_hash: str):
        """Set the commit hash for a branch."""
        if not _ref_path_under_root(branch_name, self.heads_dir):
            raise ValueError(f"Invalid branch name: {branch_name!r}")
        branch_file = self.heads_dir / branch_name
        branch_file.parent.mkdir(parents=True, exist_ok=True)
        branch_file.write_text(f'{commit_hash}\n')
    
    def create_branch(self, branch_name: str, commit_hash: Optional[str] = None) -> bool:
        """
        Create a new branch.
        
        Args:
            branch_name: Name of the new branch
            commit_hash: Commit to point to (None for current HEAD)
            
        Returns:
            True if created, False if branch already exists
        """
        if not _ref_path_under_root(branch_name, self.heads_dir):
            raise ValueError(f"Invalid branch name: {branch_name!r}")
        branch_file = self.heads_dir / branch_name
        if branch_file.exists():
            return False

        branch_file.parent.mkdir(parents=True, exist_ok=True)

        if commit_hash is None:
            # Point to current HEAD commit
            head = self.get_head()
            if head['type'] == 'branch':
                commit_hash = self.get_branch_commit(head['value'])
            else:
                commit_hash = head['value']
        
        branch_file.write_text(f'{commit_hash}\n' if commit_hash else '')
        return True
    
    def delete_branch(self, branch_name: str) -> bool:
        """
        Delete a branch.
        
        Returns:
            True if deleted, False if branch doesn't exist
        """
        if not _ref_path_under_root(branch_name, self.heads_dir):
            return False
        branch_file = self.heads_dir / branch_name
        if branch_file.exists():
            branch_file.unlink()
            return True
        return False
    
    def list_branches(self) -> List[str]:
        """List all branch names (supports nested names like feature/test)."""
        if not self.heads_dir.exists():
            return []
        branches = []
        for p in self.heads_dir.rglob('*'):
            if p.is_file():
                branches.append(str(p.relative_to(self.heads_dir)))
        return sorted(branches)
    
    def branch_exists(self, branch_name: str) -> bool:
        """Check if a branch exists."""
        if not _ref_path_under_root(branch_name, self.heads_dir):
            return False
        return (self.heads_dir / branch_name).exists()
    
    def get_current_branch(self) -> Optional[str]:
        """Get the name of the current branch, or None if detached."""
        head = self.get_head()
        if head['type'] == 'branch':
            return head['value']
        return None
    
    def is_detached(self) -> bool:
        """Check if HEAD is detached."""
        head = self.get_head()
        return head['type'] == 'commit'
    
    # Tag management
    
    def create_tag(self, tag_name: str, commit_hash: str, message: str = '') -> bool:
        """
        Create a new tag.
        
        Args:
            tag_name: Name of the tag
            commit_hash: Commit to tag
            message: Optional tag message
            
        Returns:
            True if created, False if tag already exists
        """
        if not _ref_path_under_root(tag_name, self.tags_dir):
            raise ValueError(f"Invalid tag name: {tag_name!r}")
        tag_file = self.tags_dir / tag_name
        if tag_file.exists():
            return False

        tag_file.parent.mkdir(parents=True, exist_ok=True)
        tag_file.write_text(f'{commit_hash}\n')
        return True
    
    def delete_tag(self, tag_name: str) -> bool:
        """
        Delete a tag.
        
        Returns:
            True if deleted, False if tag doesn't exist
        """
        if not _ref_path_under_root(tag_name, self.tags_dir):
            return False
        tag_file = self.tags_dir / tag_name
        if tag_file.exists():
            tag_file.unlink()
            return True
        return False
    
    def get_tag_commit(self, tag_name: str) -> Optional[str]:
        """Get the commit hash for a tag."""
        if not _ref_path_under_root(tag_name, self.tags_dir):
            return None
        tag_file = self.tags_dir / tag_name
        if tag_file.exists():
            return tag_file.read_text().strip()
        return None
    
    def list_tags(self) -> List[str]:
        """List all tag names (supports nested names)."""
        if not self.tags_dir.exists():
            return []
        tags = []
        for p in self.tags_dir.rglob('*'):
            if p.is_file():
                tags.append(str(p.relative_to(self.tags_dir)))
        return sorted(tags)
    
    def tag_exists(self, tag_name: str) -> bool:
        """Check if a tag exists."""
        if not _ref_path_under_root(tag_name, self.tags_dir):
            return False
        return (self.tags_dir / tag_name).exists()

    def get_remote_branch_commit(self, remote_name: str, branch_name: str) -> Optional[str]:
        """Get commit hash for a remote-tracking branch (e.g. refs/remotes/origin/main)."""
        if not _safe_ref_name(remote_name) or not _ref_path_under_root(branch_name, self.heads_dir):
            return None
        remote_refs = self.remotes_dir / remote_name
        ref_file = remote_refs / branch_name
        if ref_file.exists() and ref_file.is_file():
            content = ref_file.read_text().strip()
            return content if content else None
        return None

    def set_remote_branch_commit(self, remote_name: str, branch_name: str, commit_hash: str) -> None:
        """Set remote-tracking branch (e.g. after fetch)."""
        if not _safe_ref_name(remote_name):
            raise ValueError(f"Invalid remote name: {remote_name!r}")
        remote_refs = self.remotes_dir / remote_name
        if not _ref_path_under_root(branch_name, remote_refs):
            raise ValueError(f"Invalid branch name: {branch_name!r}")
        ref_file = self.remotes_dir / remote_name / branch_name
        ref_file.parent.mkdir(parents=True, exist_ok=True)
        ref_file.write_text(commit_hash + '\n')
    
    def resolve_ref(self, ref: str, object_store=None) -> Optional[str]:
        """
        Resolve a reference to a commit hash.
        
        Supports:
        - Branch names
        - Tag names
        - Partial commit hashes
        - HEAD
        - HEAD~n (nth parent)
        
        Args:
            ref: Reference to resolve
            
        Returns:
            Commit hash or None if not found
        """
        ref = ref.strip()
        
        # Handle HEAD
        if ref == 'HEAD':
            head = self.get_head()
            if head['type'] == 'commit':
                return head['value']
            else:
                return self.get_branch_commit(head['value'])
        
        # Handle HEAD~n
        if ref.startswith('HEAD~'):
            try:
                n = int(ref[5:])
                if n < 0:
                    return None
                head = self.get_head()
                if head['type'] == 'branch':
                    commit_hash = self.get_branch_commit(head['value'])
                else:
                    commit_hash = head['value']
                if not commit_hash:
                    return None
                # Walk back n parents when object_store is available
                if object_store is not None and n > 0:
                    from .objects import Commit
                    for _ in range(n):
                        commit = Commit.load(object_store, commit_hash)
                        if not commit or not commit.parents:
                            return None
                        commit_hash = commit.parents[0]
                return commit_hash
            except ValueError:
                return None
        
        # Check branches
        if self.branch_exists(ref):
            return self.get_branch_commit(ref)

        # Check remote-tracking refs (e.g. origin/main)
        if '/' in ref:
            parts = ref.split('/', 1)
            if len(parts) == 2:
                remote_name, branch_name = parts
                if _safe_ref_name(remote_name) and _ref_path_under_root(branch_name, self.heads_dir):
                    remote_hash = self.get_remote_branch_commit(remote_name, branch_name)
                    if remote_hash:
                        return remote_hash
        
        # Check tags
        if self.tag_exists(ref):
            return self.get_tag_commit(ref)
        
        # Check stash refs (stash@{n})
        if ref.startswith('stash@'):
            if ref == 'stash':
                return self.get_stash_commit(0)
            if ref.startswith('stash@{') and ref.endswith('}'):
                try:
                    n = int(ref[7:-1])
                    return self.get_stash_commit(n)
                except ValueError:
                    pass
        
        # Assume it's a commit hash (full or partial); validate to avoid path/injection
        return ref if _valid_commit_hash(ref) else None
    
    # Reflog - log of HEAD changes
    def append_reflog(self, ref_name: str, old_hash: str, new_hash: str, message: str):
        """Append entry to reflog."""
        if not _safe_ref_name(ref_name):
            raise ValueError(f"Invalid ref name for reflog: {ref_name!r}")
        self.reflog_dir.mkdir(parents=True, exist_ok=True)
        log_file = self.reflog_dir / ref_name
        timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        line = f"{new_hash} {old_hash} {timestamp} {message}\n"
        with open(log_file, 'a') as f:
            f.write(line)
    
    def get_reflog(self, ref_name: str = 'HEAD', max_count: int = 20) -> List[Dict]:
        """Get reflog entries for a reference."""
        if not _safe_ref_name(ref_name):
            return []
        log_file = self.reflog_dir / ref_name
        if not log_file.exists():
            return []
        entries = []
        for line in reversed(log_file.read_text().strip().split('\n')):
            if not line:
                continue
            parts = line.split(' ', 3)
            if len(parts) >= 4:
                entries.append({
                    'hash': parts[0],
                    'old_hash': parts[1],
                    'timestamp': parts[2],
                    'message': parts[3]
                })
            if len(entries) >= max_count:
                break
        return entries
    
    # Stash - stack of stashed changes
    def stash_push(self, commit_hash: str, message: str = '') -> int:
        """Push a commit onto the stash stack. Returns stash index."""
        stashes = self._load_stash_list()
        stashes.insert(0, {'hash': commit_hash, 'message': message or 'WIP'})
        self._save_stash_list(stashes)
        return 0
    
    def stash_pop(self, index: int = 0) -> Optional[str]:
        """Pop stash at index. Returns commit hash or None."""
        stashes = self._load_stash_list()
        if index >= len(stashes):
            return None
        entry = stashes.pop(index)
        self._save_stash_list(stashes)
        return entry['hash']
    
    def stash_list(self) -> List[Dict]:
        """List all stashes."""
        return self._load_stash_list()
    
    def get_stash_commit(self, index: int) -> Optional[str]:
        """Get commit hash for stash at index."""
        stashes = self._load_stash_list()
        if 0 <= index < len(stashes):
            return stashes[index]['hash']
        return None
    
    def _load_stash_list(self) -> List[Dict]:
        """Load stash list from disk."""
        if not self.stash_file.exists():
            return []
        try:
            import json
            data = json.loads(self.stash_file.read_text())
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    
    def _save_stash_list(self, stashes: List[Dict]):
        """Save stash list to disk."""
        import json
        self.stash_file.write_text(json.dumps(stashes, indent=2))
