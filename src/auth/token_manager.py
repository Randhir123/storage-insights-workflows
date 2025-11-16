"""Simple API token cache for IBM Storage Insights."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

from src.config import Settings, load_settings

DEFAULT_CACHE_PATH = Path(".cache/token.json")
_TOKEN_SKEW_SECONDS = 30


@dataclass
class TokenInfo:
    token: str
    expiration_ms: int

    @property
    def expires_at(self) -> datetime:
        return datetime.fromtimestamp(self.expiration_ms / 1000, tz=timezone.utc)

    def is_valid(self) -> bool:
        now_ms = int(time.time() * 1000)
        return now_ms < (self.expiration_ms - (_TOKEN_SKEW_SECONDS * 1000))


class TokenManager:
    """Retrieves and caches short-lived API tokens."""

    def __init__(self, settings: Settings, cache_path: Optional[Path] = None) -> None:
        self.settings = settings
        self.cache_path = cache_path or DEFAULT_CACHE_PATH
        self._cached: Optional[TokenInfo] = None

    def get_token(self) -> str:
        token_info = self._cached or self._load_from_disk()
        if token_info and token_info.is_valid():
            self._cached = token_info
            return token_info.token

        token_info = self._fetch_from_api()
        self._cached = token_info
        self._write_to_disk(token_info)
        return token_info.token

    # Internal helpers -------------------------------------------------
    def _cache_payload(self, token_info: TokenInfo) -> dict[str, Any]:
        return {
            "token": token_info.token,
            "expiration": token_info.expiration_ms,
        }

    def _write_to_disk(self, token_info: TokenInfo) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._cache_payload(token_info)
        self.cache_path.write_text(json.dumps(payload, indent=2))

    def _load_from_disk(self) -> Optional[TokenInfo]:
        if not self.cache_path.exists():
            return None
        try:
            data = json.loads(self.cache_path.read_text())
            return TokenInfo(
                token=data["token"],
                expiration_ms=int(data["expiration"]),
            )
        except (KeyError, ValueError, json.JSONDecodeError):
            return None

    def _fetch_from_api(self) -> TokenInfo:
        url = f"{self.settings.api_base}/restapi/v1/tenants/{self.settings.tenant_id}/token"
        headers = {
            "x-api-key": self.settings.api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        response = requests.post(url, headers=headers, timeout=30)
        response.raise_for_status()
        payload = response.json()
        result = payload.get("result", {})
        token = result["token"]
        expiration = int(result["expiration"])
        return TokenInfo(token=token, expiration_ms=expiration)


def fetch_token(cache_path: Optional[Path] = None) -> str:
    settings = load_settings()
    manager = TokenManager(settings, cache_path=cache_path)
    return manager.get_token()


def main() -> None:
    token = fetch_token()
    print(token)


if __name__ == "__main__":
    main()
