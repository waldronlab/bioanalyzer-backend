#!/usr/bin/env python3
"""
Run script for BugSigDB Analyzer.
This script allows running the application with either HTTP or HTTPS.
"""

import argparse
import os
import ssl
import sys
import uvicorn
from pathlib import Path

# Add the project root directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Import the app after setting up the path
from web.app import app

def main():
    parser = argparse.ArgumentParser(description="Run BugSigDB Analyzer")
    parser.add_argument("--https", action="store_true", help="Run with HTTPS")
    parser.add_argument("--port", type=int, default=None, help="Port to run on (default: 8443 for HTTPS, 8000 for HTTP)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to run on (default: 127.0.0.1)")
    
    args = parser.parse_args()
    
    print("Starting BugSigDB Analyzer API...")
    
    if args.https:
        # Set default HTTPS port if not specified
        port = args.port or 8443
        
        # Check if SSL certificates exist, if not, create self-signed certificates
        cert_dir = Path("./certs")
        cert_file = cert_dir / "cert.pem"
        key_file = cert_dir / "key.pem"
        
        if not cert_dir.exists():
            cert_dir.mkdir(exist_ok=True)
        
        if not cert_file.exists() or not key_file.exists():
            print("Generating self-signed SSL certificates...")
            os.system(f'openssl req -x509 -newkey rsa:4096 -nodes -out {cert_file} -keyout {key_file} -days 365 -subj "/CN=localhost"')
        
        print(f"Running with HTTPS on {args.host}:{port}")
        uvicorn.run("web.app:app", host=args.host, port=port, ssl_certfile=str(cert_file), ssl_keyfile=str(key_file), log_level="info")
    else:
        # Set default HTTP port if not specified
        port = args.port or 8000
        print(f"Running with HTTP on {args.host}:{port}")
        uvicorn.run("web.app:app", host=args.host, port=port, log_level="info")

if __name__ == "__main__":
    main() 