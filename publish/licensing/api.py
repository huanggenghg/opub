"""Small, fail-closed client for the activation service."""
from typing import Any, Dict, Optional

import requests


class ActivationServiceError(RuntimeError):
    code = "LIC-011"


class LicenseApi:
    def __init__(self, base_url: str, session: Optional[requests.Session] = None):
        self.base_url = str(base_url).rstrip("/")
        self.session = session or requests.Session()

    def create_session(self, device_hash: str, client_version: str, payway: str, nonce: str) -> Dict[str, Any]:
        return self._json(
            "POST", "/v1/activation-sessions",
            json={"device_hash": device_hash, "client_nonce": nonce,
                  "client_version": client_version, "payway": payway},
        )

    def get_session(self, session_id: str, poll_token: str) -> Dict[str, Any]:
        return self._json(
            "GET", "/v1/activation-sessions/" + str(session_id),
            headers={"Authorization": "Bearer " + str(poll_token)},
        )

    def _json(self, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
        try:
            response = self.session.request(method, self.base_url + path, timeout=(5, 20), **kwargs)
            response.raise_for_status()
            value = response.json()
            if not isinstance(value, dict):
                raise ValueError("response is not an object")
            return value
        except Exception as exc:
            # Never expose request/response details: they may contain bearer tokens.
            raise ActivationServiceError("activation service unavailable") from None
