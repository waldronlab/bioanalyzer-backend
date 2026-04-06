#!/usr/bin/env python3
"""Backward-compatible API server entrypoint.

This shim keeps older tooling working after main.py moved to scripts/main.py.
"""

from scripts.main import main


if __name__ == "__main__":
    main()
