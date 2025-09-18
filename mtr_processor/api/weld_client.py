"""
Certificate-authenticated client for weld management system APIs.
Encapsulates GET and POST with requests_pkcs12.
"""
from __future__ import annotations
import os
import base64
import tempfile
from typing import Any, Dict, Optional, Tuple

try:
    import requests_pkcs12
except Exception:
    requests_pkcs12 = None


class WeldAPIClient:
    BASE_URL = "https://oamsapi.gasopsiq.com"

    def __init__(self, pfx_source: str = "./certificate/oamsapicert2023.pfx", pfx_password: str = "password1234", verify_ssl: bool = True):
        self.pfx_source = pfx_source
        self.pfx_password = pfx_password
        self.verify_ssl = verify_ssl

    def _load_pfx_bytes(self) -> Tuple[bytes, Optional[tempfile.NamedTemporaryFile]]:
        temp_file = None
        if not os.path.isfile(self.pfx_source):
            # Support base64-encoded certificate string
            cert_bytes = base64.b64decode(self.pfx_source)
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pfx")
            temp_file.write(cert_bytes)
            temp_file.close()
            pfx_path = temp_file.name
        else:
            pfx_path = self.pfx_source
        with open(pfx_path, "rb") as f:
            pfx_data = f.read()
        return pfx_data, temp_file

    def get(self, path: str, headers: Dict[str, str], params: Dict[str, Any]) -> Tuple[int, Any]:
        if requests_pkcs12 is None:
            raise RuntimeError("requests_pkcs12 not installed")
        pfx_data, temp = self._load_pfx_bytes()
        try:
            resp = requests_pkcs12.get(
                f"{self.BASE_URL}{path}",
                headers=headers,
                params=params,
                pkcs12_data=pfx_data,
                pkcs12_password=self.pfx_password,
                verify=self.verify_ssl,
                timeout=30,
            )
            try:
                return resp.status_code, resp.json()
            except Exception:
                return resp.status_code, resp.text
        finally:
            if temp:
                try:
                    os.unlink(temp.name)
                except Exception:
                    pass

    def post_json(self, path: str, headers: Dict[str, str], json_body: Dict[str, Any]) -> Tuple[int, Any]:
        if requests_pkcs12 is None:
            raise RuntimeError("requests_pkcs12 not installed")
        pfx_data, temp = self._load_pfx_bytes()
        try:
            resp = requests_pkcs12.post(
                f"{self.BASE_URL}{path}",
                headers=headers,
                json=json_body,
                pkcs12_data=pfx_data,
                pkcs12_password=self.pfx_password,
                verify=self.verify_ssl,
                timeout=30,
            )
            try:
                return resp.status_code, resp.json()
            except Exception:
                return resp.status_code, resp.text
        finally:
            if temp:
                try:
                    os.unlink(temp.name)
                except Exception:
                    pass
