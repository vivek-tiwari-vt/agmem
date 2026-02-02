"""
WebSocket support for real-time memory updates.

Provides live notifications for:
- File changes
- Commits
- Session events
- Agent activity
"""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

try:
    from fastapi import WebSocket, WebSocketDisconnect

    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False


class ConnectionManager:
    """Manages WebSocket connections and broadcasts."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.subscriptions: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        # Remove from all subscriptions
        for topic in self.subscriptions:
            self.subscriptions[topic].discard(websocket)

    def subscribe(self, websocket: WebSocket, topic: str):
        """Subscribe a connection to a topic."""
        if topic not in self.subscriptions:
            self.subscriptions[topic] = set()
        self.subscriptions[topic].add(websocket)

    def unsubscribe(self, websocket: WebSocket, topic: str):
        """Unsubscribe a connection from a topic."""
        if topic in self.subscriptions:
            self.subscriptions[topic].discard(websocket)

    async def send_personal(self, message: Dict[str, Any], websocket: WebSocket):
        """Send a message to a specific connection."""
        await websocket.send_json(message)

    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast a message to all connections."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)

    async def broadcast_to_topic(self, topic: str, message: Dict[str, Any]):
        """Broadcast a message to subscribers of a topic."""
        if topic not in self.subscriptions:
            return

        disconnected = []
        for connection in self.subscriptions[topic]:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)


# Global connection manager
manager = ConnectionManager()


class EventType:
    """Event type constants."""

    FILE_CHANGED = "file_changed"
    FILE_CREATED = "file_created"
    FILE_DELETED = "file_deleted"
    COMMIT = "commit"
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    AGENT_ACTIVITY = "agent_activity"
    ALERT = "alert"
    HEALTH_CHECK = "health_check"


def create_event(event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a standardized event message."""
    return {
        "type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }


async def emit_file_change(path: str, change_type: str):
    """Emit a file change event."""
    event = create_event(EventType.FILE_CHANGED, {"path": path, "change_type": change_type})
    await manager.broadcast_to_topic("files", event)
    await manager.broadcast_to_topic("all", event)


async def emit_commit(commit_hash: str, message: str, files: List[str]):
    """Emit a commit event."""
    event = create_event(
        EventType.COMMIT, {"hash": commit_hash, "message": message, "files": files}
    )
    await manager.broadcast_to_topic("commits", event)
    await manager.broadcast_to_topic("all", event)


async def emit_session_event(event_type: str, session_id: str, details: Dict[str, Any]):
    """Emit a session event."""
    event = create_event(event_type, {"session_id": session_id, **details})
    await manager.broadcast_to_topic("sessions", event)
    await manager.broadcast_to_topic("all", event)


async def emit_alert(alert_type: str, message: str, severity: str = "info"):
    """Emit an alert event."""
    event = create_event(
        EventType.ALERT, {"alert_type": alert_type, "message": message, "severity": severity}
    )
    await manager.broadcast_to_topic("alerts", event)
    await manager.broadcast_to_topic("all", event)


def add_websocket_routes(app):
    """Add WebSocket routes to a FastAPI app."""
    if not HAS_FASTAPI:
        return

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """Main WebSocket endpoint."""
        await manager.connect(websocket)

        # Subscribe to 'all' by default
        manager.subscribe(websocket, "all")

        try:
            while True:
                data = await websocket.receive_json()

                # Handle subscription messages
                if data.get("action") == "subscribe":
                    topic = data.get("topic", "all")
                    manager.subscribe(websocket, topic)
                    await manager.send_personal({"type": "subscribed", "topic": topic}, websocket)

                elif data.get("action") == "unsubscribe":
                    topic = data.get("topic")
                    if topic:
                        manager.unsubscribe(websocket, topic)
                        await manager.send_personal(
                            {"type": "unsubscribed", "topic": topic}, websocket
                        )

                elif data.get("action") == "ping":
                    await manager.send_personal(
                        {"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()},
                        websocket,
                    )

        except WebSocketDisconnect:
            manager.disconnect(websocket)

    @app.websocket("/ws/files")
    async def websocket_files(websocket: WebSocket):
        """WebSocket for file change events only."""
        await manager.connect(websocket)
        manager.subscribe(websocket, "files")

        try:
            while True:
                await websocket.receive_text()  # Keep connection alive
        except WebSocketDisconnect:
            manager.disconnect(websocket)

    @app.websocket("/ws/commits")
    async def websocket_commits(websocket: WebSocket):
        """WebSocket for commit events only."""
        await manager.connect(websocket)
        manager.subscribe(websocket, "commits")

        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket)


# Async helper for synchronous callers
def sync_emit_file_change(path: str, change_type: str):
    """Synchronous wrapper for file change emission."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(emit_file_change(path, change_type))
        else:
            loop.run_until_complete(emit_file_change(path, change_type))
    except RuntimeError:
        # No event loop - ignore
        pass
