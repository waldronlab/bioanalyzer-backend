#!/usr/bin/env python3
"""
BioAnalyzer Backend - Main Entry Point
======================================

This is the main entry point for the BioAnalyzer Backend API server.
It can be run directly or imported as a module.

Usage:
    python main.py                    # Start API server
    python main.py --port 8080        # Start on custom port
    python main.py --host 0.0.0.0     # Start on all interfaces
    python main.py --reload           # Start with auto-reload
"""

import sys
import os
import argparse
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Import and run the FastAPI application
from app.api.app import app

def main():
    """Main function to start the API server."""
    parser = argparse.ArgumentParser(description="BioAnalyzer Backend API Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    parser.add_argument("--log-level", default="info", choices=["debug", "info", "warning", "error"], 
                       help="Log level (default: info)")
    
    args = parser.parse_args()
    
    # Check for environment variable override
    reload_flag = args.reload or os.getenv("UVICORN_RELOAD", "false").lower() in ("true", "1", "yes")
    
    print("🚀 Starting BioAnalyzer Backend API Server...")
    print("📁 Project root:", project_root)
    print(f"🌐 API server will be available at: http://{args.host}:{args.port}")
    print(f"📚 API documentation at: http://{args.host}:{args.port}/docs")
    print(f"🔍 Health check at: http://{args.host}:{args.port}/health")
    print(f"📊 Metrics at: http://{args.host}:{args.port}/metrics")
    print(f"🔁 Live reload: {'enabled' if reload_flag else 'disabled'}")
    print(f"📝 Log level: {args.log_level}")
    print("\nPress Ctrl+C to stop the server")
    
    import uvicorn
    uvicorn.run(
        "app.api.app:app",
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        reload=reload_flag
    )

if __name__ == "__main__":
    main()
