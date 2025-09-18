"""
Token helpers wrapping existing decryption module.
Provides a single get_default_auth_token() function.
"""
from __future__ import annotations
import os
from typing import Optional

try:
    # Use existing logic; we only wrap
    from decryption import auth_token as _auth_token
except Exception:
    _auth_token = None


def get_default_auth_token(encoded: Optional[str] = None) -> Optional[str]:
    """Return a valid auth token or None.
    - Reads ENCODED_STRING or encoded_string if not provided
    - Uses decryption.auth_token to generate
    """
    encoded = (
        encoded
        or os.getenv("ENCODED_STRING")
        or os.getenv("encoded_string")
    )
    if not encoded:
        return None
    if _auth_token is None:
        return None
    try:
        token = _auth_token(encoded)
        return token
    except Exception:
        return None
