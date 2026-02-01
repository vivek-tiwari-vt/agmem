"""
Pack files and garbage collection for agmem.

Pack: collect loose objects into single file + index. GC: delete unreachable objects, repack.
"""

import json
import zlib
from pathlib import Path
from typing import Set, Dict, List, Optional, Tuple

from .objects import ObjectStore
from .refs import RefsManager


def _pack_dir(objects_dir: Path) -> Path:
    return objects_dir / "pack"


def list_loose_objects(objects_dir: Path) -> Set[str]:
    """List all loose object hashes (blob, tree, commit, tag)."""
    hashes = set()
    for obj_type in ["blob", "tree", "commit", "tag"]:
        type_dir = objects_dir / obj_type
        if not type_dir.exists():
            continue
        for prefix_dir in type_dir.iterdir():
            if not prefix_dir.is_dir():
                continue
            for f in prefix_dir.iterdir():
                hash_id = prefix_dir.name + f.name
                hashes.add(hash_id)
    return hashes


def reachable_from_refs(mem_dir: Path, store: ObjectStore, gc_prune_days: int = 90) -> Set[str]:
    """Collect all object hashes reachable from branches, tags, and reflog (within prune window)."""
    refs = RefsManager(mem_dir)
    reachable = set()
    # Branch tips
    for b in refs.list_branches():
        ch = refs.get_branch_commit(b)
        if ch:
            reachable.update(_collect_from_commit(store, ch))
    # Tags
    for t in refs.list_tags():
        ch = refs.get_tag_commit(t)
        if ch:
            reachable.update(_collect_from_commit(store, ch))
    # Reflog (simplified: just HEAD recent)
    try:
        log = refs.get_reflog("HEAD", max_count=1000)
        for e in log:
            h = e.get("hash")
            if h:
                reachable.update(_collect_from_commit(store, h))
    except Exception:
        pass
    return reachable


def _collect_from_commit(store: ObjectStore, commit_hash: str) -> Set[str]:
    """Collect all object hashes reachable from a commit."""
    from .remote import _collect_objects_from_commit
    return _collect_objects_from_commit(store, commit_hash)


def run_gc(mem_dir: Path, store: ObjectStore, gc_prune_days: int = 90, dry_run: bool = False) -> Tuple[int, int]:
    """
    Garbage collect: delete unreachable loose objects.
    Returns (deleted_count, bytes_freed). dry_run: only report, do not delete.
    """
    loose = list_loose_objects(mem_dir / "objects")
    reachable = reachable_from_refs(mem_dir, store, gc_prune_days)
    to_delete = loose - reachable
    freed = 0
    for hash_id in to_delete:
        # Resolve type from path
        for obj_type in ["blob", "tree", "commit", "tag"]:
            p = store.objects_dir / obj_type / hash_id[:2] / hash_id[2:]
            if p.exists():
                if not dry_run:
                    size = p.stat().st_size
                    p.unlink()
                    freed += size
                else:
                    freed += p.stat().st_size
                break
    return (len(to_delete), freed)
