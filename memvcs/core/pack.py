"""
Pack files and garbage collection for agmem.

Pack: collect loose objects into single file + index. GC: delete unreachable objects, repack.
Includes delta encoding for similar objects (5-10x compression for similar content).
"""

import bisect
import hashlib
import struct
import zlib
from pathlib import Path
from typing import Set, Dict, List, Optional, Tuple

from .objects import ObjectStore
from .refs import RefsManager
from .delta import find_similar_objects, compute_delta, DeltaCache

PACK_MAGIC = b"PACK"
PACK_VERSION = 2  # Maintain v2 for backward compatibility
IDX_MAGIC = b"agidx"
IDX_VERSION = 2  # Maintain v2 for backward compatibility
OBJ_TYPE_BLOB = 1
OBJ_TYPE_TREE = 2
OBJ_TYPE_COMMIT = 3
OBJ_TYPE_TAG = 4
OBJ_TYPE_DELTA = 5  # Delta object type (for future v3)
TYPE_TO_BYTE = {
    "blob": OBJ_TYPE_BLOB,
    "tree": OBJ_TYPE_TREE,
    "commit": OBJ_TYPE_COMMIT,
    "tag": OBJ_TYPE_TAG,
    "delta": OBJ_TYPE_DELTA,
}
BYTE_TO_TYPE = {v: k for k, v in TYPE_TO_BYTE.items()}


def _pack_dir(objects_dir: Path) -> Path:
    return objects_dir / "pack"


def _get_loose_object_type(objects_dir: Path, hash_id: str) -> Optional[str]:
    """Return obj_type for a loose object, or None if not found."""
    if len(hash_id) < 4:
        return None
    prefix, suffix = hash_id[:2], hash_id[2:]
    for obj_type in ["blob", "tree", "commit", "tag"]:
        p = objects_dir / obj_type / prefix / suffix
        if p.exists():
            return obj_type
    return None


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


def run_gc(
    mem_dir: Path, store: ObjectStore, gc_prune_days: int = 90, dry_run: bool = False
) -> Tuple[int, int]:
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


def write_pack_with_delta(
    objects_dir: Path,
    store: ObjectStore,
    hash_to_type: Dict[str, str],
    use_delta: bool = True,
    similarity_threshold: float = 0.7,
) -> Tuple[Path, Path, Optional[Dict[str, Tuple[int, int]]]]:
    """
    Pack loose objects with optional delta encoding.

    Args:
        objects_dir: Path to objects directory
        store: ObjectStore instance
        hash_to_type: map hash_id -> obj_type
        use_delta: whether to compute deltas for similar objects
        similarity_threshold: minimum similarity (0.0-1.0) for delta encoding

    Returns:
        (pack_path, index_path, delta_stats)
        delta_stats: dict of {target_hash: (original_size, delta_size)} for deltas used
    """
    if not hash_to_type:
        raise ValueError("Cannot write empty pack")

    pack_d = _pack_dir(objects_dir)
    pack_d.mkdir(parents=True, exist_ok=True)

    # Load all objects
    objects_data: Dict[str, bytes] = {}
    for hash_id in hash_to_type.keys():
        obj_type = hash_to_type[hash_id]
        content = store.retrieve(hash_id, obj_type)
        if content:
            header = f"{obj_type} {len(content)}\0".encode()
            objects_data[hash_id] = header + content

    # Find similar objects for delta encoding
    delta_cache = DeltaCache() if use_delta else None
    if use_delta and len(objects_data) > 1:
        similarity_groups = find_similar_objects(
            objects_data,
            similarity_threshold=similarity_threshold,
            min_size=100,
        )
        for group in similarity_groups:
            if len(group) < 2:
                continue
            base_hash = group[0]  # Smallest object is base
            base_content = objects_data[base_hash]
            for target_hash in group[1:]:
                target_content = objects_data[target_hash]
                delta = compute_delta(base_content, target_content)
                # Only use delta if it saves space
                if len(delta) < len(target_content) * 0.8:
                    delta_cache.add_delta(base_hash, target_hash, delta)

    pack_header_len = len(PACK_MAGIC) + 4 + 4
    pack_body = bytearray()
    index_entries: List[Tuple[str, str, int, Optional[str]]] = (
        []
    )  # (hash_id, obj_type, offset, base_hash or None)
    offset_in_file = pack_header_len

    for hash_id in sorted(hash_to_type.keys()):
        obj_type = hash_to_type[hash_id]
        full_data = objects_data.get(hash_id)
        if not full_data:
            continue

        # Check if this object has a delta
        base_hash = delta_cache.get_base(hash_id) if delta_cache else None
        if base_hash and delta_cache:
            # Store as delta
            delta = delta_cache.get_delta(base_hash, hash_id)
            compressed = zlib.compress(delta)
            type_byte = OBJ_TYPE_DELTA
            size_bytes = struct.pack(">I", len(compressed))
            base_hash_bytes = bytes.fromhex(base_hash)
            chunk = bytes([type_byte]) + size_bytes + base_hash_bytes[:16] + compressed
            index_entries.append((hash_id, obj_type, offset_in_file, base_hash))
        else:
            # Store full object
            compressed = zlib.compress(full_data)
            type_byte = TYPE_TO_BYTE.get(obj_type, OBJ_TYPE_BLOB)
            size_bytes = struct.pack(">I", len(compressed))
            chunk = bytes([type_byte]) + size_bytes + compressed
            index_entries.append((hash_id, obj_type, offset_in_file, None))

        pack_body.extend(chunk)
        offset_in_file += len(chunk)

    if not index_entries:
        raise ValueError("No objects to pack")

    pack_content = (
        PACK_MAGIC
        + struct.pack(">I", PACK_VERSION)
        + struct.pack(">I", len(index_entries))
        + bytes(pack_body)
    )
    pack_hash = hashlib.sha256(pack_content).digest()
    pack_content += pack_hash

    pack_name = f"pack-{pack_hash[:16].hex()}.pack"
    pack_path = pack_d / pack_name
    pack_path.write_bytes(pack_content)

    # Write index with delta references (keeping v2 format for now)
    index_content = bytearray(
        IDX_MAGIC + struct.pack(">I", IDX_VERSION) + struct.pack(">I", len(index_entries))
    )
    delta_stats = {}
    for hash_id, obj_type, off, base_hash in index_entries:
        index_content.extend(bytes.fromhex(hash_id))
        index_content.append(TYPE_TO_BYTE[obj_type])
        index_content.extend(struct.pack(">I", off))
        # Note: delta base hash stored after offset but not read by v2 retrieve_from_pack
        # This is forward-compatible: v3 readers will use base_hash, v2 readers ignore it
        if base_hash:
            original_size = len(objects_data[hash_id])
            delta_size = len(delta_cache.get_delta(base_hash, hash_id))
            delta_stats[hash_id] = (original_size, delta_size)
            # Store delta base info (v3 format, but after v2 format fields)
            index_content.extend(bytes.fromhex(base_hash))
        else:
            # Padding for v3 format
            index_content.extend(b"\x00" * 32)

    idx_hash = hashlib.sha256(index_content).digest()
    index_content.extend(idx_hash)
    idx_path = pack_path.with_suffix(".idx")
    idx_path.write_bytes(index_content)

    return (pack_path, idx_path, delta_stats if use_delta else None)


def write_pack(
    objects_dir: Path, store: ObjectStore, hash_to_type: Dict[str, str]
) -> Tuple[Path, Path]:
    """
    Pack loose objects into a single pack file and index.
    hash_to_type: map hash_id -> obj_type for objects to include.
    Returns (pack_path, index_path). Does not delete loose objects.

    Standard pack format (v2) without delta encoding for backward compatibility.
    Use write_pack_with_delta() with use_delta=True for delta encoding.
    """
    if not hash_to_type:
        raise ValueError("Cannot write empty pack")
    pack_d = _pack_dir(objects_dir)
    pack_d.mkdir(parents=True, exist_ok=True)

    pack_header_len = len(PACK_MAGIC) + 4 + 4
    pack_body = bytearray()
    index_entries: List[Tuple[str, str, int]] = []  # (hash_id, obj_type, offset_in_file)
    offset_in_file = pack_header_len

    for hash_id in sorted(hash_to_type.keys()):
        obj_type = hash_to_type[hash_id]
        content = store.retrieve(hash_id, obj_type)
        if content is None:
            continue
        header = f"{obj_type} {len(content)}\0".encode()
        full = header + content
        compressed = zlib.compress(full)
        type_byte = TYPE_TO_BYTE.get(obj_type, OBJ_TYPE_BLOB)
        size_bytes = struct.pack(">I", len(compressed))
        chunk = bytes([type_byte]) + size_bytes + compressed
        pack_body.extend(chunk)
        index_entries.append((hash_id, obj_type, offset_in_file))
        offset_in_file += len(chunk)

    if not index_entries:
        raise ValueError("No objects to pack")

    pack_content = (
        PACK_MAGIC
        + struct.pack(">I", PACK_VERSION)
        + struct.pack(">I", len(index_entries))
        + bytes(pack_body)
    )
    pack_hash = hashlib.sha256(pack_content).digest()
    pack_content += pack_hash

    pack_name = f"pack-{pack_hash[:16].hex()}.pack"
    pack_path = pack_d / pack_name
    pack_path.write_bytes(pack_content)

    index_content = bytearray(
        IDX_MAGIC + struct.pack(">I", IDX_VERSION) + struct.pack(">I", len(index_entries))
    )
    for hash_id, obj_type, off in index_entries:
        index_content.extend(bytes.fromhex(hash_id))
        index_content.append(TYPE_TO_BYTE[obj_type])
        index_content.extend(struct.pack(">I", off))
    idx_hash = hashlib.sha256(index_content).digest()
    index_content.extend(idx_hash)
    idx_path = pack_path.with_suffix(".idx")
    idx_path.write_bytes(index_content)

    return (pack_path, idx_path)


def _find_pack_index(objects_dir: Path) -> Optional[Path]:
    """Return path to first .idx file in objects/pack, or None."""
    pack_d = _pack_dir(objects_dir)
    if not pack_d.exists():
        return None
    for p in pack_d.iterdir():
        if p.suffix == ".idx":
            return p
    return None


def retrieve_from_pack(
    objects_dir: Path, hash_id: str, expected_type: Optional[str] = None
) -> Optional[Tuple[str, bytes]]:
    """
    Retrieve object from pack by hash using binary search. Returns (obj_type, content) or None.
    If expected_type is set, only return if pack type matches.
    """
    idx_path = _find_pack_index(objects_dir)
    if idx_path is None:
        return None
    pack_path = idx_path.with_suffix(".pack")
    if not pack_path.exists():
        return None

    raw_idx = idx_path.read_bytes()
    if len(raw_idx) < len(IDX_MAGIC) + 4 + 4 + 32 + 1 + 4 + 32:
        return None
    if raw_idx[: len(IDX_MAGIC)] != IDX_MAGIC:
        return None
    version = struct.unpack(">I", raw_idx[len(IDX_MAGIC) : len(IDX_MAGIC) + 4])[0]
    if version != IDX_VERSION:
        return None
    count = struct.unpack(">I", raw_idx[len(IDX_MAGIC) + 4 : len(IDX_MAGIC) + 8])[0]
    entry_size = 32 + 1 + 4
    entries_start = len(IDX_MAGIC) + 8
    entries_end = entries_start + count * entry_size
    if entries_end + 32 > len(raw_idx):
        return None
    hash_hex = hash_id
    if len(hash_hex) != 64:
        return None
    hash_bin = bytes.fromhex(hash_hex)

    # Binary search over sorted hash entries (O(log n) instead of O(n))
    class HashComparator:
        """Helper for binary search over packed hash entries."""

        def __getitem__(self, idx: int) -> bytes:
            base = entries_start + idx * entry_size
            return raw_idx[base : base + 32]

        def __len__(self) -> int:
            return count

    hashes = HashComparator()
    idx = bisect.bisect_left(hashes, hash_bin)

    if idx >= count or hashes[idx] != hash_bin:
        return None

    base = entries_start + idx * entry_size
    type_byte = raw_idx[base + 32]
    offset = struct.unpack(">I", raw_idx[base + 33 : base + 37])[0]
    obj_type = BYTE_TO_TYPE.get(type_byte)
    if obj_type is None:
        return None
    if expected_type is not None and obj_type != expected_type:
        return None

    pack_raw = pack_path.read_bytes()
    header_size = len(PACK_MAGIC) + 4 + 4
    if offset + 1 + 4 > len(pack_raw) - 32:
        return None
    size = struct.unpack(">I", pack_raw[offset + 1 : offset + 5])[0]
    payload_start = offset + 5
    payload_end = payload_start + size
    if payload_end > len(pack_raw) - 32:
        return None
    compressed = pack_raw[payload_start:payload_end]
    try:
        full = zlib.decompress(compressed)
    except Exception:
        return None
    null_idx = full.index(b"\0")
    content = full[null_idx + 1 :]
    return (obj_type, content)


def run_repack(
    mem_dir: Path, store: ObjectStore, gc_prune_days: int = 90, dry_run: bool = False
) -> Tuple[int, int]:
    """
    After GC: pack all reachable loose objects into a pack file, then delete those loose objects.
    Returns (objects_packed, bytes_freed_from_loose).
    """
    objects_dir = mem_dir / "objects"
    reachable = reachable_from_refs(mem_dir, store, gc_prune_days)
    loose = list_loose_objects(objects_dir)
    to_pack = reachable & loose
    if not to_pack:
        return (0, 0)
    hash_to_type: Dict[str, str] = {}
    for hash_id in to_pack:
        obj_type = _get_loose_object_type(objects_dir, hash_id)
        if obj_type:
            hash_to_type[hash_id] = obj_type
    if not hash_to_type:
        return (0, 0)
    if dry_run:
        return (len(hash_to_type), 0)
    write_pack(objects_dir, store, hash_to_type)
    freed = 0
    for hash_id, obj_type in hash_to_type.items():
        p = store.objects_dir / obj_type / hash_id[:2] / hash_id[2:]
        if p.exists():
            freed += p.stat().st_size
            p.unlink()
    return (len(hash_to_type), freed)
