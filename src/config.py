"""Configuration helpers for IBM Storage Insights workflows."""
from __future__ import annotations

import os
from dataclasses import dataclass


class MissingConfigError(RuntimeError):
    """Raised when required configuration is missing."""


@dataclass(frozen=True)
class Settings:
    base_url: str
    tenant_id: str
    api_key: str

    @property
    def api_base(self) -> str:
        return self.base_url.rstrip("/")


def load_settings() -> Settings:
    """Load settings from environment variables.

    Defaults the base URL to the IBM Storage Insights dev endpoint if one is not
    provided. Tenant ID and API Key are required and will raise if missing.
    """

    base_url = os.getenv("SI_BASE_URL", "https://dev.insights.ibm.com")
    tenant_id = os.getenv("SI_TENANT_ID")
    api_key = os.getenv("SI_API_KEY")

    pairs = (("SI_TENANT_ID", tenant_id), ("SI_API_KEY", api_key))
    missing = [name for name, value in pairs if not value]
    if missing:
        raise MissingConfigError(
            "Missing required environment variables: " + ", ".join(missing)
        )

    return Settings(base_url=base_url, tenant_id=tenant_id, api_key=api_key)
