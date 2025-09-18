from __future__ import annotations
try:
    from mtr_processor.utils.loader import get_legacy_module  # type: ignore
    _mod = get_legacy_module()
    XLSXProcessor = getattr(_mod, "XLSXProcessor")
except Exception as _e:
    class XLSXProcessor:  # type: ignore
        def __init__(self, *args, **kwargs):
            raise ImportError("XLSXProcessor not available: " + str(_e))
