"""
Diff functionality for agmem.

Compare commits, trees, and files.
"""

from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum

from .objects import ObjectStore, Commit, Tree, Blob


class DiffType(Enum):
    """Types of differences."""

    ADDED = "added"
    DELETED = "deleted"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"


@dataclass
class FileDiff:
    """Difference for a single file."""

    path: str
    diff_type: DiffType
    old_hash: Optional[str]
    new_hash: Optional[str]
    old_content: Optional[str]
    new_content: Optional[str]
    diff_lines: List[str]


@dataclass
class TreeDiff:
    """Difference between two trees."""

    files: List[FileDiff]
    added_count: int
    deleted_count: int
    modified_count: int


class DiffEngine:
    """Engine for computing differences."""

    def __init__(self, object_store: ObjectStore):
        self.object_store = object_store

    def get_tree_files(self, tree_hash: str) -> Dict[str, str]:
        """Get all files in a tree with their blob hashes."""
        files = {}
        tree = Tree.load(self.object_store, tree_hash)

        if tree:
            for entry in tree.entries:
                path = entry.path + "/" + entry.name if entry.path else entry.name
                files[path] = entry.hash

        return files

    def get_blob_content(self, hash_id: Optional[str]) -> Optional[str]:
        """Get blob content as string."""
        if not hash_id:
            return None

        blob = Blob.load(self.object_store, hash_id)
        if blob:
            return blob.content.decode("utf-8", errors="replace")
        return None

    def compute_line_diff(
        self, old_content: Optional[str], new_content: Optional[str]
    ) -> List[str]:
        """
        Compute line-by-line diff between two contents.

        Returns:
            List of diff lines with +/- prefixes
        """
        old_lines = (old_content or "").splitlines(keepends=True)
        new_lines = (new_content or "").splitlines(keepends=True)

        # Simple diff algorithm (LCS-based would be better)
        diff_lines = []

        # Handle empty cases
        if not old_lines or old_lines == [""]:
            for line in new_lines:
                diff_lines.append(f"+ {line.rstrip()}")
            return diff_lines

        if not new_lines or new_lines == [""]:
            for line in old_lines:
                diff_lines.append(f"- {line.rstrip()}")
            return diff_lines

        # Use unified diff style
        max_lines = max(len(old_lines), len(new_lines))

        i, j = 0, 0
        while i < len(old_lines) or j < len(new_lines):
            if i < len(old_lines) and j < len(new_lines):
                old_line = old_lines[i].rstrip()
                new_line = new_lines[j].rstrip()

                if old_line == new_line:
                    diff_lines.append(f"  {old_line}")
                    i += 1
                    j += 1
                else:
                    # Find if this line exists later in new
                    found = False
                    for k in range(j + 1, min(j + 5, len(new_lines))):
                        if new_lines[k].rstrip() == old_line:
                            # Lines were added
                            for l in range(j, k):
                                diff_lines.append(f"+ {new_lines[l].rstrip()}")
                            j = k
                            found = True
                            break

                    if not found:
                        # Line was removed
                        diff_lines.append(f"- {old_line}")
                        i += 1
            elif i < len(old_lines):
                diff_lines.append(f"- {old_lines[i].rstrip()}")
                i += 1
            else:
                diff_lines.append(f"+ {new_lines[j].rstrip()}")
                j += 1

        return diff_lines

    def diff_trees(self, old_tree_hash: Optional[str], new_tree_hash: Optional[str]) -> TreeDiff:
        """
        Compute diff between two trees.

        Args:
            old_tree_hash: Hash of old tree (None for empty)
            new_tree_hash: Hash of new tree (None for empty)

        Returns:
            TreeDiff with file differences
        """
        old_files = self.get_tree_files(old_tree_hash) if old_tree_hash else {}
        new_files = self.get_tree_files(new_tree_hash) if new_tree_hash else {}

        all_paths = set(old_files.keys()) | set(new_files.keys())

        file_diffs = []
        added = 0
        deleted = 0
        modified = 0

        for path in sorted(all_paths):
            old_hash = old_files.get(path)
            new_hash = new_files.get(path)

            if not old_hash and new_hash:
                # Added
                new_content = self.get_blob_content(new_hash)
                diff_lines = self.compute_line_diff(None, new_content)

                file_diffs.append(
                    FileDiff(
                        path=path,
                        diff_type=DiffType.ADDED,
                        old_hash=None,
                        new_hash=new_hash,
                        old_content=None,
                        new_content=new_content,
                        diff_lines=diff_lines,
                    )
                )
                added += 1

            elif old_hash and not new_hash:
                # Deleted
                old_content = self.get_blob_content(old_hash)
                diff_lines = self.compute_line_diff(old_content, None)

                file_diffs.append(
                    FileDiff(
                        path=path,
                        diff_type=DiffType.DELETED,
                        old_hash=old_hash,
                        new_hash=None,
                        old_content=old_content,
                        new_content=None,
                        diff_lines=diff_lines,
                    )
                )
                deleted += 1

            elif old_hash != new_hash:
                # Modified
                old_content = self.get_blob_content(old_hash)
                new_content = self.get_blob_content(new_hash)
                diff_lines = self.compute_line_diff(old_content, new_content)

                file_diffs.append(
                    FileDiff(
                        path=path,
                        diff_type=DiffType.MODIFIED,
                        old_hash=old_hash,
                        new_hash=new_hash,
                        old_content=old_content,
                        new_content=new_content,
                        diff_lines=diff_lines,
                    )
                )
                modified += 1

        return TreeDiff(
            files=file_diffs, added_count=added, deleted_count=deleted, modified_count=modified
        )

    def diff_commits(
        self, old_commit_hash: Optional[str], new_commit_hash: Optional[str]
    ) -> TreeDiff:
        """
        Compute diff between two commits.

        Args:
            old_commit_hash: Hash of old commit (None for empty)
            new_commit_hash: Hash of new commit (None for empty)

        Returns:
            TreeDiff with file differences
        """
        old_tree_hash = None
        new_tree_hash = None

        if old_commit_hash:
            old_commit = Commit.load(self.object_store, old_commit_hash)
            if old_commit:
                old_tree_hash = old_commit.tree

        if new_commit_hash:
            new_commit = Commit.load(self.object_store, new_commit_hash)
            if new_commit:
                new_tree_hash = new_commit.tree

        return self.diff_trees(old_tree_hash, new_tree_hash)

    def format_diff(self, tree_diff: TreeDiff, old_ref: str = "a", new_ref: str = "b") -> str:
        """
        Format tree diff as unified diff string.

        Args:
            tree_diff: TreeDiff to format
            old_ref: Label for old version
            new_ref: Label for new version

        Returns:
            Formatted diff string
        """
        lines = []

        for file_diff in tree_diff.files:
            if file_diff.diff_type == DiffType.UNCHANGED:
                continue

            # File header
            lines.append(f"diff --agmem {old_ref}/{file_diff.path} {new_ref}/{file_diff.path}")

            if file_diff.diff_type == DiffType.ADDED:
                lines.append(f"new file mode 100644")
                lines.append(f"index 0000000..{file_diff.new_hash[:7]}")
                lines.append(f"--- /dev/null")
                lines.append(f"+++ {new_ref}/{file_diff.path}")
            elif file_diff.diff_type == DiffType.DELETED:
                lines.append(f"deleted file mode 100644")
                lines.append(f"index {file_diff.old_hash[:7]}..0000000")
                lines.append(f"--- {old_ref}/{file_diff.path}")
                lines.append(f"+++ /dev/null")
            else:  # MODIFIED
                lines.append(f"index {file_diff.old_hash[:7]}..{file_diff.new_hash[:7]}")
                lines.append(f"--- {old_ref}/{file_diff.path}")
                lines.append(f"+++ {new_ref}/{file_diff.path}")

            # Diff content
            lines.append("@@ -1 +1 @@")
            for diff_line in file_diff.diff_lines:
                lines.append(diff_line)

            lines.append("")  # Empty line between files

        # Summary
        lines.append(f"# {tree_diff.added_count} file(s) added")
        lines.append(f"# {tree_diff.deleted_count} file(s) deleted")
        lines.append(f"# {tree_diff.modified_count} file(s) modified")

        return "\n".join(lines)

    def diff_working_dir(self, commit_hash: str, working_files: Dict[str, bytes]) -> TreeDiff:
        """
        Compute diff between a commit and working directory.

        Args:
            commit_hash: Commit to compare against
            working_files: Dict mapping paths to file contents

        Returns:
            TreeDiff with differences
        """
        # Get commit files
        commit = Commit.load(self.object_store, commit_hash)
        if not commit:
            return TreeDiff(files=[], added_count=0, deleted_count=0, modified_count=0)

        commit_files = self.get_tree_files(commit.tree)

        file_diffs = []
        added = 0
        deleted = 0
        modified = 0

        all_paths = set(commit_files.keys()) | set(working_files.keys())

        for path in sorted(all_paths):
            commit_hash_id = commit_files.get(path)
            working_content = working_files.get(path)

            # Compute working file hash
            working_hash = None
            if working_content is not None:
                blob = Blob(content=working_content)
                working_hash = blob.store(self.object_store)

            if not commit_hash_id and working_hash:
                # Added
                new_content = (
                    working_content.decode("utf-8", errors="replace") if working_content else None
                )
                diff_lines = self.compute_line_diff(None, new_content)

                file_diffs.append(
                    FileDiff(
                        path=path,
                        diff_type=DiffType.ADDED,
                        old_hash=None,
                        new_hash=working_hash,
                        old_content=None,
                        new_content=new_content,
                        diff_lines=diff_lines,
                    )
                )
                added += 1

            elif commit_hash_id and not working_hash:
                # Deleted
                old_content = self.get_blob_content(commit_hash_id)
                diff_lines = self.compute_line_diff(old_content, None)

                file_diffs.append(
                    FileDiff(
                        path=path,
                        diff_type=DiffType.DELETED,
                        old_hash=commit_hash_id,
                        new_hash=None,
                        old_content=old_content,
                        new_content=None,
                        diff_lines=diff_lines,
                    )
                )
                deleted += 1

            elif commit_hash_id != working_hash:
                # Modified
                old_content = self.get_blob_content(commit_hash_id)
                new_content = (
                    working_content.decode("utf-8", errors="replace") if working_content else None
                )
                diff_lines = self.compute_line_diff(old_content, new_content)

                file_diffs.append(
                    FileDiff(
                        path=path,
                        diff_type=DiffType.MODIFIED,
                        old_hash=commit_hash_id,
                        new_hash=working_hash,
                        old_content=old_content,
                        new_content=new_content,
                        diff_lines=diff_lines,
                    )
                )
                modified += 1

        return TreeDiff(
            files=file_diffs, added_count=added, deleted_count=deleted, modified_count=modified
        )
