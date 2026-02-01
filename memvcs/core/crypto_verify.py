"""
Cryptographic commit verification for agmem.

Merkle tree over commit blobs, optional Ed25519 signing of Merkle root.
Verification on checkout, pull, and via verify/fsck.
"""

import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Optional, List, Tuple, Any, Dict

from .objects import ObjectStore, Tree, Commit, Blob

# Ed25519 via cryptography (optional)
try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import serialization

    ED25519_AVAILABLE = True
except ImportError:
    ED25519_AVAILABLE = False


def _collect_blob_hashes_from_tree(store: ObjectStore, tree_hash: str) -> List[str]:
    """Recursively collect all blob hashes from a tree. Returns sorted list for deterministic Merkle."""
    tree = Tree.load(store, tree_hash)
    if not tree:
        return []
    blobs: List[str] = []
    for entry in tree.entries:
        if entry.obj_type == "blob":
            blobs.append(entry.hash)
        elif entry.obj_type == "tree":
            blobs.extend(_collect_blob_hashes_from_tree(store, entry.hash))
    return sorted(blobs)


def _merkle_hash(data: bytes) -> str:
    """SHA-256 hash for Merkle tree nodes."""
    return hashlib.sha256(data).hexdigest()


def build_merkle_tree(blob_hashes: List[str]) -> str:
    """
    Build balanced binary Merkle tree from blob hashes.
    Leaves are hashes of blob hashes (as hex strings); internal nodes hash(left_hex || right_hex).
    Returns root hash (hex).
    """
    if not blob_hashes:
        return _merkle_hash(b"empty")
    # Leaves: hash each blob hash string to fixed-size leaf
    layer = [_merkle_hash(h.encode()) for h in blob_hashes]
    while len(layer) > 1:
        next_layer = []
        for i in range(0, len(layer), 2):
            left = layer[i]
            right = layer[i + 1] if i + 1 < len(layer) else layer[i]
            combined = (left + right).encode()
            next_layer.append(_merkle_hash(combined))
        layer = next_layer
    return layer[0]


def build_merkle_root_for_commit(store: ObjectStore, commit_hash: str) -> Optional[str]:
    """Build Merkle root for a commit's tree. Returns None if commit/tree missing."""
    commit = Commit.load(store, commit_hash)
    if not commit:
        return None
    blobs = _collect_blob_hashes_from_tree(store, commit.tree)
    return build_merkle_tree(blobs)


def merkle_proof(blob_hashes: List[str], target_blob_hash: str) -> Optional[List[Tuple[str, str]]]:
    """
    Produce Merkle proof for a blob: list of (sibling_hash, "L"|"R") from leaf to root.
    Returns None if target not in list.
    """
    if target_blob_hash not in blob_hashes:
        return None
    layer = [_merkle_hash(h.encode()) for h in sorted(blob_hashes)]
    leaf_index = sorted(blob_hashes).index(target_blob_hash)
    proof: List[Tuple[str, str]] = []
    idx = leaf_index
    while len(layer) > 1:
        next_layer = []
        for i in range(0, len(layer), 2):
            left = layer[i]
            right = layer[i + 1] if i + 1 < len(layer) else layer[i]
            combined = (left + right).encode()
            parent = _merkle_hash(combined)
            next_layer.append(parent)
            # If current idx is in this pair, record sibling and advance index
            pair_idx = i // 2
            if idx == i:
                proof.append((right, "R"))
                idx = pair_idx
            elif idx == i + 1:
                proof.append((left, "L"))
                idx = pair_idx
        layer = next_layer
    return proof if proof else []


def verify_merkle_proof(blob_hash: str, proof: List[Tuple[str, str]], expected_root: str) -> bool:
    """Verify a Merkle proof for a blob against expected root."""
    current = _merkle_hash(blob_hash.encode())
    for sibling, side in proof:
        if side == "L":
            current = _merkle_hash((sibling + current).encode())
        else:
            current = _merkle_hash((current + sibling).encode())
    return current == expected_root


# --- Signing (Ed25519) ---


def _keys_dir(mem_dir: Path) -> Path:
    return mem_dir / "keys"


def get_signing_key_paths(mem_dir: Path) -> Tuple[Path, Path]:
    """Return (private_key_path, public_key_path). Private may not exist (env-only)."""
    kd = _keys_dir(mem_dir)
    return (kd / "private.pem", kd / "public.pem")


def ensure_keys_dir(mem_dir: Path) -> Path:
    """Ensure .mem/keys exists; return keys dir."""
    kd = _keys_dir(mem_dir)
    kd.mkdir(parents=True, exist_ok=True)
    return kd


def generate_keypair(mem_dir: Path) -> Tuple[bytes, bytes]:
    """Generate Ed25519 keypair. Returns (private_pem, public_pem). Requires cryptography."""
    if not ED25519_AVAILABLE:
        raise RuntimeError(
            "Signing requires 'cryptography'; install with: pip install cryptography"
        )
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return (private_pem, public_pem)


def save_public_key(mem_dir: Path, public_pem: bytes) -> Path:
    """Save public key to .mem/keys/public.pem. Returns path."""
    ensure_keys_dir(mem_dir)
    path = _keys_dir(mem_dir) / "public.pem"
    path.write_bytes(public_pem)
    return path


def load_public_key(mem_dir: Path) -> Optional[bytes]:
    """Load public key PEM from .mem/keys/public.pem or config. Returns None if not found."""
    path = _keys_dir(mem_dir) / "public.pem"
    if path.exists():
        return path.read_bytes()
    config_file = mem_dir / "config.json"
    if config_file.exists():
        try:
            config = json.loads(config_file.read_text())
            return config.get("signing", {}).get("public_key_pem")
        except Exception:
            pass
    return None


def load_private_key_from_env() -> Optional[bytes]:
    """Load private key PEM from env AGMEM_SIGNING_PRIVATE_KEY (or path in AGMEM_SIGNING_PRIVATE_KEY_FILE)."""
    pem = os.environ.get("AGMEM_SIGNING_PRIVATE_KEY")
    if pem:
        return pem.encode() if isinstance(pem, str) else pem
    path = os.environ.get("AGMEM_SIGNING_PRIVATE_KEY_FILE")
    if path and os.path.isfile(path):
        return Path(path).read_bytes()
    return None


def sign_merkle_root(root_hex: str, private_key_pem: bytes) -> str:
    """Sign Merkle root (hex string). Returns signature as hex."""
    if not ED25519_AVAILABLE:
        raise RuntimeError("Signing requires 'cryptography'")
    key = serialization.load_pem_private_key(private_key_pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("Ed25519 private key required")
    sig = key.sign(root_hex.encode())
    return sig.hex()


def verify_signature(root_hex: str, signature_hex: str, public_key_pem: bytes) -> bool:
    """Verify signature of Merkle root. Returns True if valid."""
    if not ED25519_AVAILABLE:
        return False
    try:
        key = serialization.load_pem_public_key(public_key_pem)
        if not isinstance(key, Ed25519PublicKey):
            return False
        key.verify(bytes.fromhex(signature_hex), root_hex.encode())
        return True
    except InvalidSignature:
        return False
    except Exception:
        return False


def verify_commit(
    store: ObjectStore,
    commit_hash: str,
    public_key_pem: Optional[bytes] = None,
    *,
    mem_dir: Optional[Path] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Verify commit: rebuild Merkle tree from blobs, compare root to stored, verify signature.
    Returns (verified, error_message). verified=True means OK; False + message means tampered or unverified.
    If public_key_pem is None and mem_dir is set, load from mem_dir.
    """
    commit = Commit.load(store, commit_hash)
    if not commit:
        return (False, "commit not found")
    stored_root = (commit.metadata or {}).get("merkle_root")
    stored_sig = (commit.metadata or {}).get("signature")
    if not stored_root:
        return (False, "commit has no merkle_root (unverified)")

    # Verify that blob objects can be loaded successfully (detects tampering in compressed/encrypted content)
    blob_hashes = _collect_blob_hashes_from_tree(store, commit.tree)
    for blob_hash in blob_hashes:
        try:
            blob = Blob.load(store, blob_hash)
            if blob is None:
                return (False, f"blob {blob_hash[:8]} corrupted or missing")
        except Exception as e:
            return (False, f"merkle_root mismatch (commit tampered)")

    computed_root = build_merkle_root_for_commit(store, commit_hash)
    if not computed_root:
        return (False, "could not build Merkle tree (missing tree/blobs)")
    if not hmac.compare_digest(computed_root, stored_root):
        return (False, "merkle_root mismatch (commit tampered)")
    if not stored_sig:
        return (True, None)  # Root matches; no signature (legacy)
    pub = public_key_pem
    if not pub and mem_dir:
        pub = load_public_key(mem_dir)
    if not pub:
        return (False, "signature present but no public key configured")
    if isinstance(pub, str):
        pub = pub.encode()
    if not verify_signature(stored_root, stored_sig, pub):
        return (False, "signature verification failed")
    return (True, None)


def verify_commit_optional(
    store: ObjectStore,
    commit_hash: str,
    mem_dir: Optional[Path] = None,
    *,
    strict: bool = False,
) -> None:
    """
    Verify commit; if strict=True raise on failure. If strict=False, only raise on tamper (root mismatch).
    Unverified (no merkle_root) is OK when not strict.
    """
    ok, err = verify_commit(store, commit_hash, None, mem_dir=mem_dir)
    if ok:
        return
    if not err:
        return
    if "tampered" in err or "mismatch" in err or "signature verification failed" in err:
        raise ValueError(f"Commit verification failed: {err}")
    if strict:
        raise ValueError(f"Commit verification failed: {err}")
