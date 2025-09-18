from __future__ import annotations
try:
    from mtr_processor.utils.loader import get_legacy_module  # type: ignore
    _mod = get_legacy_module()
    PDFProcessor = getattr(_mod, "PDFProcessor")
except Exception as _e:
    class PDFProcessor:  # type: ignore
        def __init__(self, *args, **kwargs):
            raise ImportError("PDFProcessor not available: " + str(_e))
