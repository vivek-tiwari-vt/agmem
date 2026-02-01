"""
IPFS remote for agmem (stub).

Push/pull via CIDs; pinning; gateway fallback when daemon unavailable.
Requires optional ipfs extra (ipfshttpclient or gateway requests).
"""

from pathlib import Path
from typing import Optional, Set

from .objects import ObjectStore
from .remote import _collect_objects_from_commit


def push_to_ipfs(
    objects_dir: Path,
    branch: str,
    commit_hash: str,
    gateway_url: str = "https://ipfs.io",
) -> Optional[str]:
    """Push branch objects to IPFS and return root CID. Stub: returns None until IPFS client added."""
    return None


def pull_from_ipfs(
    objects_dir: Path,
    cid: str,
    gateway_url: str = "https://ipfs.io",
) -> bool:
    """Pull objects by CID from IPFS into objects_dir. Stub: returns False until IPFS client added."""
    return False


def parse_ipfs_url(url: str) -> Optional[str]:
    """Parse ipfs://<cid> or ipfs://<cid>/path. Returns CID or None."""
    if not url.startswith("ipfs://"):
        return None
    rest = url[7:].lstrip("/")
    return rest.split("/")[0] or None
