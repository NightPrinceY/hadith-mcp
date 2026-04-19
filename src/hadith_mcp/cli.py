"""CLI entry: run the MCP server (stdio or HTTP)."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv


def main() -> int:
    p = argparse.ArgumentParser(description="Hadith MCP server (FastMCP)")
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="YAML config (optional). Default: env HADITH_MCP_DB_PATH or ./data/hadith.db",
    )
    p.add_argument(
        "--transport",
        default="stdio",
        choices=("stdio", "http", "sse", "streamable-http"),
        help="MCP transport (default: stdio for Cursor / Claude Desktop)",
    )
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        help="Python log level for hadith_mcp.* loggers",
    )
    args = p.parse_args()
    load_dotenv()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s %(name)s %(message)s",
    )

    from hadith_mcp.server import build_server

    server = build_server(config_yaml=args.config)
    try:
        server.run(transport=args.transport)
    except KeyboardInterrupt:
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
