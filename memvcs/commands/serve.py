"""
agmem serve - Start web UI server for browsing history.
"""

import argparse
import sys
from pathlib import Path


class ServeCommand:
    """Start the agmem web UI server."""

    name = "serve"
    help = "Start web UI for browsing memory history"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            "--port", "-p",
            type=int,
            default=8765,
            help="Port to bind (default: 8765)",
        )
        parser.add_argument(
            "--host",
            default="127.0.0.1",
            help="Host to bind (default: 127.0.0.1)",
        )

    @staticmethod
    def execute(args) -> int:
        try:
            import uvicorn
        except ImportError:
            print(
                "Error: Web UI requires fastapi and uvicorn. "
                "Install with: pip install agmem[web]",
                file=sys.stderr,
            )
            return 1

        from memvcs.commands.base import require_repo
        from memvcs.core.repository import Repository

        repo, code = require_repo()
        if code != 0:
            return code

        from memvcs.integrations.web_ui.server import create_app

        app = create_app(repo.root)
        print(f"agmem Web UI: http://{args.host}:{args.port}")
        uvicorn.run(app, host=args.host, port=args.port)
        return 0
