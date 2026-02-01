"""
Merge functionality for agmem.

Implements memory-type-aware merging strategies with frontmatter support.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum

from .objects import ObjectStore, Commit, Tree, TreeEntry, Blob
from .repository import Repository
from .schema import FrontmatterParser, FrontmatterData, compare_timestamps


class MergeStrategy(Enum):
    """Merge strategies for different memory types."""

    EPISODIC = "episodic"  # Append chronologically
    SEMANTIC = "semantic"  # Smart consolidation with conflict detection
    PROCEDURAL = "procedural"  # Prefer newer, validate compatibility


@dataclass
class Conflict:
    """Represents a merge conflict."""

    path: str
    base_content: Optional[str]
    ours_content: Optional[str]
    theirs_content: Optional[str]
    message: str
    memory_type: Optional[str] = None  # episodic, semantic, procedural
    payload: Optional[Dict[str, Any]] = None  # type-specific (e.g. fact strings, step diffs)


@dataclass
class MergeResult:
    """Result of a merge operation."""

    success: bool
    commit_hash: Optional[str]
    conflicts: List[Conflict]
    message: str


class MergeEngine:
    """Engine for merging memory branches."""

    def __init__(self, repo: Repository):
        self.repo = repo
        self.object_store = repo.object_store

    def detect_memory_type(self, filepath: str) -> MergeStrategy:
        """
        Detect the memory type from file path.

        Args:
            filepath: Path to the file

        Returns:
            MergeStrategy for this file type
        """
        path_lower = filepath.lower()

        if "episodic" in path_lower:
            return MergeStrategy.EPISODIC
        elif "semantic" in path_lower:
            return MergeStrategy.SEMANTIC
        elif "procedural" in path_lower or "workflow" in path_lower:
            return MergeStrategy.PROCEDURAL

        # Default to semantic for unknown types
        return MergeStrategy.SEMANTIC

    def find_common_ancestor(self, commit1: str, commit2: str) -> Optional[str]:
        """
        Find the common ancestor of two commits.

        Args:
            commit1: First commit hash
            commit2: Second commit hash

        Returns:
            Common ancestor commit hash or None
        """
        # Build ancestor chain for commit1
        ancestors1 = set()
        current = commit1

        while current:
            ancestors1.add(current)
            commit = Commit.load(self.object_store, current)
            if not commit or not commit.parents:
                break
            current = commit.parents[0]  # Follow first parent

        # Walk back from commit2 and find first common ancestor
        current = commit2
        while current:
            if current in ancestors1:
                return current

            commit = Commit.load(self.object_store, current)
            if not commit or not commit.parents:
                break
            current = commit.parents[0]

        return None

    def get_tree_files(self, tree_hash: str) -> Dict[str, str]:
        """
        Get all files in a tree.

        Args:
            tree_hash: Hash of tree object

        Returns:
            Dict mapping file paths to blob hashes
        """
        files = {}
        tree = Tree.load(self.object_store, tree_hash)

        if tree:
            for entry in tree.entries:
                path = entry.path + "/" + entry.name if entry.path else entry.name
                files[path] = entry.hash

        return files

    def merge_episodic(
        self,
        base_content: Optional[str],
        ours_content: Optional[str],
        theirs_content: Optional[str],
    ) -> Tuple[str, bool]:
        """
        Merge episodic memory (append chronologically).

        Returns:
            Tuple of (merged_content, had_conflict)
        """
        # Episodic logs are append-only
        parts = []

        if base_content:
            parts.append(base_content)

        # Add ours if different from base
        if ours_content and ours_content != base_content:
            parts.append(ours_content)

        # Add theirs if different from base and ours
        if theirs_content and theirs_content != base_content and theirs_content != ours_content:
            parts.append(theirs_content)

        # Combine with clear separators
        merged = "\n\n---\n\n".join(parts)
        return merged, False  # Episodic never conflicts

    def _get_semantic_merge_config(self) -> Dict[str, Any]:
        """Get merge config for semantic memory."""
        config = self.repo.get_config()
        return config.get("merge", {}).get("semantic", {})

    def merge_semantic(
        self,
        base_content: Optional[str],
        ours_content: Optional[str],
        theirs_content: Optional[str],
    ) -> Tuple[str, bool]:
        """
        Merge semantic memory (smart consolidation).

        Dispatches to strategy from config: recency-wins, confidence-wins,
        append-both, or llm-arbitrate.
        """
        # If ours == theirs, no conflict
        if ours_content == theirs_content:
            return ours_content or "", False

        # If one is same as base, use the other
        if ours_content == base_content:
            return theirs_content or "", False
        if theirs_content == base_content:
            return ours_content or "", False

        cfg = self._get_semantic_merge_config()
        strategy = cfg.get("strategy", "recency-wins")
        threshold = float(cfg.get("auto_resolve_threshold", 0.8))

        if strategy == "recency-wins":
            return self._merge_semantic_recency(ours_content, theirs_content)
        if strategy == "confidence-wins":
            return self._merge_semantic_confidence(ours_content, theirs_content, threshold)
        if strategy == "append-both":
            return self._merge_semantic_append(ours_content, theirs_content)
        if strategy == "llm-arbitrate":
            return self._merge_semantic_llm(ours_content, theirs_content)
        # Default
        return self._merge_semantic_recency(ours_content, theirs_content)

    def _merge_semantic_recency(
        self,
        ours_content: Optional[str],
        theirs_content: Optional[str],
    ) -> Tuple[str, bool]:
        """Recency-wins: newer memory wins, keep older as deprecated."""
        ours_fm, _ = FrontmatterParser.parse(ours_content or "")
        theirs_fm, _ = FrontmatterParser.parse(theirs_content or "")
        if ours_fm and theirs_fm and ours_fm.last_updated and theirs_fm.last_updated:
            c = compare_timestamps(ours_fm.last_updated, theirs_fm.last_updated)
            if c > 0:
                return ours_content or "", False
            if c < 0:
                return theirs_content or "", False
        return ours_content or "", False  # Fallback to ours

    def _merge_semantic_confidence(
        self,
        ours_content: Optional[str],
        theirs_content: Optional[str],
        threshold: float,
    ) -> Tuple[str, bool]:
        """Confidence-wins: user-stated (high confidence) > inferred."""
        ours_fm, _ = FrontmatterParser.parse(ours_content or "")
        theirs_fm, _ = FrontmatterParser.parse(theirs_content or "")
        ours_conf = ours_fm.confidence_score if ours_fm else 0.5
        theirs_conf = theirs_fm.confidence_score if theirs_fm else 0.5
        if ours_conf >= threshold and theirs_conf < threshold:
            return ours_content or "", False
        if theirs_conf >= threshold and ours_conf < threshold:
            return theirs_content or "", False
        if ours_conf >= theirs_conf:
            return ours_content or "", False
        return theirs_content or "", False

    def _merge_semantic_append(
        self,
        ours_content: Optional[str],
        theirs_content: Optional[str],
    ) -> Tuple[str, bool]:
        """Append-both: keep both with validity periods."""
        ours_fm, ours_body = FrontmatterParser.parse(ours_content or "")
        theirs_fm, theirs_body = FrontmatterParser.parse(theirs_content or "")
        parts = []
        if ours_content:
            parts.append(f"<!-- valid_from: ours -->\n{ours_content}")
        if theirs_content and theirs_content != ours_content:
            parts.append(f"<!-- valid_from: theirs -->\n{theirs_content}")
        return "\n\n---\n\n".join(parts) if parts else "", False

    def _merge_semantic_llm(
        self,
        ours_content: Optional[str],
        theirs_content: Optional[str],
    ) -> Tuple[str, bool]:
        """LLM arbitration: call LLM to resolve contradiction (multi-provider)."""
        try:
            from .llm import get_provider
            provider = get_provider()
            if provider:
                merged = provider.complete(
                    [
                        {"role": "system", "content": "Resolve the contradiction between two memory versions. Output the merged content that best reflects the combined truth."},
                        {"role": "user", "content": f"OURS:\n{ours_content}\n\nTHEIRS:\n{theirs_content}"},
                    ],
                    max_tokens=1000,
                )
                return (merged or "").strip(), False
        except Exception:
            pass
        # Fallback to conflict markers
        merged = f"<<<<<<< OURS\n{ours_content}\n=======\n{theirs_content}\n>>>>>>> THEIRS"
        return merged, True

    def merge_procedural(
        self,
        base_content: Optional[str],
        ours_content: Optional[str],
        theirs_content: Optional[str],
    ) -> Tuple[str, bool]:
        """
        Merge procedural memory (prefer newer, validate).

        Uses frontmatter timestamps to determine which version is newer.
        Procedural memory is more likely to auto-resolve using Last-Write-Wins
        since workflows typically should be replaced, not merged.

        Returns:
            Tuple of (merged_content, had_conflict)
        """
        # If ours == theirs, no conflict
        if ours_content == theirs_content:
            return ours_content or "", False

        # If one is same as base, use the other
        if ours_content == base_content:
            return theirs_content or "", False
        if theirs_content == base_content:
            return ours_content or "", False

        # Both changed - try to use frontmatter timestamps
        ours_fm, _ = FrontmatterParser.parse(ours_content or "")
        theirs_fm, _ = FrontmatterParser.parse(theirs_content or "")

        # Use timestamps if available
        if ours_fm and theirs_fm and ours_fm.last_updated and theirs_fm.last_updated:
            comparison = compare_timestamps(ours_fm.last_updated, theirs_fm.last_updated)

            if comparison > 0:
                # Ours is newer - keep it
                return ours_content or "", False
            elif comparison < 0:
                # Theirs is newer - use it
                return theirs_content or "", False
            # Equal timestamps - fall through to conflict

        # No timestamps or equal - flag for manual review
        merged = f"""<<<<<<< OURS (Current)
{ours_content}
=======
{theirs_content}
>>>>>>> THEIRS (Incoming)
"""
        return merged, True

    def merge_files(
        self, base_files: Dict[str, str], ours_files: Dict[str, str], theirs_files: Dict[str, str]
    ) -> Tuple[Dict[str, str], List[Conflict]]:
        """
        Merge file sets from three trees.

        Returns:
            Tuple of (merged_files, conflicts)
        """
        merged = {}
        conflicts = []

        # Get all unique file paths
        all_paths = set(base_files.keys()) | set(ours_files.keys()) | set(theirs_files.keys())

        for path in all_paths:
            base_hash = base_files.get(path)
            ours_hash = ours_files.get(path)
            theirs_hash = theirs_files.get(path)

            # Get content
            base_content = None
            ours_content = None
            theirs_content = None

            if base_hash:
                blob = Blob.load(self.object_store, base_hash)
                if blob:
                    base_content = blob.content.decode("utf-8", errors="replace")

            if ours_hash:
                blob = Blob.load(self.object_store, ours_hash)
                if blob:
                    ours_content = blob.content.decode("utf-8", errors="replace")

            if theirs_hash:
                blob = Blob.load(self.object_store, theirs_hash)
                if blob:
                    theirs_content = blob.content.decode("utf-8", errors="replace")

            # Determine merge strategy
            strategy = self.detect_memory_type(path)

            # Apply merge
            if strategy == MergeStrategy.EPISODIC:
                merged_content, had_conflict = self.merge_episodic(
                    base_content, ours_content, theirs_content
                )
            elif strategy == MergeStrategy.PROCEDURAL:
                merged_content, had_conflict = self.merge_procedural(
                    base_content, ours_content, theirs_content
                )
            else:  # SEMANTIC
                merged_content, had_conflict = self.merge_semantic(
                    base_content, ours_content, theirs_content
                )

            # Store merged content
            if merged_content is not None:
                blob = Blob(content=merged_content.encode("utf-8"))
                merged_hash = blob.store(self.object_store)
                merged[path] = merged_hash

            # Record conflict if any
            if had_conflict:
                payload = {}
                if ours_content:
                    payload["ours_preview"] = ours_content[:300] if len(ours_content) > 300 else ours_content
                if theirs_content:
                    payload["theirs_preview"] = theirs_content[:300] if len(theirs_content) > 300 else theirs_content
                conflicts.append(
                    Conflict(
                        path=path,
                        base_content=base_content,
                        ours_content=ours_content,
                        theirs_content=theirs_content,
                        message=f"{strategy.value} merge conflict in {path}",
                        memory_type=strategy.value,
                        payload=payload or None,
                    )
                )

        return merged, conflicts

    def merge(
        self, source_branch: str, target_branch: Optional[str] = None, message: Optional[str] = None
    ) -> MergeResult:
        """
        Merge source branch into target branch (or current branch).

        Args:
            source_branch: Branch to merge from
            target_branch: Branch to merge into (None for current)
            message: Merge commit message

        Returns:
            MergeResult with success status and conflicts
        """
        # Resolve branches
        source_commit_hash = self.repo.resolve_ref(source_branch)
        if not source_commit_hash:
            return MergeResult(
                success=False,
                commit_hash=None,
                conflicts=[],
                message=f"Source branch not found: {source_branch}",
            )

        if target_branch:
            target_commit_hash = self.repo.resolve_ref(target_branch)
            if not target_commit_hash:
                return MergeResult(
                    success=False,
                    commit_hash=None,
                    conflicts=[],
                    message=f"Target branch not found: {target_branch}",
                )
        else:
            head = self.repo.refs.get_head()
            if head["type"] == "branch":
                target_commit_hash = self.repo.refs.get_branch_commit(head["value"])
            else:
                target_commit_hash = head["value"]

        # Find common ancestor
        ancestor_hash = self.find_common_ancestor(source_commit_hash, target_commit_hash)

        if ancestor_hash == source_commit_hash:
            # Already up to date
            return MergeResult(
                success=True,
                commit_hash=target_commit_hash,
                conflicts=[],
                message="Already up to date",
            )

        if ancestor_hash == target_commit_hash:
            # Fast-forward
            if not target_branch:
                target_branch = self.repo.refs.get_current_branch()

            self.repo.refs.set_branch_commit(target_branch, source_commit_hash)

            return MergeResult(
                success=True,
                commit_hash=source_commit_hash,
                conflicts=[],
                message=f"Fast-forward to {source_branch}",
            )

        # Three-way merge
        # Get trees
        ancestor_commit = Commit.load(self.object_store, ancestor_hash)
        ours_commit = Commit.load(self.object_store, target_commit_hash)
        theirs_commit = Commit.load(self.object_store, source_commit_hash)

        base_files = self.get_tree_files(ancestor_commit.tree)
        ours_files = self.get_tree_files(ours_commit.tree)
        theirs_files = self.get_tree_files(theirs_commit.tree)

        # Merge files
        merged_files, conflicts = self.merge_files(base_files, ours_files, theirs_files)

        if conflicts:
            # Stage merged files for manual resolution
            for path, hash_id in merged_files.items():
                content = Blob.load(self.object_store, hash_id).content
                self.repo.staging.add(path, hash_id, content)

            return MergeResult(
                success=False,
                commit_hash=None,
                conflicts=conflicts,
                message=f"Merge conflict in {len(conflicts)} file(s). Resolve conflicts and commit.",
            )

        # Create merge commit
        # Build tree from merged files
        entries = []
        for path, hash_id in merged_files.items():
            path_obj = Path(path)
            entries.append(
                TreeEntry(
                    mode="100644",
                    obj_type="blob",
                    hash=hash_id,
                    name=path_obj.name,
                    path=str(path_obj.parent) if str(path_obj.parent) != "." else "",
                )
            )

        tree = Tree(entries=entries)
        tree_hash = tree.store(self.object_store)

        merge_message = message or f"Merge branch '{source_branch}'"

        merge_commit = Commit(
            tree=tree_hash,
            parents=[target_commit_hash, source_commit_hash],
            author=self.repo.get_author(),
            timestamp=datetime.utcnow().isoformat() + "Z",
            message=merge_message,
            metadata={"merge": True, "source_branch": source_branch},
        )

        merge_hash = merge_commit.store(self.object_store)

        # Update target branch
        if not target_branch:
            target_branch = self.repo.refs.get_current_branch()

        if target_branch:
            self.repo.refs.set_branch_commit(target_branch, merge_hash)
        else:
            # Detached HEAD
            self.repo.refs.set_head_detached(merge_hash)

        return MergeResult(
            success=True,
            commit_hash=merge_hash,
            conflicts=[],
            message=f"Successfully merged {source_branch}",
        )
