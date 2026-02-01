"""Integration tests for IPFS remote push/pull via Remote class."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from memvcs.core.remote import Remote, _is_ipfs_remote
from memvcs.core.repository import Repository


class TestIPFSRemoteDetection:
    """Test IPFS URL detection."""

    def test_is_ipfs_remote_true(self):
        assert _is_ipfs_remote("ipfs://QmHash123")
        assert _is_ipfs_remote("ipfs://bafyHash456")

    def test_is_ipfs_remote_false(self):
        assert not _is_ipfs_remote("file:///tmp/repo")
        assert not _is_ipfs_remote("s3://bucket/repo")
        assert not _is_ipfs_remote("gs://bucket/repo")
        assert not _is_ipfs_remote("https://example.com")


class TestIPFSRemotePushPull:
    """Test IPFS push/pull through Remote class."""

    @patch("memvcs.core.ipfs_remote.push_to_ipfs")
    def test_push_to_ipfs_success(self, mock_push_to_ipfs):
        """Test pushing to IPFS via Remote.push()."""
        mock_push_to_ipfs.return_value = "QmTestCID123"

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            repo = Repository.init(repo_path)

            # Create a file in current/ directory
            test_file = repo_path / "current" / "test.txt"
            test_file.write_text("test content")
            repo.stage_file("test.txt")
            repo.commit("Test commit")

            # Set up IPFS remote
            remote = Remote(repo_path, "origin")
            remote.set_remote_url("ipfs://placeholder")

            # Push should call push_to_ipfs and return CID
            result = remote.push()

            assert "QmTestCID123" in result
            assert "WARNING" in result  # Should warn about pinning
            mock_push_to_ipfs.assert_called_once()

            # Verify remote URL was updated with new CID
            assert remote.get_remote_url() == "ipfs://QmTestCID123"

    @patch("memvcs.core.ipfs_remote.pull_from_ipfs")
    @patch("memvcs.core.ipfs_remote.parse_ipfs_url")
    def test_fetch_from_ipfs_success(self, mock_parse_url, mock_pull_from_ipfs):
        """Test fetching from IPFS via Remote.fetch()."""
        mock_parse_url.return_value = "QmTestCID123"
        mock_pull_from_ipfs.return_value = True

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            repo = Repository.init(repo_path)

            # Set up IPFS remote
            remote = Remote(repo_path, "origin")
            remote.set_remote_url("ipfs://QmTestCID123")

            # Fetch should call pull_from_ipfs
            result = remote.fetch()

            assert "QmTestCID123" in result
            mock_parse_url.assert_called_once_with("ipfs://QmTestCID123")
            mock_pull_from_ipfs.assert_called_once()

    @patch("memvcs.core.ipfs_remote.push_to_ipfs")
    def test_push_to_ipfs_failure(self, mock_push_to_ipfs):
        """Test push failure handling."""
        mock_push_to_ipfs.return_value = None  # Simulate failure

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            repo = Repository.init(repo_path)

            # Create a file in current/ directory
            test_file = repo_path / "current" / "test.txt"
            test_file.write_text("test content")
            repo.stage_file("test.txt")
            repo.commit("Test commit")

            # Set up IPFS remote
            remote = Remote(repo_path, "origin")
            remote.set_remote_url("ipfs://placeholder")

            # Push should raise ValueError on failure
            with pytest.raises(ValueError, match="Failed to push to IPFS gateway"):
                remote.push()

    @patch("memvcs.core.ipfs_remote.pull_from_ipfs")
    @patch("memvcs.core.ipfs_remote.parse_ipfs_url")
    def test_fetch_from_ipfs_failure(self, mock_parse_url, mock_pull_from_ipfs):
        """Test fetch failure handling."""
        mock_parse_url.return_value = "QmTestCID123"
        mock_pull_from_ipfs.return_value = False  # Simulate failure

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            repo = Repository.init(repo_path)

            # Set up IPFS remote
            remote = Remote(repo_path, "origin")
            remote.set_remote_url("ipfs://QmTestCID123")

            # Fetch should raise ValueError on failure
            with pytest.raises(ValueError, match="Failed to pull from IPFS"):
                remote.fetch()

    def test_push_no_commit(self):
        """Test push fails gracefully when no commits exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            repo = Repository.init(repo_path)

            # Set up IPFS remote without any commits
            remote = Remote(repo_path, "origin")
            remote.set_remote_url("ipfs://placeholder")

            # Push should raise ValueError
            with pytest.raises(ValueError, match="has no commit"):
                remote.push()
