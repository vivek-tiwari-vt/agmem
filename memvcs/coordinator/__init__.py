"""Coordinator package for federated collaboration."""

from .server import app, FASTAPI_AVAILABLE

__all__ = ["app", "FASTAPI_AVAILABLE"]
