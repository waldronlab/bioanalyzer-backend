#!/usr/bin/env python3
"""Main entry point for BioAnalyzer Package API server."""

import sys
import os
import argparse
import traceback
from pathlib import Path

# Import errors are usually import errors, not generic exceptions
try:
    from app.api.app import app
except ImportError as e:
    print(f"Failed to import application: {e}")
    print("\nPossible causes:")
    print("  1. Missing dependencies - run: pip install -r requirements.txt")
    print("  2. Syntax errors in application code")
    print("  3. Missing environment variables")
    traceback.print_exc()
    sys.exit(1)
except SyntaxError as e:
    print(f"Syntax error in application code: {e}")
    traceback.print_exc()
    sys.exit(1)


def _should_reload(args: argparse.Namespace) -> bool:
    """Determine if auto-reload should be enabled."""
    if args.reload:
        return True
    reload_env = os.getenv("UVICORN_RELOAD", "false").lower()
    return reload_env in ("true", "1", "yes")


def _get_workers() -> int:
    """Get number of worker processes from environment."""
    try:
        return int(os.getenv("UVICORN_WORKERS", "1"))
    except ValueError:
        return 1


def main():
    """Start the API server."""
    parser = argparse.ArgumentParser(description="BioAnalyzer Package API Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["debug", "info", "warning", "error"],
        help="Log level",
    )

    args = parser.parse_args()
    reload_enabled = _should_reload(args)
    workers = _get_workers()

    print("Starting BioAnalyzer Package API Server...")
    print(f"API: http://{args.host}:{args.port}")
    print(f"Docs: http://{args.host}:{args.port}/docs")
    print(f"Health: http://{args.host}:{args.port}/health")
    print(f"Reload: {'enabled' if reload_enabled else 'disabled'}")
    print(f"Log level: {args.log_level}")
    print("\nPress Ctrl+C to stop")

    try:
        import uvicorn

        if workers > 1 and not reload_enabled:
            uvicorn.run(
                "app.api.app:app",
                host=args.host,
                port=args.port,
                log_level=args.log_level,
                workers=workers,
            )
        else:
            uvicorn.run(
                "app.api.app:app",
                host=args.host,
                port=args.port,
                log_level=args.log_level,
                reload=reload_enabled,
            )
    except KeyboardInterrupt:
        print("\nServer stopped")
    except ImportError as e:
        print(f"Failed to import uvicorn: {e}")
        print("Install with: pip install uvicorn[standard]")
        sys.exit(1)
    except OSError as e:
        print(f"Server error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
