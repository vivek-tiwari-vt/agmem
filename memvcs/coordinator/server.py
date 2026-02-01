"""
Minimal Federated Coordinator Server for agmem.

Implements the coordinator API from docs/FEDERATED.md:
- POST /push: Accept agent summaries
- GET /pull: Return merged summaries

This is a reference implementation. For production:
- Add authentication (API keys, OAuth)
- Use persistent storage (PostgreSQL, Redis)
- Add rate limiting
- Enable HTTPS
- Scale horizontally

Install: pip install "agmem[coordinator]"
Run: uvicorn memvcs.coordinator.server:app --host 0.0.0.0 --port 8000
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from pathlib import Path
import json
import hashlib

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, Field

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

    # Stub for when FastAPI not installed
    class BaseModel:
        pass

    def Field(*args, **kwargs):
        return None


# Storage: In-memory for simplicity (use Redis/PostgreSQL for production)
summaries_store: Dict[str, List[Dict[str, Any]]] = {}
metadata_store: Dict[str, Any] = {
    "coordinator_version": "0.1.6",
    "started_at": datetime.now(timezone.utc).isoformat(),
    "total_pushes": 0,
    "total_agents": 0,
}


class AgentSummary(BaseModel):
    """Agent summary for federated push."""

    agent_id: str = Field(..., description="Unique agent identifier")
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    topic_counts: Dict[str, int] = Field(default_factory=dict, description="Topic -> count")
    fact_hashes: List[str] = Field(default_factory=list, description="SHA-256 hashes of facts")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Optional metadata")


class PushRequest(BaseModel):
    """Request body for /push endpoint."""

    summary: AgentSummary


class PullResponse(BaseModel):
    """Response body for /pull endpoint."""

    merged_topic_counts: Dict[str, int]
    unique_fact_hashes: List[str]
    contributing_agents: int
    last_updated: str
    metadata: Optional[Dict[str, Any]] = None


if FASTAPI_AVAILABLE:
    app = FastAPI(
        title="agmem Federated Coordinator",
        description="Minimal coordinator for federated agent memory collaboration",
        version="0.1.6",
    )

    @app.get("/")
    async def root():
        """Health check and API info."""
        return {
            "service": "agmem-coordinator",
            "version": metadata_store["coordinator_version"],
            "status": "running",
            "endpoints": {
                "push": "POST /push",
                "pull": "GET /pull",
                "health": "GET /health",
            },
            "started_at": metadata_store["started_at"],
            "total_pushes": metadata_store["total_pushes"],
            "total_agents": metadata_store["total_agents"],
        }

    @app.get("/health")
    async def health():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @app.post("/push", response_model=Dict[str, Any])
    async def push(request: PushRequest):
        """
        Accept agent summary and store it.

        Returns:
            Confirmation with push timestamp
        """
        summary = request.summary

        # Validate timestamp
        try:
            datetime.fromisoformat(summary.timestamp.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid timestamp format (expected ISO 8601)"
            )

        # Store summary by agent_id
        if summary.agent_id not in summaries_store:
            summaries_store[summary.agent_id] = []
            metadata_store["total_agents"] += 1

        summaries_store[summary.agent_id].append(summary.dict())
        metadata_store["total_pushes"] += 1

        return {
            "status": "accepted",
            "agent_id": summary.agent_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": f"Summary from {summary.agent_id} stored successfully",
        }

    @app.get("/pull", response_model=PullResponse)
    async def pull():
        """
        Return merged summaries from all agents.

        Returns:
            Aggregated topic counts, unique fact hashes, contributing agent count
        """
        if not summaries_store:
            return PullResponse(
                merged_topic_counts={},
                unique_fact_hashes=[],
                contributing_agents=0,
                last_updated=datetime.now(timezone.utc).isoformat(),
            )

        # Merge topic counts across all agents
        merged_topics: Dict[str, int] = {}
        all_fact_hashes = set()
        latest_timestamp = None

        for agent_id, summaries in summaries_store.items():
            for summary in summaries:
                # Aggregate topic counts
                for topic, count in summary.get("topic_counts", {}).items():
                    merged_topics[topic] = merged_topics.get(topic, 0) + count

                # Collect unique fact hashes
                for fact_hash in summary.get("fact_hashes", []):
                    all_fact_hashes.add(fact_hash)

                # Track latest update
                ts = summary.get("timestamp")
                if ts:
                    if latest_timestamp is None or ts > latest_timestamp:
                        latest_timestamp = ts

        return PullResponse(
            merged_topic_counts=merged_topics,
            unique_fact_hashes=sorted(list(all_fact_hashes)),
            contributing_agents=len(summaries_store),
            last_updated=latest_timestamp or datetime.now(timezone.utc).isoformat(),
            metadata={
                "total_facts": len(all_fact_hashes),
                "total_topics": len(merged_topics),
            },
        )

    @app.delete("/admin/reset")
    async def admin_reset(request: Request):
        """
        Admin endpoint to reset all stored data.
        In production, protect this with authentication!
        """
        summaries_store.clear()
        metadata_store["total_pushes"] = 0
        metadata_store["total_agents"] = 0
        metadata_store["started_at"] = datetime.now(timezone.utc).isoformat()

        return {
            "status": "reset",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

else:
    # Stub when FastAPI not available
    app = None
    print("FastAPI not available. Install with: pip install 'agmem[coordinator]'")


if __name__ == "__main__":
    if not FASTAPI_AVAILABLE:
        print("Error: FastAPI not installed")
        print("Install with: pip install 'fastapi[all]' uvicorn")
        exit(1)

    import uvicorn

    print("Starting agmem Federated Coordinator...")
    print("API docs: http://localhost:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000)
