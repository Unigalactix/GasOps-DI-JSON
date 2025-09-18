from __future__ import annotations
try:
    from mtr_processor.utils.loader import get_legacy_module  # type: ignore
    _mod = get_legacy_module()
    AITemplateProcessor = getattr(_mod, "AITemplateProcessor")
except Exception as _e:
    class AITemplateProcessor:  # type: ignore
        def __init__(self, *args, **kwargs):
            raise ImportError("AITemplateProcessor not available: " + str(_e))
