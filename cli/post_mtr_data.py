#!/usr/bin/env python3
"""Minimal CLI for posting MTR JSON files.
Wraps existing poster class with tiny entry point.
"""
from __future__ import annotations
import os
import sys

# Reuse the existing standalone class for the heavy lifting
from post_mtr_data import MTRDataPoster
import pathlib


def main() -> int:
    if len(sys.argv) > 1:
        folder = os.path.abspath(sys.argv[1])
    else:
        # default to repo_root/output
        repo_root = pathlib.Path(__file__).resolve().parents[1]
        folder = str(repo_root / "output")
    poster = MTRDataPoster()
    ok, fail = poster.process_json_files(folder)
    poster.print_summary(ok, fail)
    return 0 if not fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
