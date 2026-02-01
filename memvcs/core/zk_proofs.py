"""
Zero-knowledge proof system for agmem.

Hash/signature-based proofs: keyword containment (Merkle set membership),
memory freshness (signed timestamp). Full zk-SNARK backend can be added later.
"""

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Optional, List, Tuple, Any, Dict

from .crypto_verify import (
    build_merkle_tree,
    merkle_proof,
    verify_merkle_proof,
    load_public_key,
    load_private_key_from_env,
    sign_merkle_root,
    verify_signature,
    ED25519_AVAILABLE,
)


def _word_hashes(content: str) -> List[str]:
    """Extract words and return sorted list of SHA-256 hashes (hex)."""
    words = set()
    for word in content.split():
        w = word.strip().lower()
        if len(w) >= 1:
            words.add(w)
    return sorted(hashlib.sha256(w.encode()).hexdigest() for w in words)


def prove_keyword_containment(memory_path: Path, keyword: str, output_proof_path: Path) -> bool:
    """
    Prove memory file contains keyword without revealing content.
    Proof: Merkle set membership of H(keyword) over word hashes in file.
    """
    if not memory_path.exists() or not memory_path.is_file():
        return False
    try:
        content = memory_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False
    word_hashes_list = _word_hashes(content)
    keyword_hash = hashlib.sha256(keyword.strip().lower().encode()).hexdigest()
    if keyword_hash not in word_hashes_list:
        return False
    root = build_merkle_tree(word_hashes_list)
    proof_path_list = merkle_proof(word_hashes_list, keyword_hash)
    if proof_path_list is None:
        return False
    proof_data = {
        "statement_type": "keyword",
        "keyword_hash": keyword_hash,
        "root": root,
        "path": proof_path_list,
    }
    output_proof_path.parent.mkdir(parents=True, exist_ok=True)
    output_proof_path.write_text(json.dumps(proof_data, indent=2))
    return True


def prove_memory_freshness(
    memory_path: Path, after_timestamp: str, output_proof_path: Path, mem_dir: Optional[Path] = None
) -> bool:
    """
    Prove memory was updated after date without revealing content.
    Proof: signed file mtime (or current time) and optional public key.
    """
    if not memory_path.exists() or not memory_path.is_file():
        return False
    if not ED25519_AVAILABLE:
        return False
    try:
        stat = memory_path.stat()
        ts = stat.st_mtime
        from datetime import datetime, timezone

        iso_ts = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except Exception:
        return False
    private_pem = load_private_key_from_env() if mem_dir is not None else None
    if private_pem is None:
        return False
    try:
        sig_hex = sign_merkle_root(iso_ts, private_pem)
    except Exception:
        return False
    proof_data = {"statement_type": "freshness", "timestamp": iso_ts, "signature": sig_hex}
    if mem_dir is not None:
        pub_pem = load_public_key(mem_dir)
        if pub_pem is not None:
            proof_data["public_key_pem_b64"] = base64.b64encode(pub_pem).decode()
    output_proof_path.parent.mkdir(parents=True, exist_ok=True)
    output_proof_path.write_text(json.dumps(proof_data, indent=2))
    return True


def verify_proof(proof_path: Path, statement_type: str, **kwargs: Any) -> bool:
    """
    Verify a proof. statement_type in ("keyword", "freshness").
    For keyword: pass keyword=... (the keyword string).
    For freshness: pass after_timestamp=... (ISO date string). Optional mem_dir=... for public key.
    """
    if not proof_path.exists() or not proof_path.is_file():
        return False
    try:
        data = json.loads(proof_path.read_text())
    except Exception:
        return False
    if data.get("statement_type") != statement_type:
        return False
    if statement_type == "keyword":
        keyword = kwargs.get("keyword")
        if keyword is None:
            return False
        keyword_hash = hashlib.sha256(keyword.strip().lower().encode()).hexdigest()
        if data.get("keyword_hash") != keyword_hash:
            return False
        root = data.get("root")
        path_list = data.get("path")
        if not root or path_list is None:
            return False
        return verify_merkle_proof(keyword_hash, path_list, root)
    if statement_type == "freshness":
        after_ts = kwargs.get("after_timestamp")
        if after_ts is None:
            return False
        ts_str = data.get("timestamp")
        sig_hex = data.get("signature")
        if not ts_str or not sig_hex:
            return False
        pub_pem_b64 = data.get("public_key_pem_b64")
        if pub_pem_b64:
            try:
                pub_pem = base64.b64decode(pub_pem_b64)
            except Exception:
                return False
        else:
            mem_dir = kwargs.get("mem_dir")
            if mem_dir is None:
                return False
            pub_pem = load_public_key(Path(mem_dir))
            if pub_pem is None:
                return False
        if not verify_signature(ts_str, sig_hex, pub_pem):
            return False
        try:
            from datetime import datetime

            after_dt = datetime.fromisoformat(after_ts.replace("Z", "+00:00"))
            ts_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            return ts_dt >= after_dt
        except Exception:
            return False
    return False
