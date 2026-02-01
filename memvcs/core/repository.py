"""
Main repository class for agmem.

Coordinates object storage, staging area, and references.
"""

import json
import os
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from .constants import MEMORY_TYPES
from .config_loader import load_agmem_config
from .objects import ObjectStore, Blob, Tree, TreeEntry, Commit
from .staging import StagingArea
from .refs import RefsManager


class Repository:
    """Main repository class coordinating all agmem operations."""

    def __init__(self, path: Path):
        self.root = Path(path).resolve()
        self.mem_dir = self.root / ".mem"
        self.current_dir = self.root / "current"
        self.config_file = self.mem_dir / "config.json"

        self.object_store: Optional[ObjectStore] = None
        self.staging: Optional[StagingArea] = None
        self.refs: Optional[RefsManager] = None

        if self.is_valid_repo():
            self._init_components()

    def _init_components(self):
        """Initialize repository components."""
        self.object_store = ObjectStore(self.mem_dir / "objects")
        self.staging = StagingArea(self.mem_dir)
        self.refs = RefsManager(self.mem_dir)

    @classmethod
    def init(
        cls, path: Path, author_name: str = "Agent", author_email: str = "agent@example.com"
    ) -> "Repository":
        """
        Initialize a new repository.

        Args:
            path: Directory to initialize repository in
            author_name: Default author name
            author_email: Default author email

        Returns:
            Initialized Repository instance
        """
        repo = cls(path)

        if repo.is_valid_repo():
            raise ValueError(f"Repository already exists at {path}")

        # Create directory structure
        repo.mem_dir.mkdir(parents=True, exist_ok=True)
        repo.current_dir.mkdir(parents=True, exist_ok=True)

        for mem_type in MEMORY_TYPES:
            (repo.current_dir / mem_type).mkdir(parents=True, exist_ok=True)

        # Create object store directories
        (repo.mem_dir / "objects").mkdir(parents=True, exist_ok=True)

        # Create staging directory
        (repo.mem_dir / "staging").mkdir(parents=True, exist_ok=True)

        # Create refs directories
        (repo.mem_dir / "refs" / "heads").mkdir(parents=True, exist_ok=True)
        (repo.mem_dir / "refs" / "tags").mkdir(parents=True, exist_ok=True)

        # Create config
        config = {
            "author": {"name": author_name, "email": author_email},
            "core": {"default_branch": "main", "compression": True, "gc_prune_days": 90},
            "memory": {
                "auto_summarize": True,
                "summarizer_model": "default",
                "max_episode_size": 1024 * 1024,  # 1MB
                "consolidation_threshold": 100,  # Episodes before consolidation
            },
        }
        repo.config_file.write_text(json.dumps(config, indent=2))

        # Initialize components
        repo._init_components()

        # Initialize HEAD
        repo.refs.init_head("main")

        return repo

    def is_valid_repo(self) -> bool:
        """Check if this is a valid repository."""
        return (
            self.mem_dir.exists()
            and self.config_file.exists()
            and (self.mem_dir / "objects").exists()
        )

    def get_config(self) -> Dict[str, Any]:
        """Get repository configuration."""
        if self.config_file.exists():
            return json.loads(self.config_file.read_text())
        return {}

    def set_config(self, config: Dict[str, Any]):
        """Set repository configuration."""
        self.config_file.write_text(json.dumps(config, indent=2))

    def get_author(self) -> str:
        """Get the configured author string."""
        config = self.get_config()
        author = config.get("author", {})
        name = author.get("name", "Agent")
        email = author.get("email", "agent@example.com")
        return f"{name} <{email}>"

    def get_agmem_config(self) -> Dict[str, Any]:
        """Get merged agmem config (user + repo). Use for cloud and PII settings."""
        return load_agmem_config(self.root)

    def get_head_commit(self) -> Optional[Commit]:
        """Get the current HEAD commit object."""
        if not self.refs:
            return None

        head = self.refs.get_head()
        if head["type"] == "branch":
            commit_hash = self.refs.get_branch_commit(head["value"])
        else:
            commit_hash = head["value"]

        if commit_hash:
            return Commit.load(self.object_store, commit_hash)
        return None

    def get_commit_tree(self, commit_hash: str) -> Optional[Tree]:
        """Get the tree for a specific commit."""
        commit = Commit.load(self.object_store, commit_hash)
        if commit:
            return Tree.load(self.object_store, commit.tree)
        return None

    def resolve_ref(self, ref: str) -> Optional[str]:
        """Resolve a reference (branch, tag, HEAD, HEAD~n, commit hash, or ISO date) to a commit hash."""
        if not self.refs:
            return None
        resolved = self.refs.resolve_ref(ref, self.object_store)
        if resolved:
            return resolved
        # Try temporal resolution for ISO date strings
        if ref and (ref[0].isdigit() or ref.startswith("202")):
            try:
                from .temporal_index import TemporalIndex

                ti = TemporalIndex(self.mem_dir, self.object_store)
                return ti.resolve_at(ref)
            except Exception:
                pass
        return None

    def _path_under_current_dir(self, relative_path: str) -> Optional[Path]:
        """Resolve path under current/; return None if it escapes (path traversal)."""
        try:
            resolved = (self.current_dir / relative_path).resolve()
            resolved.relative_to(self.current_dir.resolve())
            return resolved
        except ValueError:
            return None

    def stage_file(self, filepath: str, content: Optional[bytes] = None) -> str:
        """
        Stage a file for commit.

        Args:
            filepath: Path relative to current/ directory
            content: File content (if None, reads from current/)

        Returns:
            Blob hash of staged content

        Raises:
            FileNotFoundError: If file does not exist
            ValueError: If filepath escapes current/ (path traversal)
        """
        if content is None:
            full_path = self._path_under_current_dir(filepath)
            if full_path is None:
                raise ValueError(f"Path escapes current directory: {filepath}")
            if not full_path.exists():
                raise FileNotFoundError(f"File not found: {filepath}")
            content = full_path.read_bytes()

        # Store as blob
        blob = Blob(content=content)
        blob_hash = blob.store(self.object_store)

        # Add to staging area
        self.staging.add(filepath, blob_hash, content)

        return blob_hash

    def _build_tree_from_staged(self) -> str:
        """Build and store tree from staged files. Returns tree hash."""
        staged_files = self.staging.get_staged_files()
        entries = []
        for path, sf in staged_files.items():
            path_obj = Path(path)
            entries.append(
                TreeEntry(
                    mode=oct(sf.mode)[2:],
                    obj_type="blob",
                    hash=sf.blob_hash,
                    name=path_obj.name,
                    path=str(path_obj.parent) if str(path_obj.parent) != "." else "",
                )
            )
        tree = Tree(entries=entries)
        return tree.store(self.object_store)

    def _restore_tree_to_current_dir(self, tree: Tree) -> None:
        """Clear current dir and restore files from tree."""
        for item in self.current_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        for mem_type in MEMORY_TYPES:
            (self.current_dir / mem_type).mkdir(exist_ok=True)
        current_resolved = self.current_dir.resolve()
        for entry in tree.entries:
            # Prevent path traversal: ensure entry path stays under current/
            try:
                filepath = (self.current_dir / entry.path / entry.name).resolve()
                filepath.relative_to(current_resolved)
            except (ValueError, RuntimeError):
                continue
            blob = Blob.load(self.object_store, entry.hash)
            if blob:
                filepath.parent.mkdir(parents=True, exist_ok=True)
                filepath.write_bytes(blob.content)

    def stage_directory(self, dirpath: str = "") -> Dict[str, str]:
        """
        Stage all files in a directory.

        Args:
            dirpath: Directory path relative to current/ (empty for all)

        Returns:
            Dict mapping file paths to blob hashes
        """
        target_dir = self.current_dir / dirpath if dirpath else self.current_dir
        staged = {}

        for root, dirs, files in os.walk(target_dir):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith(".")]

            for filename in files:
                full_path = Path(root) / filename
                rel_path = full_path.relative_to(self.current_dir)

                content = full_path.read_bytes()
                blob_hash = self.stage_file(str(rel_path), content)
                staged[str(rel_path)] = blob_hash

        return staged

    def commit(self, message: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Create a commit from staged changes.

        Args:
            message: Commit message
            metadata: Additional metadata

        Returns:
            Commit hash
        """
        staged_files = self.staging.get_staged_files()

        if not staged_files:
            raise ValueError("No changes staged for commit")

        tree_hash = self._build_tree_from_staged()

        # Get parent commit
        head_commit = self.get_head_commit()
        parents = [head_commit.store(self.object_store)] if head_commit else []

        # Create commit
        commit = Commit(
            tree=tree_hash,
            parents=parents,
            author=self.get_author(),
            timestamp=datetime.utcnow().isoformat() + "Z",
            message=message,
            metadata=metadata or {},
        )
        commit_hash = commit.store(self.object_store)

        # Reflog: record HEAD change
        old_hash = parents[0] if parents else "0" * 64
        self.refs.append_reflog("HEAD", old_hash, commit_hash, f"commit: {message}")

        # Update HEAD
        head = self.refs.get_head()
        if head["type"] == "branch":
            self.refs.set_branch_commit(head["value"], commit_hash)
        else:
            self.refs.set_head_detached(commit_hash)

        # Clear staging area
        self.staging.clear()

        return commit_hash

    def checkout(self, ref: str, force: bool = False) -> str:
        """
        Checkout a commit or branch.

        Args:
            ref: Branch name, tag name, or commit hash
            force: Whether to discard uncommitted changes

        Returns:
            Commit hash that was checked out
        """
        # Get current HEAD for reflog
        old_head = self.refs.get_head()
        old_hash = None
        if old_head["type"] == "branch":
            old_hash = self.refs.get_branch_commit(old_head["value"])
        else:
            old_hash = old_head.get("value")

        # Resolve reference
        commit_hash = self.resolve_ref(ref)
        if not commit_hash:
            raise ValueError(f"Reference not found: {ref}")

        # Validate that the resolved ref is a valid commit
        tree = self.get_commit_tree(commit_hash)
        if not tree:
            raise ValueError(f"Reference not found: {ref}")

        # Check for uncommitted changes
        if not force:
            staged = self.staging.get_staged_files()
            if staged:
                raise ValueError(
                    "You have uncommitted changes. " "Commit them or use --force to discard."
                )

        self._restore_tree_to_current_dir(tree)

        # Reflog: record HEAD change
        if old_hash and old_hash != commit_hash:
            self.refs.append_reflog("HEAD", old_hash, commit_hash, f"checkout: moving to {ref}")

        # Update HEAD
        if self.refs.branch_exists(ref):
            self.refs.set_head_branch(ref)
        else:
            self.refs.set_head_detached(commit_hash)

        # Clear staging
        self.staging.clear()

        return commit_hash

    def get_status(self) -> Dict[str, Any]:
        """
        Get repository status.

        Returns:
            Status dictionary with staged, modified, untracked files
        """
        staged = self.staging.get_staged_files()

        # Compare current directory with HEAD
        head_commit = self.get_head_commit()
        head_files = {}

        if head_commit:
            tree = Tree.load(self.object_store, head_commit.tree)
            if tree:
                for entry in tree.entries:
                    path = entry.path + "/" + entry.name if entry.path else entry.name
                    head_files[path] = entry.hash

        # Check working directory
        modified = []
        untracked = []

        for root, dirs, files in os.walk(self.current_dir):
            dirs[:] = [d for d in dirs if not d.startswith(".")]

            for filename in files:
                full_path = Path(root) / filename
                rel_path = str(full_path.relative_to(self.current_dir))

                if rel_path not in staged:
                    content = full_path.read_bytes()
                    blob = Blob(content=content)
                    blob_hash = blob.store(self.object_store)

                    if rel_path in head_files:
                        if head_files[rel_path] != blob_hash:
                            modified.append(rel_path)
                    else:
                        untracked.append(rel_path)

        # Check for deleted files
        deleted = []
        for path in head_files:
            full_path = self.current_dir / path
            if not full_path.exists() and path not in staged:
                deleted.append(path)

        return {
            "staged": list(staged.keys()),
            "modified": modified,
            "untracked": untracked,
            "deleted": deleted,
            "head": self.refs.get_head(),
            "branch": self.refs.get_current_branch(),
        }

    def get_log(self, max_count: int = 10) -> List[Dict[str, Any]]:
        """
        Get commit history.

        Args:
            max_count: Maximum number of commits to return

        Returns:
            List of commit info dictionaries
        """
        commits = []
        commit_hash = None

        # Get starting commit
        head = self.refs.get_head()
        if head["type"] == "branch":
            commit_hash = self.refs.get_branch_commit(head["value"])
        else:
            commit_hash = head["value"]

        # Walk back through parents
        while commit_hash and len(commits) < max_count:
            commit = Commit.load(self.object_store, commit_hash)
            if not commit:
                break

            commits.append(
                {
                    "hash": commit_hash,
                    "short_hash": commit_hash[:8],
                    "message": commit.message,
                    "author": commit.author,
                    "timestamp": commit.timestamp,
                    "parents": commit.parents,
                }
            )

            # Follow first parent (linear history for now)
            commit_hash = commit.parents[0] if commit.parents else None

        return commits

    def stash_create(self, message: str = "") -> Optional[str]:
        """
        Stash current changes (staged + modified + untracked) and reset to HEAD.
        Returns stash commit hash or None if nothing to stash.
        """
        status = self.get_status()
        if not status["staged"] and not status["modified"] and not status["untracked"]:
            return None

        # Stage everything
        self.stage_directory()
        staged = self.staging.get_staged_files()
        if not staged:
            return None

        # Create stash commit (parent = HEAD)
        head_commit = self.get_head_commit()
        parents = [head_commit.store(self.object_store)] if head_commit else []

        tree_hash = self._build_tree_from_staged()

        stash_commit = Commit(
            tree=tree_hash,
            parents=parents,
            author=self.get_author(),
            timestamp=datetime.utcnow().isoformat() + "Z",
            message=message or "WIP on " + (self.refs.get_current_branch() or "HEAD"),
            metadata={"stash": True},
        )
        stash_hash = stash_commit.store(self.object_store)

        self.refs.stash_push(stash_hash, message)
        self.staging.clear()

        head_hash = self.resolve_ref("HEAD")
        if head_hash:
            tree = self.get_commit_tree(head_hash)
            if tree:
                self._restore_tree_to_current_dir(tree)

        return stash_hash

    def stash_pop(self, index: int = 0) -> Optional[str]:
        """Apply stash at index and remove from stash list."""
        stash_hash = self.refs.stash_pop(index)
        if not stash_hash:
            return None
        tree = self.get_commit_tree(stash_hash)
        if tree:
            self._restore_tree_to_current_dir(tree)
        return stash_hash
