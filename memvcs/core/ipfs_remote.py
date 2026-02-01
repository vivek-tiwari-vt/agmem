"""
IPFS remote for agmem.

Push/pull via CIDs using HTTP gateway (POST /api/v0/add, GET /ipfs/<cid>).
Optional ipfshttpclient for local daemon.
"""

import json
import struct
import zlib
from pathlib import Path
from typing import Optional, Set, Dict, Tuple

from .objects import ObjectStore
from .remote import _collect_objects_from_commit

# Type byte for bundle (same as pack)
_TYPE_BLOB = 1
_TYPE_TREE = 2
_TYPE_COMMIT = 3
_TYPE_TAG = 4
_TYPE_TO_BYTE = {"blob": _TYPE_BLOB, "tree": _TYPE_TREE, "commit": _TYPE_COMMIT, "tag": _TYPE_TAG}
_BYTE_TO_TYPE = {v: k for k, v in _TYPE_TO_BYTE.items()}


def _get_object_type_and_content(store: ObjectStore, hash_id: str) -> Optional[Tuple[str, bytes]]:
    """Return (obj_type, raw_content) for a hash, or None."""
    for obj_type in ["commit", "tree", "blob", "tag"]:
        content = store.retrieve(hash_id, obj_type)
        if content is not None:
            return (obj_type, content)
    return None


def _bundle_objects(store: ObjectStore, hash_ids: Set[str]) -> bytes:
    """Bundle objects into a single byte blob: count + [hash(32) type(1) len(4) zlib_payload]."""
    entries = []
    for h in sorted(hash_ids):
        pair = _get_object_type_and_content(store, h)
        if pair is None:
            continue
        obj_type, content = pair
        header = f"{obj_type} {len(content)}\0".encode()
        full = header + content
        compressed = zlib.compress(full)
        h_bin = bytes.fromhex(h) if len(h) == 64 else h.encode().ljust(32)[:32]
        entries.append((h_bin, _TYPE_TO_BYTE.get(obj_type, _TYPE_BLOB), compressed))
    parts = [struct.pack(">I", len(entries))]
    for h_bin, type_byte, compressed in entries:
        parts.append(h_bin)
        parts.append(bytes([type_byte]))
        parts.append(struct.pack(">I", len(compressed)))
        parts.append(compressed)
    return b"".join(parts)


def _unbundle_objects(data: bytes, objects_dir: Path) -> int:
    """Unbundle and write loose objects. Returns count written."""
    if len(data) < 4:
        return 0
    count = struct.unpack(">I", data[:4])[0]
    offset = 4
    written = 0
    for _ in range(count):
        if offset + 32 + 1 + 4 > len(data):
            break
        h_bin = data[offset : offset + 32]
        offset += 32
        type_byte = data[offset]
        offset += 1
        comp_len = struct.unpack(">I", data[offset : offset + 4])[0]
        offset += 4
        if offset + comp_len > len(data):
            break
        compressed = data[offset : offset + comp_len]
        offset += comp_len
        obj_type = _BYTE_TO_TYPE.get(type_byte)
        if obj_type is None:
            continue
        try:
            full = zlib.decompress(compressed)
        except Exception:
            continue
        null_idx = full.index(b"\0")
        # Validate header
        prefix = full[:null_idx].decode()
        if " " not in prefix:
            continue
        name, size_str = prefix.split(" ", 1)
        hash_hex = h_bin.hex() if len(h_bin) == 32 else h_bin.decode().strip()
        if len(hash_hex) < 4:
            continue
        obj_path = objects_dir / obj_type / hash_hex[:2] / hash_hex[2:]
        obj_path.parent.mkdir(parents=True, exist_ok=True)
        obj_path.write_bytes(compressed)
        written += 1
    return written


def _add_to_ipfs_gateway(bundle: bytes, gateway_url: str) -> Optional[str]:
    """POST bundle to IPFS gateway /api/v0/add (multipart). Returns CID or None."""
    boundary = "----agmem-boundary-" + str(abs(hash(bundle)))[:12]
    body = (
        b"--" + boundary.encode() + b"\r\n"
        b'Content-Disposition: form-data; name="file"; filename="agmem-bundle.bin"\r\n'
        b"Content-Type: application/octet-stream\r\n\r\n"
        + bundle + b"\r\n"
        b"--" + boundary.encode() + b"--\r\n"
    )
    try:
        import urllib.request

        url = gateway_url.rstrip("/") + "/api/v0/add"
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "multipart/form-data; boundary=" + boundary)
        req.add_header("Content-Length", str(len(body)))
        with urllib.request.urlopen(req, timeout=120) as resp:
            if resp.status != 200:
                return None
            data = json.loads(resp.read().decode())
            return data.get("Hash") or data.get("Name")
    except Exception:
        try:
            import requests

            url = gateway_url.rstrip("/") + "/api/v0/add"
            r = requests.post(
                url,
                files={"file": ("agmem-bundle.bin", bundle, "application/octet-stream")},
                timeout=120,
            )
            if r.status_code != 200:
                return None
            return r.json().get("Hash") or r.json().get("Name")
        except Exception:
            return None


def push_to_ipfs(
    objects_dir: Path,
    branch: str,
    commit_hash: str,
    gateway_url: str = "https://ipfs.io",
    store: Optional[ObjectStore] = None,
) -> Optional[str]:
    """
    Push branch objects to IPFS and return root CID.
    Uses gateway POST /api/v0/add (multipart).
    """
    if store is None:
        store = ObjectStore(objects_dir)
    try:
        reachable = _collect_objects_from_commit(store, commit_hash)
    except Exception:
        return None
    if not reachable:
        return None
    bundle = _bundle_objects(store, reachable)
    return _add_to_ipfs_gateway(bundle, gateway_url)


def pull_from_ipfs(
    objects_dir: Path,
    cid: str,
    gateway_url: str = "https://ipfs.io",
) -> bool:
    """
    Pull objects by CID from IPFS into objects_dir (loose objects).
    Uses GET gateway_url/ipfs/<cid>.
    """
    try:
        import urllib.request

        url = gateway_url.rstrip("/") + "/ipfs/" + cid
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=60) as resp:
            if resp.status != 200:
                return False
            data = resp.read()
    except Exception:
        try:
            import requests

            url = gateway_url.rstrip("/") + "/ipfs/" + cid
            r = requests.get(url, timeout=60)
            if r.status_code != 200:
                return False
            data = r.content
        except Exception:
            return False
    written = _unbundle_objects(data, objects_dir)
    return written > 0


def parse_ipfs_url(url: str) -> Optional[str]:
    """Parse ipfs://<cid> or ipfs://<cid>/path. Returns CID or None."""
    if not url.startswith("ipfs://"):
        return None
    rest = url[7:].lstrip("/")
    return rest.split("/")[0] or None
