"""
Compliance Dashboard - Privacy, Encryption, and Audit verification.

This module provides compliance monitoring capabilities:
- Privacy budget tracking (ε/δ for differential privacy)
- Encryption status verification
- Tamper detection via Merkle tree verification
- Audit trail analysis
"""

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class PrivacyBudget:
    """Tracks differential privacy budget consumption."""

    epsilon: float  # Privacy loss parameter
    delta: float  # Failure probability
    queries_made: int = 0
    budget_consumed: float = 0.0
    budget_limit: float = 1.0
    last_query: Optional[str] = None

    def consume(self, epsilon_cost: float) -> bool:
        """Consume privacy budget. Returns True if within limit."""
        if self.budget_consumed + epsilon_cost > self.budget_limit:
            return False
        self.budget_consumed += epsilon_cost
        self.queries_made += 1
        self.last_query = datetime.now(timezone.utc).isoformat()
        return True

    def remaining(self) -> float:
        """Get remaining privacy budget."""
        return max(0, self.budget_limit - self.budget_consumed)

    def is_exhausted(self) -> bool:
        """Check if budget is exhausted."""
        return self.budget_consumed >= self.budget_limit

    def to_dict(self) -> Dict[str, Any]:
        return {
            "epsilon": self.epsilon,
            "delta": self.delta,
            "queries_made": self.queries_made,
            "budget_consumed": self.budget_consumed,
            "budget_limit": self.budget_limit,
            "remaining": self.remaining(),
            "exhausted": self.is_exhausted(),
            "last_query": self.last_query,
        }


class PrivacyManager:
    """Manages privacy budgets for different data sources."""

    def __init__(self, mem_dir: Path):
        self.mem_dir = Path(mem_dir)
        self.privacy_file = self.mem_dir / "privacy.json"
        self._budgets: Dict[str, PrivacyBudget] = {}
        self._load()

    def _load(self) -> None:
        """Load privacy budgets from disk."""
        if self.privacy_file.exists():
            try:
                data = json.loads(self.privacy_file.read_text())
                for name, budget_data in data.get("budgets", {}).items():
                    self._budgets[name] = PrivacyBudget(
                        epsilon=budget_data["epsilon"],
                        delta=budget_data["delta"],
                        queries_made=budget_data.get("queries_made", 0),
                        budget_consumed=budget_data.get("budget_consumed", 0.0),
                        budget_limit=budget_data.get("budget_limit", 1.0),
                        last_query=budget_data.get("last_query"),
                    )
            except Exception:
                pass

    def _save(self) -> None:
        """Save privacy budgets to disk."""
        self.mem_dir.mkdir(parents=True, exist_ok=True)
        data = {"budgets": {name: b.to_dict() for name, b in self._budgets.items()}}
        self.privacy_file.write_text(json.dumps(data, indent=2))

    def create_budget(
        self, name: str, epsilon: float = 0.1, delta: float = 1e-5, limit: float = 1.0
    ) -> PrivacyBudget:
        """Create a new privacy budget."""
        budget = PrivacyBudget(epsilon=epsilon, delta=delta, budget_limit=limit)
        self._budgets[name] = budget
        self._save()
        return budget

    def consume(self, name: str, epsilon_cost: float) -> Tuple[bool, Optional[PrivacyBudget]]:
        """Consume budget for a data source. Returns (success, budget)."""
        budget = self._budgets.get(name)
        if not budget:
            return False, None
        success = budget.consume(epsilon_cost)
        self._save()
        return success, budget

    def get_budget(self, name: str) -> Optional[PrivacyBudget]:
        """Get a privacy budget by name."""
        return self._budgets.get(name)

    def get_all_budgets(self) -> Dict[str, PrivacyBudget]:
        """Get all privacy budgets."""
        return self._budgets.copy()

    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get data for privacy dashboard."""
        return {
            "budgets": [
                {"name": name, **budget.to_dict()} for name, budget in self._budgets.items()
            ],
            "total_queries": sum(b.queries_made for b in self._budgets.values()),
            "total_consumed": sum(b.budget_consumed for b in self._budgets.values()),
        }


@dataclass
class EncryptionStatus:
    """Status of an encrypted file."""

    path: str
    is_encrypted: bool
    algorithm: Optional[str] = None
    key_id: Optional[str] = None
    encrypted_at: Optional[str] = None
    can_decrypt: bool = False


class EncryptionVerifier:
    """Verifies encryption status of memory files."""

    ENCRYPTION_MARKERS = [b"-----BEGIN ENCRYPTED", b"$ENCRYPTED$", b"\x00AGMEM-ENC"]

    def __init__(self, mem_dir: Path, current_dir: Path):
        self.mem_dir = Path(mem_dir)
        self.current_dir = Path(current_dir)
        self.key_file = self.mem_dir / "encryption_keys.json"

    def check_file(self, filepath: Path) -> EncryptionStatus:
        """Check encryption status of a file."""
        if not filepath.exists():
            return EncryptionStatus(path=str(filepath), is_encrypted=False)

        try:
            content = filepath.read_bytes()[:100]
            is_encrypted = any(marker in content for marker in self.ENCRYPTION_MARKERS)

            if is_encrypted:
                algorithm = self._detect_algorithm(content)
                return EncryptionStatus(
                    path=str(filepath),
                    is_encrypted=True,
                    algorithm=algorithm,
                    can_decrypt=self._can_decrypt(filepath),
                )
            else:
                return EncryptionStatus(
                    path=str(filepath),
                    is_encrypted=False,
                )
        except Exception:
            return EncryptionStatus(path=str(filepath), is_encrypted=False)

    def _detect_algorithm(self, content: bytes) -> str:
        """Detect encryption algorithm from header."""
        if b"AES-256" in content:
            return "AES-256-GCM"
        elif b"CHACHA20" in content:
            return "ChaCha20-Poly1305"
        elif b"FERNET" in content:
            return "Fernet"
        return "Unknown"

    def _can_decrypt(self, filepath: Path) -> bool:
        """Check if we have the key to decrypt."""
        if not self.key_file.exists():
            return False
        # Simplified check - just verify key file exists
        return True

    def scan_directory(self) -> Dict[str, Any]:
        """Scan current directory for encryption status."""
        results = {"encrypted": [], "unencrypted": [], "errors": []}

        for filepath in self.current_dir.rglob("*"):
            if filepath.is_file():
                try:
                    status = self.check_file(filepath)
                    if status.is_encrypted:
                        results["encrypted"].append(status)
                    else:
                        results["unencrypted"].append(status)
                except Exception as e:
                    results["errors"].append({"path": str(filepath), "error": str(e)})

        return {
            "total": len(results["encrypted"]) + len(results["unencrypted"]),
            "encrypted_count": len(results["encrypted"]),
            "unencrypted_count": len(results["unencrypted"]),
            "error_count": len(results["errors"]),
            "encrypted_files": [e.path for e in results["encrypted"]],
            "encryption_coverage": len(results["encrypted"])
            / max(1, len(results["encrypted"]) + len(results["unencrypted"]))
            * 100,
        }


class TamperDetector:
    """Detects tampering via Merkle tree verification."""

    def __init__(self, mem_dir: Path):
        self.mem_dir = Path(mem_dir)
        self.merkle_file = self.mem_dir / "merkle_root.json"

    def compute_file_hash(self, filepath: Path) -> str:
        """Compute SHA-256 hash of a file."""
        hasher = hashlib.sha256()
        try:
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception:
            return ""

    def compute_merkle_root(self, file_hashes: List[str]) -> str:
        """Compute Merkle root from file hashes."""
        if not file_hashes:
            return hashlib.sha256(b"").hexdigest()

        # Pad to power of 2
        while len(file_hashes) & (len(file_hashes) - 1):
            file_hashes.append(file_hashes[-1])

        # Build tree
        level = file_hashes
        while len(level) > 1:
            next_level = []
            for i in range(0, len(level), 2):
                combined = level[i] + level[i + 1]
                next_level.append(hashlib.sha256(combined.encode()).hexdigest())
            level = next_level

        return level[0]

    def store_merkle_state(self, directory: Path) -> Dict[str, Any]:
        """Store current Merkle state for later verification."""
        file_hashes = []
        file_paths = []

        for filepath in sorted(directory.rglob("*")):
            if filepath.is_file():
                file_hash = self.compute_file_hash(filepath)
                if file_hash:
                    file_hashes.append(file_hash)
                    file_paths.append(str(filepath.relative_to(directory)))

        merkle_root = self.compute_merkle_root(file_hashes)

        state = {
            "merkle_root": merkle_root,
            "file_count": len(file_hashes),
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "file_hashes": dict(zip(file_paths, file_hashes)),
        }

        self.mem_dir.mkdir(parents=True, exist_ok=True)
        self.merkle_file.write_text(json.dumps(state, indent=2))

        return state

    def verify_integrity(self, directory: Path) -> Dict[str, Any]:
        """Verify current state against stored Merkle root."""
        if not self.merkle_file.exists():
            return {"verified": False, "error": "No stored Merkle state found"}

        stored = json.loads(self.merkle_file.read_text())
        stored_hashes = stored.get("file_hashes", {})

        current_hashes = {}
        for filepath in sorted(directory.rglob("*")):
            if filepath.is_file():
                rel_path = str(filepath.relative_to(directory))
                current_hashes[rel_path] = self.compute_file_hash(filepath)

        # Compare
        modified = []
        added = []
        deleted = []

        for path, hash_value in current_hashes.items():
            if path not in stored_hashes:
                added.append(path)
            elif stored_hashes[path] != hash_value:
                modified.append(path)

        for path in stored_hashes:
            if path not in current_hashes:
                deleted.append(path)

        current_root = self.compute_merkle_root(list(current_hashes.values()))

        return {
            "verified": len(modified) == 0 and len(added) == 0 and len(deleted) == 0,
            "stored_root": stored.get("merkle_root"),
            "current_root": current_root,
            "roots_match": stored.get("merkle_root") == current_root,
            "modified_files": modified,
            "added_files": added,
            "deleted_files": deleted,
            "stored_at": stored.get("computed_at"),
        }


class AuditAnalyzer:
    """Analyzes audit trail for compliance."""

    def __init__(self, mem_dir: Path):
        self.mem_dir = Path(mem_dir)
        self.audit_file = self.mem_dir / "audit.log"

    def load_audit_entries(self) -> List[Dict[str, Any]]:
        """Load audit log entries."""
        if not self.audit_file.exists():
            return []

        entries = []
        try:
            for line in self.audit_file.read_text().strip().split("\n"):
                if line:
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        pass
        except Exception:
            pass

        return entries

    def verify_chain(self) -> Dict[str, Any]:
        """Verify audit chain integrity."""
        entries = self.load_audit_entries()
        if not entries:
            return {"valid": True, "entries": 0, "message": "No audit entries"}

        valid = True
        errors = []
        prev_hash = None

        for i, entry in enumerate(entries):
            # Verify hash chain
            entry_hash = entry.get("hash")
            entry_prev = entry.get("prev_hash")

            if i > 0 and entry_prev != prev_hash:
                valid = False
                errors.append(f"Chain break at entry {i}")

            prev_hash = entry_hash

        return {
            "valid": valid,
            "entries": len(entries),
            "errors": errors,
            "first_entry": entries[0].get("timestamp") if entries else None,
            "last_entry": entries[-1].get("timestamp") if entries else None,
        }

    def get_statistics(self) -> Dict[str, Any]:
        """Get audit statistics."""
        entries = self.load_audit_entries()

        operations = {}
        agents = {}
        by_day = {}

        for entry in entries:
            op = entry.get("operation", "unknown")
            operations[op] = operations.get(op, 0) + 1

            agent = entry.get("agent", "unknown")
            agents[agent] = agents.get(agent, 0) + 1

            ts = entry.get("timestamp", "")[:10]
            if ts:
                by_day[ts] = by_day.get(ts, 0) + 1

        return {
            "total_entries": len(entries),
            "operations": operations,
            "agents": agents,
            "by_day": by_day,
        }


# --- Dashboard Helper ---


def get_compliance_dashboard(mem_dir: Path, current_dir: Path) -> Dict[str, Any]:
    """Get data for compliance dashboard."""
    privacy_mgr = PrivacyManager(mem_dir)
    encryption_verifier = EncryptionVerifier(mem_dir, current_dir)
    tamper_detector = TamperDetector(mem_dir)
    audit_analyzer = AuditAnalyzer(mem_dir)

    return {
        "privacy": privacy_mgr.get_dashboard_data(),
        "encryption": encryption_verifier.scan_directory(),
        "integrity": tamper_detector.verify_integrity(current_dir),
        "audit": {
            "chain_valid": audit_analyzer.verify_chain(),
            "statistics": audit_analyzer.get_statistics(),
        },
    }
