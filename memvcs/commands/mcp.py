"""
agmem mcp - Run MCP server for Cursor/Claude integration.
"""

import argparse
import sys


class McpCommand:
    """Run the agmem MCP server for Cursor/Claude."""

    name = "mcp"
    help = "Run MCP server for Cursor/Claude memory integration"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            "--transport",
            choices=["stdio", "streamable-http"],
            default="stdio",
            help="Transport: stdio (default for Cursor/Claude) or streamable-http",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=8000,
            help="Port for streamable-http (default: 8000)",
        )

    @staticmethod
    def execute(args) -> int:
        try:
            from memvcs.integrations.mcp_server import _create_mcp_server

            mcp = _create_mcp_server()
        except ImportError as e:
            print(
                "Error: MCP support requires 'mcp' package (Python 3.10+). "
                "Install with: pip install agmem[mcp]",
                file=sys.stderr,
            )
            return 1

        try:
            if args.transport == "streamable-http":
                mcp.run(transport="streamable-http", port=args.port)
            else:
                mcp.run(transport="stdio")
        except TypeError:
            # Some MCP versions may not support port kwarg
            if args.transport == "streamable-http":
                mcp.run(transport="streamable-http")
            else:
                mcp.run(transport="stdio")
        except Exception as e:
            print(f"Error running MCP server: {e}", file=sys.stderr)
            return 1

        return 0
