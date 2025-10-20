#!/usr/bin/env python3
"""
Simple starter script for BugSigDB Analyzer.
This script uses python -m to run the web app, which should handle imports correctly.
"""

import os
import subprocess
import sys
import argparse

def main():
    parser = argparse.ArgumentParser(description="Run BugSigDB Analyzer")
    parser.add_argument("--https", action="store_true", help="Run with HTTPS")
    parser.add_argument("--port", type=int, default=None, help="Port to run on (default: 8443 for HTTPS, 8000 for HTTP)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to run on (default: 127.0.0.1)")
    
    args = parser.parse_args()
    
    # Build command
    cmd = [sys.executable, "-m", "web.app"]
    
    # Add arguments
    if args.https:
        cmd.append("--https")
    
    if args.port:
        cmd.extend(["--port", str(args.port)])
        
    if args.host != "127.0.0.1":
        cmd.extend(["--host", args.host])
    
    # Print info
    port = args.port or (8443 if args.https else 8000)
    protocol = "HTTPS" if args.https else "HTTP"
    print(f"Starting BugSigDB Analyzer API with {protocol} on {args.host}:{port}...")
    
    # Run the command
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\nShutting down...")

if __name__ == "__main__":
    import uvicorn
    print("Starting BugSigDB Analyzer API with HTTP on 127.0.0.1:8000...")
    uvicorn.run("web.app:app", host="127.0.0.1", port=8000, reload=True) 