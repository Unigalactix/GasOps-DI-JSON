from __future__ import annotations
# Thin wrapper to import class from legacy monolithic script
try:
    from mtr_processor.utils.loader import get_legacy_module  # type: ignore
    _mod = get_legacy_module()
    DocumentIntelligenceOCR = getattr(_mod, "DocumentIntelligenceOCR")
except Exception as _e:
    class DocumentIntelligenceOCR:  # type: ignore
        def __init__(self, *args, **kwargs):
            raise ImportError("DocumentIntelligenceOCR not available: " + str(_e))
