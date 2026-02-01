"""Tests for multi-agent trust store."""

import pytest
import tempfile
from pathlib import Path

from memvcs.core.trust import (
    load_trust_store,
    get_trust_level,
    set_trust,
    _key_id,
    _ensure_bytes,
    TRUST_LEVELS,
)


SAMPLE_PEM = b"-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyE=\n-----END PUBLIC KEY-----"


class TestEnsureBytes:
    """Test PEM normalization."""

    def test_ensure_bytes_from_bytes(self):
        out = _ensure_bytes(SAMPLE_PEM)
        assert out == SAMPLE_PEM

    def test_ensure_bytes_from_str(self):
        out = _ensure_bytes(SAMPLE_PEM.decode("utf-8"))
        assert out == SAMPLE_PEM


class TestKeyId:
    """Test key ID derivation."""

    def test_key_id_stable(self):
        assert _key_id(SAMPLE_PEM) == _key_id(SAMPLE_PEM)
        assert len(_key_id(SAMPLE_PEM)) == 16


class TestTrustStore:
    """Test trust store load/set/get."""

    def test_load_empty_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            entries = load_trust_store(Path(tmpdir))
            assert entries == []

    def test_set_and_get_trust_level(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mem_dir = Path(tmpdir)
            set_trust(mem_dir, SAMPLE_PEM, "full")
            level = get_trust_level(mem_dir, SAMPLE_PEM)
            assert level == "full"

    def test_set_trust_rejects_invalid_level(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="level must be one of"):
                set_trust(Path(tmpdir), SAMPLE_PEM, "invalid")

    def test_set_trust_rejects_oversized_pem(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            big_pem = b"x" * 9000
            with pytest.raises(ValueError, match="exceeds maximum size"):
                set_trust(Path(tmpdir), big_pem, "full")

    def test_get_trust_level_unknown_returns_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            level = get_trust_level(Path(tmpdir), SAMPLE_PEM)
            assert level is None

    def test_set_trust_accepts_str_pem(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mem_dir = Path(tmpdir)
            set_trust(mem_dir, SAMPLE_PEM.decode("utf-8"), "conditional")
            level = get_trust_level(mem_dir, SAMPLE_PEM)
            assert level == "conditional"
