"""Tests for tamper-evident audit trail."""

import pytest
import tempfile
from pathlib import Path

from memvcs.core.audit import (
    append_audit,
    read_audit,
    verify_audit,
    _hash_entry,
    _get_previous_hash,
    _log_path,
)


class TestAuditAppendRead:
    """Test append and read audit log."""

    def test_append_and_read_single(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mem_dir = Path(tmpdir)
            append_audit(mem_dir, "init", {"branch": "main"})
            entries = read_audit(mem_dir, max_entries=10)
            assert len(entries) == 1
            assert entries[0]["operation"] == "init"
            assert entries[0]["details"].get("branch") == "main"
            assert "entry_hash" in entries[0]
            assert "timestamp" in entries[0]

    def test_append_multiple_and_read_newest_first(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mem_dir = Path(tmpdir)
            append_audit(mem_dir, "op1", {"x": 1})
            append_audit(mem_dir, "op2", {"x": 2})
            entries = read_audit(mem_dir, max_entries=10)
            assert len(entries) == 2
            assert entries[0]["operation"] == "op2"
            assert entries[1]["operation"] == "op1"

    def test_read_empty_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            entries = read_audit(Path(tmpdir), max_entries=10)
            assert entries == []


class TestAuditVerify:
    """Test audit chain verification."""

    def test_verify_valid_chain(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mem_dir = Path(tmpdir)
            append_audit(mem_dir, "a", {})
            append_audit(mem_dir, "b", {})
            valid, first_bad = verify_audit(mem_dir)
            assert valid is True
            assert first_bad is None

    def test_verify_empty_is_valid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            valid, first_bad = verify_audit(Path(tmpdir))
            assert valid is True
            assert first_bad is None

    def test_verify_tampered_chain_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mem_dir = Path(tmpdir)
            append_audit(mem_dir, "a", {})
            append_audit(mem_dir, "b", {})
            log_path = _log_path(mem_dir)
            lines = log_path.read_text().strip().split("\n")
            # Corrupt second line (change payload)
            lines[1] = lines[1].split("\t", 1)[0] + "\t" + '{"timestamp":"x","operation":"b","details":{},"prev_hash":"y"}'
            log_path.write_text("\n".join(lines) + "\n")
            valid, first_bad = verify_audit(mem_dir)
            assert valid is False
            assert first_bad == 1


class TestHashEntry:
    """Test hash computation."""

    def test_hash_entry_deterministic(self):
        h1 = _hash_entry("prev", '{"x":1}')
        h2 = _hash_entry("prev", '{"x":1}')
        assert h1 == h2
        assert len(h1) == 64

    def test_hash_entry_different_input_different_output(self):
        h1 = _hash_entry("prev1", "payload1")
        h2 = _hash_entry("prev2", "payload2")
        assert h1 != h2
