"""Small, fail-closed client for activation-code redemption."""
from typing import Any, Dict, Optional

import requests


_SERVICE_ERROR_STATUS = {
    "LIC-013": 400,
    "LIC-014": 409,
    "LIC-015": 422,
}


class ActivationServiceError(RuntimeError):
    def __init__(self, code: str = "LIC-011") -> None:
        super().__init__("activation service unavailable")
        self.code = code


class LicenseApi:
    def __init__(self, base_url: str, session: Optional[requests.Session] = None):
        self.base_url = str(base_url).rstrip("/")
        self.session = session or requests.Session()

    def activate_code(
        self,
        device_hash: str,
        client_version: str,
        activation_code: str,
    ) -> Dict[str, Any]:
        return self._json(
            "/v1/code-activations",
            json={
                "device_hash": device_hash,
                "client_version": client_version,
                "activation_code": activation_code,
            },
        )

    def _json(self, path: str, **kwargs: Any) -> Dict[str, Any]:
        try:
            response = self.session.request(
                "POST",
                self.base_url + path,
                timeout=(5, 20),
                **kwargs,
            )
            status_code = response.status_code
            value = response.json()
        except Exception:
            raise ActivationServiceError() from None

        if status_code == 200 and isinstance(value, dict):
            return value

        if (
            isinstance(value, dict)
            and set(value) == {"detail"}
            and isinstance(value["detail"], dict)
            and set(value["detail"]) == {"code"}
            and isinstance(value["detail"]["code"], str)
        ):
            code = value["detail"]["code"]
            if _SERVICE_ERROR_STATUS.get(code) == status_code:
                raise ActivationServiceError(code)

        raise ActivationServiceError()
