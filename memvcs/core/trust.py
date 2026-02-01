"""
Multi-agent trust and identity model for agmem.

Trust store: map public keys to levels (full | conditional | untrusted).
Used on pull/merge to decide auto-merge, prompt, or block.
"""

import hashlib
import json
from pathlib import Path
from typing import Optional, Dict, List, Any, Union

TRUST_LEVELS = ("full", "conditional", "untrusted")


def _trust_dir(mem_dir: Path) -> Path:
    return mem_dir / "trust"


def _trust_file(mem_dir: Path) -> Path:
    return _trust_dir(mem_dir) / "trust.json"


def _key_id(public_key_pem: bytes) -> str:
    """Stable id for a public key (hash of PEM)."""
    return hashlib.sha256(public_key_pem).hexdigest()[:16]


def _ensure_bytes(pem: Union[bytes, str]) -> bytes:
    """Normalize PEM to bytes for hashing/serialization."""
    return pem.encode("utf-8") if isinstance(pem, str) else pem


def load_trust_store(mem_dir: Path) -> List[Dict[str, Any]]:
    """Load trust store: list of { key_id, public_key_pem, level }."""
    path = _trust_file(mem_dir)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        return data.get("entries", [])
    except Exception:
        return []


def get_trust_level(mem_dir: Path, public_key_pem: Union[bytes, str]) -> Optional[str]:
    """Get trust level for a public key. Returns 'full'|'conditional'|'untrusted' or None if unknown."""
    pem_b = _ensure_bytes(public_key_pem)
    kid = _key_id(pem_b)
    key_pem_str = pem_b.decode("utf-8")
    for e in load_trust_store(mem_dir):
        entry_id = e.get("key_id") or _key_id((e.get("public_key_pem") or "").encode())
        if entry_id == kid:
            return e.get("level")
        if e.get("public_key_pem") == key_pem_str:
            return e.get("level")
    return None


# Reasonable upper bound for PEM to avoid DoS (typical Ed25519 public PEM ~120 bytes)
_MAX_PEM_BYTES = 8192


def set_trust(mem_dir: Path, public_key_pem: Union[bytes, str], level: str) -> None:
    """Set trust level for a public key. level: full | conditional | untrusted."""
    if level not in TRUST_LEVELS:
        raise ValueError(f"level must be one of {TRUST_LEVELS}")
    pem_b = _ensure_bytes(public_key_pem)
    if len(pem_b) > _MAX_PEM_BYTES:
        raise ValueError("Public key PEM exceeds maximum size")
    kid = _key_id(pem_b)
    key_pem_str = pem_b.decode("utf-8")
    _trust_dir(mem_dir).mkdir(parents=True, exist_ok=True)
    entries = load_trust_store(mem_dir)
    entries = [e for e in entries if (e.get("key_id") or _key_id((e.get("public_key_pem") or "").encode())) != kid]
    entries.append({"key_id": kid, "public_key_pem": key_pem_str, "level": level})
    _trust_file(mem_dir).write_text(json.dumps({"entries": entries}, indent=2))


def find_verifying_key(mem_dir: Path, commit_metadata: Dict[str, Any]) -> Optional[bytes]:
    """
    Try each key in trust store to verify the commit's signature.
    commit_metadata should have merkle_root and signature.
    Returns public_key_pem of first key that verifies, or None.
    """
    from .crypto_verify import verify_signature
    root = commit_metadata.get("merkle_root")
    sig = commit_metadata.get("signature")
    if not root or not sig:
        return None
    for e in load_trust_store(mem_dir):
        pem = e.get("public_key_pem")
        if not pem:
            continue
        pem_b = _ensure_bytes(pem)
        if verify_signature(root, sig, pem_b):
            return pem_b
    return None
