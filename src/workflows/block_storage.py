"""High-level helpers for block storage workflows.

The functions in this module implement the logic described in
``workflows/block-storage-volume-leaders.arazzo.yaml`` so clients can reuse it
without reimplementing request plumbing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Mapping, MutableMapping, Optional, Sequence

import requests

from src.auth.token_manager import TokenManager
from src.config import Settings, load_settings

_DEFAULT_TIMEOUT = 30


@dataclass(frozen=True)
class BlockStorageVolumeLeadersResult:
    """Structure returned by :func:`get_block_storage_volume_leaders`."""

    storage_systems: Sequence[Mapping[str, Any]]
    top_five: Sequence[Mapping[str, Any]]

    def to_dict(self) -> Mapping[str, Sequence[Mapping[str, Any]]]:
        """Convert the result into a serializable dict structure."""

        return {
            "storage_systems": list(self.storage_systems),
            "top_five": list(self.top_five),
        }


def _build_headers(settings: Settings, token: str) -> Mapping[str, str]:
    return {
        "Accept": "application/json",
        "x-api-token": token,
        # Passing the API key is harmless for endpoints that only require the token.
        "x-api-key": settings.api_key,
    }


def _ensure_session(session: Optional[requests.Session] = None) -> requests.Session:
    return session or requests.Session()


def _extract_storage_systems(payload: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    """Normalize various response shapes to a list of mapping objects."""

    candidates: Iterable[Any] = payload.get("storageSystems") or payload.get("data") or []
    if isinstance(candidates, Iterable):
        return [item for item in candidates if isinstance(item, MutableMapping)]
    return []


def get_block_storage_volume_leaders(
    *,
    limit: int = 5,
    settings: Optional[Settings] = None,
    session: Optional[requests.Session] = None,
    token_manager: Optional[TokenManager] = None,
) -> BlockStorageVolumeLeadersResult:
    """Run the "block storage volume leaders" workflow.

    Parameters
    ----------
    limit:
        Number of top systems to return after sorting by ``volsCount``. Defaults to 5.
    settings:
        Optional override for repository-level :class:`Settings`.
    session:
        Optional :class:`requests.Session` that will be reused for the API call. If
        omitted a temporary session is created.
    token_manager:
        Allow callers to inject a :class:`TokenManager` (useful for tests). When
        omitted, a new manager built from ``settings`` is used.
    """

    if limit <= 0:
        raise ValueError("limit must be positive")

    settings = settings or load_settings()
    manager = token_manager or TokenManager(settings)
    token = manager.get_token()

    sess = _ensure_session(session)
    url = f"{settings.api_base}/restapi/v1/tenants/{settings.tenant_id}/storage-systems"
    params = {"storage-type": "block"}
    response = sess.get(
        url,
        headers=_build_headers(settings, token),
        params=params,
        timeout=_DEFAULT_TIMEOUT,
    )
    response.raise_for_status()
    storage_systems = _extract_storage_systems(response.json())

    sorted_systems = sorted(
        storage_systems,
        key=lambda item: _vols_count(item),
        reverse=True,
    )
    top_five = sorted_systems[:limit]

    return BlockStorageVolumeLeadersResult(
        storage_systems=storage_systems,
        top_five=top_five,
    )


def _vols_count(system: Mapping[str, Any]) -> int:
    value = system.get("volsCount")
    if isinstance(value, (int, float)):
        return int(value)
    # Fall back to the older schema spelling if present.
    alt_value = system.get("volumes_count")
    if isinstance(alt_value, (int, float)):
        return int(alt_value)
    return 0
