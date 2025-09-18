#!/usr/bin/env python3
"""Minimal CLI to process a heat number end-to-end."""
from __future__ import annotations
import os
import sys
from mtr_processor.auth.tokens import get_default_auth_token
from mtr_processor.pipeline.api_processor import APIProcessor
import pathlib


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m cli.process_heat <HEAT_NUMBER> [OUTPUT_DIR]")
        return 2
    heat = sys.argv[1]
    if len(sys.argv) > 2:
        out_dir = sys.argv[2]
    else:
        # default to repo_root/output
        repo_root = pathlib.Path(__file__).resolve().parents[1]
        out_dir = str(repo_root / "output")
    os.makedirs(out_dir, exist_ok=True)

    token = get_default_auth_token()
    api = APIProcessor()
    try:
        pdf_path, json_path, company_id = api.process_heat_number_to_json(
            heat_number=heat,
            output_dir=out_dir,
            auth_token=token,
        )
        print(f"PDF saved: {pdf_path}")
        print(f"JSON saved: {json_path}")
        print(f"CompanyMTRFileID: {company_id}")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
