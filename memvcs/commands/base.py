"""
Base command - shared logic for agmem commands.
"""

from pathlib import Path
from typing import Optional, Tuple

from memvcs.core.repository import Repository


def require_repo(repo_path: Optional[Path] = None) -> Tuple[Optional[Repository], int]:
    """
    Resolve repository and validate it exists.

    Returns:
        Tuple of (Repository or None, exit_code). If invalid, returns (None, 1).
    """
    path = (repo_path or Path(".")).resolve()
    repo = Repository(path)
    if not repo.is_valid_repo():
        print("Error: Not an agmem repository. Run 'agmem init' first.")
        return None, 1
    return repo, 0
