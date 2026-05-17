#!/usr/bin/env python3
"""
Main entry point for GitHub PR Analytics Suite.

Subcommands: fetch, summarize, by-project, technical, perf-review, publish, all, ship
Run `python main.py` with no args for the default `ship` workflow.
"""

if __name__ == "__main__":
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

    from pr_summarizer import main as summarizer_main

    if len(sys.argv) == 1:
        sys.argv.append("ship")

    sys.exit(summarizer_main())
