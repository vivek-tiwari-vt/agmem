"""
Tests for the Web UI API endpoints.
"""

import json
import pytest
import tempfile
from pathlib import Path

from memvcs.core.repository import Repository


@pytest.fixture
def test_repo():
    """Create a test repository with some content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        repo = Repository.init(repo_path, author_name="Test", author_email="test@example.com")

        # Create some memory content
        semantic_dir = repo.current_dir / "semantic"
        semantic_dir.mkdir(parents=True, exist_ok=True)
        (semantic_dir / "test-memory.md").write_text("# Test Memory\n\nThis is test content for search.")

        episodic_dir = repo.current_dir / "episodic"
        episodic_dir.mkdir(parents=True, exist_ok=True)
        (episodic_dir / "session1.md").write_text("# Session 1\n\nSome episodic content.")

        # Stage and commit
        repo.stage_directory("")
        repo.commit("Initial test commit")

        yield repo


class TestWebUIServer:
    """Test web UI server creation."""

    def test_create_app(self, test_repo):
        """Test creating the FastAPI app."""
        from memvcs.integrations.web_ui.server import create_app

        app = create_app(test_repo.root)
        assert app is not None
        assert app.title == "agmem"


class TestAPILog:
    """Test /api/log endpoint."""

    def test_api_log(self, test_repo):
        """Test getting commit log."""
        from fastapi.testclient import TestClient
        from memvcs.integrations.web_ui.server import create_app

        app = create_app(test_repo.root)
        client = TestClient(app)

        response = client.get("/api/log")
        assert response.status_code == 200
        data = response.json()
        assert "commits" in data
        assert len(data["commits"]) >= 1


class TestAPICommit:
    """Test /api/commit/{hash} endpoint."""

    def test_api_commit(self, test_repo):
        """Test getting a single commit."""
        from fastapi.testclient import TestClient
        from memvcs.integrations.web_ui.server import create_app

        app = create_app(test_repo.root)
        client = TestClient(app)

        # First get the commit hash
        log_response = client.get("/api/log")
        commit_hash = log_response.json()["commits"][0]["hash"]

        # Then get commit details
        response = client.get(f"/api/commit/{commit_hash}")
        assert response.status_code == 200
        data = response.json()
        assert data["hash"] == commit_hash
        assert "message" in data
        assert "files" in data
        assert "parents" in data

    def test_api_commit_invalid(self, test_repo):
        """Test getting an invalid commit."""
        from fastapi.testclient import TestClient
        from memvcs.integrations.web_ui.server import create_app

        app = create_app(test_repo.root)
        client = TestClient(app)

        response = client.get("/api/commit/invalid123")
        assert response.status_code == 400


class TestAPISearch:
    """Test /api/search endpoint."""

    def test_api_search(self, test_repo):
        """Test searching memory."""
        from fastapi.testclient import TestClient
        from memvcs.integrations.web_ui.server import create_app

        app = create_app(test_repo.root)
        client = TestClient(app)

        response = client.get("/api/search?q=test")
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert data["count"] >= 1

    def test_api_search_by_type(self, test_repo):
        """Test searching by memory type."""
        from fastapi.testclient import TestClient
        from memvcs.integrations.web_ui.server import create_app

        app = create_app(test_repo.root)
        client = TestClient(app)

        response = client.get("/api/search?q=test&memory_type=semantic")
        assert response.status_code == 200
        data = response.json()
        assert all(r["memory_type"] == "semantic" for r in data["results"])

    def test_api_search_short_query(self, test_repo):
        """Test that short queries are rejected."""
        from fastapi.testclient import TestClient
        from memvcs.integrations.web_ui.server import create_app

        app = create_app(test_repo.root)
        client = TestClient(app)

        response = client.get("/api/search?q=a")
        assert response.status_code == 400


class TestAPIStatus:
    """Test /api/status endpoint."""

    def test_api_status(self, test_repo):
        """Test getting repository status."""
        from fastapi.testclient import TestClient
        from memvcs.integrations.web_ui.server import create_app

        app = create_app(test_repo.root)
        client = TestClient(app)

        response = client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        assert "branch" in data
        assert "is_clean" in data


class TestAPITrust:
    """Test /api/trust endpoint."""

    def test_api_trust(self, test_repo):
        """Test getting trust graph."""
        from fastapi.testclient import TestClient
        from memvcs.integrations.web_ui.server import create_app

        app = create_app(test_repo.root)
        client = TestClient(app)

        response = client.get("/api/trust")
        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data
        assert "links" in data


class TestAPIPrivacy:
    """Test /api/privacy endpoint."""

    def test_api_privacy(self, test_repo):
        """Test getting privacy budget."""
        from fastapi.testclient import TestClient
        from memvcs.integrations.web_ui.server import create_app

        app = create_app(test_repo.root)
        client = TestClient(app)

        response = client.get("/api/privacy")
        assert response.status_code == 200
        data = response.json()
        assert "epsilon_used" in data
        assert "epsilon_limit" in data


class TestAPIAudit:
    """Test /api/audit endpoint."""

    def test_api_audit(self, test_repo):
        """Test getting audit log."""
        from fastapi.testclient import TestClient
        from memvcs.integrations.web_ui.server import create_app

        app = create_app(test_repo.root)
        client = TestClient(app)

        response = client.get("/api/audit")
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data


class TestAPITree:
    """Test /api/tree/{commit_hash} endpoint."""

    def test_api_tree(self, test_repo):
        """Test getting tree for a commit."""
        from fastapi.testclient import TestClient
        from memvcs.integrations.web_ui.server import create_app

        app = create_app(test_repo.root)
        client = TestClient(app)

        # Get commit hash first
        log_response = client.get("/api/log")
        commit_hash = log_response.json()["commits"][0]["hash"]

        response = client.get(f"/api/tree/{commit_hash}")
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data


class TestAPIDiff:
    """Test /api/diff endpoint."""

    def test_api_diff(self, test_repo):
        """Test getting diff between commits."""
        from fastapi.testclient import TestClient
        from memvcs.integrations.web_ui.server import create_app

        # Create a second commit
        (test_repo.current_dir / "semantic" / "new-file.md").write_text("# New File")
        test_repo.stage_directory("")
        test_repo.commit("Second commit")

        app = create_app(test_repo.root)
        client = TestClient(app)

        response = client.get("/api/diff?base=HEAD~1&head=HEAD")
        assert response.status_code == 200
        data = response.json()
        assert "files" in data
