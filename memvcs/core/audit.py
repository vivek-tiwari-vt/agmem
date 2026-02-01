"""
Tamper-evident audit trail for agmem.

Append-only, hash-chained log of significant operations.
"""

import datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple


def _audit_dir(mem_dir: Path) -> Path:
    return mem_dir / "audit"


def _log_path(mem_dir: Path) -> Path:
    return _audit_dir(mem_dir) / "log"


def _get_previous_hash(mem_dir: Path) -> str:
    """Read last line of audit log and return its entry hash, or empty for first entry."""
    path = _log_path(mem_dir)
    if not path.exists():
        return ""
    lines = path.read_text().strip().split("\n")
    if not lines:
        return ""
    # Format per line: entry_hash\tpayload_json
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        if "\t" in line:
            return line.split("\t", 1)[0]
        return ""
    return ""


def _hash_entry(prev_hash: str, payload: str) -> str:
    """Compute this entry's hash: SHA-256(prev_hash + payload)."""
    return hashlib.sha256((prev_hash + payload).encode()).hexdigest()


def append_audit(
    mem_dir: Path,
    operation: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Append a tamper-evident audit entry. Write synchronously.
    Each entry: entry_hash TAB payload_json (payload has timestamp, operation, details, prev_hash).
    """
    mem_dir = Path(mem_dir)
    _audit_dir(mem_dir).mkdir(parents=True, exist_ok=True)
    path = _log_path(mem_dir)
    prev_hash = _get_previous_hash(mem_dir)
    payload = {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "operation": operation,
        "details": details or {},
        "prev_hash": prev_hash,
    }
    payload_str = json.dumps(payload, sort_keys=True)
    entry_hash = _hash_entry(prev_hash, payload_str)
    line = f"{entry_hash}\t{payload_str}\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        try:
            os.fsync(f.fileno())
        except (AttributeError, OSError):
            pass


def read_audit(mem_dir: Path, max_entries: int = 1000) -> List[Dict[str, Any]]:
    """Read audit log entries (newest first). Each entry has entry_hash, prev_hash, timestamp, operation, details."""
    path = _log_path(mem_dir)
    if not path.exists():
        return []
    entries = []
    for line in reversed(path.read_text().strip().split("\n")):
        line = line.strip()
        if not line:
            continue
        if "\t" not in line:
            continue
        entry_hash, payload_str = line.split("\t", 1)
        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError:
            continue
        payload["entry_hash"] = entry_hash
        entries.append(payload)
        if len(entries) >= max_entries:
            break
    return entries


def verify_audit(mem_dir: Path) -> Tuple[bool, Optional[int]]:
    """
    Verify the audit log chain. Returns (valid, first_bad_index).
    first_bad_index is 0-based index of first entry that fails chain verification.
    """
    path = _log_path(mem_dir)
    if not path.exists():
        return (True, None)
    lines = path.read_text().strip().split("\n")
    prev_hash = ""
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        if "\t" not in line:
            return (False, i)
        entry_hash, payload_str = line.split("\t", 1)
        expected_hash = _hash_entry(prev_hash, payload_str)
        if not hmac.compare_digest(entry_hash, expected_hash):
            return (False, i)
        prev_hash = entry_hash
    return (True, None)
