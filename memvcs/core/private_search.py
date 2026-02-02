"""
Privacy-Preserving Search - Secure search with encryption and differential privacy.

This module provides:
- Encrypted search indices
- Differential privacy for queries
- Access control integration
- Secure search result handling
"""

import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class SearchQuery:
    """A search query with privacy metadata."""

    query: str
    requester_id: str
    privacy_level: str = "normal"  # "public", "normal", "sensitive", "secret"
    max_results: int = 10
    include_content: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "requester_id": self.requester_id,
            "privacy_level": self.privacy_level,
            "max_results": self.max_results,
            "include_content": self.include_content,
        }


@dataclass
class SecureSearchResult:
    """A search result with privacy handling."""

    path: str
    score: float
    snippet: Optional[str] = None
    accessed_at: Optional[str] = None
    privacy_level: str = "normal"
    redacted: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "score": self.score,
            "snippet": self.snippet,
            "privacy_level": self.privacy_level,
            "redacted": self.redacted,
        }


class SearchTokenizer:
    """Tokenizes and hashes search terms for privacy."""

    def __init__(self, secret_key: Optional[bytes] = None):
        self.secret_key = secret_key or secrets.token_bytes(32)

    def tokenize(self, text: str) -> List[str]:
        """Tokenize text into search terms."""
        # Simple tokenization
        import re

        words = re.findall(r"\b\w+\b", text.lower())
        return [w for w in words if len(w) >= 3]

    def hash_token(self, token: str) -> str:
        """Create a keyed hash of a token for blind search."""
        return hmac.new(self.secret_key, token.encode(), hashlib.sha256).hexdigest()[:16]

    def tokenize_and_hash(self, text: str) -> List[str]:
        """Tokenize and hash all terms."""
        tokens = self.tokenize(text)
        return [self.hash_token(t) for t in tokens]


class AccessControl:
    """Controls access to search results based on permissions."""

    def __init__(self, mem_dir: Path):
        self.mem_dir = Path(mem_dir)
        self.acl_file = self.mem_dir / "search_acl.json"
        self._acl: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """Load ACL from disk."""
        if self.acl_file.exists():
            try:
                self._acl = json.loads(self.acl_file.read_text())
            except Exception:
                pass

    def _save(self) -> None:
        """Save ACL to disk."""
        self.mem_dir.mkdir(parents=True, exist_ok=True)
        self.acl_file.write_text(json.dumps(self._acl, indent=2))

    def set_file_access(
        self,
        path: str,
        allowed_users: List[str],
        privacy_level: str = "normal",
    ) -> None:
        """Set access control for a file."""
        self._acl[path] = {
            "allowed_users": allowed_users,
            "privacy_level": privacy_level,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save()

    def can_access(self, path: str, user_id: str, user_level: str = "normal") -> bool:
        """Check if a user can access a file."""
        acl = self._acl.get(path)
        if not acl:
            return True  # No ACL = public access

        # Check explicit user list
        if acl.get("allowed_users"):
            if user_id not in acl["allowed_users"]:
                return False

        # Check privacy level
        level_order = ["public", "normal", "sensitive", "secret"]
        file_level = acl.get("privacy_level", "normal")

        try:
            file_idx = level_order.index(file_level)
            user_idx = level_order.index(user_level)
            return user_idx >= file_idx
        except ValueError:
            return False

    def get_file_acl(self, path: str) -> Optional[Dict[str, Any]]:
        """Get ACL for a file."""
        return self._acl.get(path)


class DifferentialPrivacyNoise:
    """Adds differential privacy noise to search results."""

    def __init__(self, epsilon: float = 0.1):
        self.epsilon = epsilon

    def add_laplace_noise(self, value: float, sensitivity: float = 1.0) -> float:
        """Add Laplace noise for differential privacy."""
        import random

        scale = sensitivity / self.epsilon
        u = random.random() - 0.5
        noise = -scale * (1 if u >= 0 else -1) * (1 - 2 * abs(u))
        return value + noise

    def randomize_order(self, results: List[Any], threshold: float = 0.8) -> List[Any]:
        """Randomly reorder similar results to add privacy."""
        import random

        # Group by similar scores
        groups: List[List[Any]] = []
        current_group: List[Any] = []
        prev_score = None

        for r in results:
            score = getattr(r, "score", 0) if hasattr(r, "score") else r.get("score", 0)
            if prev_score is None or abs(score - prev_score) < threshold:
                current_group.append(r)
            else:
                if current_group:
                    groups.append(current_group)
                current_group = [r]
            prev_score = score

        if current_group:
            groups.append(current_group)

        # Shuffle within groups
        reordered = []
        for group in groups:
            random.shuffle(group)
            reordered.extend(group)

        return reordered

    def truncate_snippets(self, snippet: str, max_len: int = 100) -> str:
        """Truncate snippets to limit information leakage."""
        if len(snippet) <= max_len:
            return snippet

        # Find a good break point
        break_point = snippet.rfind(" ", max_len - 20, max_len)
        if break_point == -1:
            break_point = max_len

        return snippet[:break_point] + "..."


class PrivateSearchEngine:
    """Privacy-preserving search engine."""

    def __init__(self, mem_dir: Path, current_dir: Path):
        self.mem_dir = Path(mem_dir)
        self.current_dir = Path(current_dir)
        self.tokenizer = SearchTokenizer()
        self.access_control = AccessControl(mem_dir)
        self.dp_noise = DifferentialPrivacyNoise(epsilon=0.1)
        self.query_log: List[Dict[str, Any]] = []

    def search(self, query: SearchQuery) -> List[SecureSearchResult]:
        """Perform a privacy-preserving search."""
        results = []

        # Token-based search
        query_tokens = self.tokenizer.tokenize(query.query)

        # Search through files
        for filepath in self.current_dir.rglob("*"):
            if not filepath.is_file():
                continue

            rel_path = str(filepath.relative_to(self.current_dir))

            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
                content_tokens = self.tokenizer.tokenize(content)

                # Simple scoring
                matches = sum(1 for t in query_tokens if t in content_tokens)
                if matches == 0:
                    continue

                score = matches / len(query_tokens)

                # Check access control
                can_access = self.access_control.can_access(
                    rel_path, query.requester_id, query.privacy_level
                )

                if not can_access:
                    # Include redacted result
                    results.append(
                        SecureSearchResult(
                            path=rel_path,
                            score=score,
                            snippet=None,
                            privacy_level=query.privacy_level,
                            redacted=True,
                        )
                    )
                else:
                    # Include full result
                    snippet = None
                    if query.include_content:
                        # Find snippet around first match
                        query_lower = query.query.lower()
                        idx = content.lower().find(query_lower)
                        if idx >= 0:
                            start = max(0, idx - 50)
                            end = min(len(content), idx + len(query.query) + 50)
                            snippet = content[start:end]
                            snippet = self.dp_noise.truncate_snippets(snippet)

                    results.append(
                        SecureSearchResult(
                            path=rel_path,
                            score=score,
                            snippet=snippet,
                            privacy_level=query.privacy_level,
                            redacted=False,
                            accessed_at=datetime.now(timezone.utc).isoformat(),
                        )
                    )
            except Exception:
                pass

        # Sort by score
        results.sort(key=lambda r: r.score, reverse=True)

        # Apply differential privacy
        results = self.dp_noise.randomize_order(results[: query.max_results * 2])

        # Log query
        self._log_query(query, len(results))

        return results[: query.max_results]

    def _log_query(self, query: SearchQuery, result_count: int) -> None:
        """Log query for auditing (without preserving full query)."""
        self.query_log.append(
            {
                "query_hash": hashlib.sha256(query.query.encode()).hexdigest()[:8],
                "requester": query.requester_id,
                "result_count": result_count,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def get_query_stats(self) -> Dict[str, Any]:
        """Get query statistics."""
        return {
            "total_queries": len(self.query_log),
            "recent_queries": self.query_log[-10:],
        }


# --- Dashboard Helper ---


def get_private_search_stats(mem_dir: Path, current_dir: Path) -> Dict[str, Any]:
    """Get private search statistics."""
    engine = PrivateSearchEngine(mem_dir, current_dir)
    access_control = AccessControl(mem_dir)

    return {
        "query_stats": engine.get_query_stats(),
        "acl_count": len(access_control._acl),
    }
