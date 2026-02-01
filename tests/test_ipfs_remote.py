"""Tests for IPFS remote (push/pull via gateway)."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from memvcs.core.ipfs_remote import (
    parse_ipfs_url,
    push_to_ipfs,
    pull_from_ipfs,
    _bundle_objects,
    _unbundle_objects,
)
from memvcs.core.objects import ObjectStore


class TestParseIpfsUrl:
    """Test parse_ipfs_url."""

    def test_parse_ipfs_url_returns_cid(self):
        assert parse_ipfs_url("ipfs://QmXXX") == "QmXXX"
        assert parse_ipfs_url("ipfs://QmXXX/path") == "QmXXX"

    def test_parse_ipfs_url_invalid_returns_none(self):
        assert parse_ipfs_url("http://example.com") is None
        assert parse_ipfs_url("") is None


class TestBundleUnbundle:
    """Test bundle/unbundle objects (no network)."""

    def test_bundle_and_unbundle_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            objects_dir = Path(tmpdir)
            store = ObjectStore(objects_dir)
            h1 = store.store(b"hello", "blob")
            h2 = store.store(b"world", "blob")
            bundle = _bundle_objects(store, {h1, h2})
            assert len(bundle) > 4
            out_dir = Path(tmpdir) / "out"
            out_dir.mkdir()
            written = _unbundle_objects(bundle, out_dir)
            assert written == 2
            store2 = ObjectStore(out_dir)
            content1 = store2.retrieve(h1, "blob")
            assert content1 == b"hello"


class TestPushPullWithMockGateway:
    """Test push_to_ipfs/pull_from_ipfs with mock HTTP."""

    def test_push_returns_none_when_no_reachable_objects(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            objects_dir = Path(tmpdir)
            for t in ["blob", "tree", "commit"]:
                (objects_dir / t).mkdir(parents=True, exist_ok=True)
            cid = push_to_ipfs(objects_dir, "main", "nonexistent", gateway_url="http://localhost")
            assert cid is None

    def test_pull_returns_false_for_invalid_response(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("urllib.request.urlopen") as mock_open:
                mock_open.side_effect = Exception("network error")
                ok = pull_from_ipfs(Path(tmpdir), "QmXXX", gateway_url="http://localhost")
            assert ok is False
