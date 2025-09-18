"""Utilities to load legacy monolithic script as a module.
This allows wrappers to access classes without duplicating code.
"""
from __future__ import annotations
import os
import sys
import importlib.util
from functools import lru_cache
from typing import Any

LEGACY_FILENAME = "pdf_processor_new prompt.py"


def _legacy_path() -> str:
    # mtr_processor/utils/loader.py -> repo_root = two dirs up from mtr_processor
    here = os.path.dirname(__file__)
    repo_root = os.path.abspath(os.path.join(here, "..", ".."))
    candidate = os.path.join(repo_root, LEGACY_FILENAME)
    if os.path.exists(candidate):
        return candidate
    # Fallback: try one more directory up
    alt = os.path.abspath(os.path.join(repo_root, LEGACY_FILENAME))
    return alt


@lru_cache(maxsize=1)
def get_legacy_module() -> Any:
    path = _legacy_path()
    module_name = "legacy_pdf_processor_new_prompt"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load legacy module from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod
