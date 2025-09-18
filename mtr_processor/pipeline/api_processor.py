from __future__ import annotations
try:
    from mtr_processor.utils.loader import get_legacy_module  # type: ignore
    _mod = get_legacy_module()
    APIProcessor = getattr(_mod, "APIProcessor")
except Exception as _e:
    class APIProcessor:  # type: ignore
        def __init__(self, *args, **kwargs):
            raise ImportError("APIProcessor not available: " + str(_e))
