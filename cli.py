#!/usr/bin/env python3
"""Backward-compatible CLI entrypoint.

This shim keeps older global BioAnalyzer launchers working after the
CLI implementation moved to scripts/cli.py.
"""

from scripts.cli import main


if __name__ == "__main__":
    main()
