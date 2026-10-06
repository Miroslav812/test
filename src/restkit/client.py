import logging
from time import perf_counter
from typing import Any
from urllib.parse import unquote, urlsplit

import httpx

from restkit.config import Settings

logger = logging.getLogger(__name__)


class ApiClient:
    """One connection pool per fixture. No retries for state-changing requests."""

    def __init__(self, settings: Settings, *, transport: httpx.BaseTransport | None = None) -> None:
        headers = {"Accept": "application/json"}
        if settings.token and settings.token.get_secret_value():
            headers["Authorization"] = f"Bearer {settings.token.get_secret_value()}"
        self._http = httpx.Client(
            base_url=settings.base_url,
            headers=headers,
            timeout=settings.timeout_seconds,
            verify=settings.verify_tls,
            trust_env=settings.trust_env,
            follow_redirects=False,
            transport=transport,
        )

    def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        url = urlsplit(path)
        if url.scheme or url.netloc or path.startswith("/") or "\\" in path:
            raise ValueError("API paths must be relative to the configured base URL")
        if any(part in {".", ".."} for part in unquote(url.path).split("/")):
            raise ValueError("API paths must not contain traversal segments")
        started = perf_counter()
        response = self._http.request(method, path, **kwargs)
        # Deliberately omit URL parameters, headers and bodies (may contain secrets/PII).
        logger.info("HTTP %s -> %s (%.3fs)", method, response.status_code, perf_counter() - started)
        return response

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "ApiClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
