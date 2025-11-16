"""Alert-focused workflows for IBM Storage Insights block systems."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import requests

from src.auth.token_manager import TokenManager
from src.config import Settings, load_settings

_SEVERITY_ORDER = ("critical", "warning", "info")
_DEFAULT_TIMEOUT = 30


@dataclass(frozen=True)
class SeverityCounts:
    critical: int = 0
    warning: int = 0
    info: int = 0

    @property
    def total(self) -> int:
        return self.critical + self.warning + self.info

    def sort_key(self) -> tuple[int, int, int, int]:
        return (self.critical, self.warning, self.info, self.total)

    def to_dict(self) -> Dict[str, int]:
        return {
            "critical": self.critical,
            "warning": self.warning,
            "info": self.info,
            "total": self.total,
        }


@dataclass(frozen=True)
class SystemAlertSummary:
    system_id: str
    name: str
    counts: SeverityCounts

    def to_dict(self) -> Mapping[str, Any]:
        return {
            "system_id": self.system_id,
            "name": self.name,
            "counts": self.counts.to_dict(),
        }


@dataclass(frozen=True)
class BlockAlertHotspotsResult:
    block_systems: Sequence[Mapping[str, Any]]
    tenant_alerts: Sequence[Mapping[str, Any]]
    ranked_systems: Sequence[SystemAlertSummary]
    critical_systems: Sequence[SystemAlertSummary]
    top_system_alerts: Sequence[Mapping[str, Any]]
    top_system_alert_types: Sequence[str]

    def to_dict(self) -> Mapping[str, Any]:
        return {
            "block_systems": list(self.block_systems),
            "tenant_alerts": list(self.tenant_alerts),
            "ranked_systems": [summary.to_dict() for summary in self.ranked_systems],
            "critical_systems": [summary.to_dict() for summary in self.critical_systems],
            "top_system_alerts": list(self.top_system_alerts),
            "top_system_alert_types": list(self.top_system_alert_types),
        }


def analyze_block_alert_hotspots(
    *,
    duration: str = "28d",
    limit_alerts: Optional[int] = None,
    settings: Optional[Settings] = None,
    session: Optional[requests.Session] = None,
    token_manager: Optional[TokenManager] = None,
) -> BlockAlertHotspotsResult:
    """Implement the ``block-alert-hotspots`` workflow described in Arazzo.

    The function fetches block systems, retrieves tenant-wide alerts for critical,
    warning, and info severities, orders systems by those counts, and finally pulls
    the alert feed for the system with the highest aggregate.
    """

    settings = settings or load_settings()
    manager = token_manager or TokenManager(settings)
    token = manager.get_token()
    sess = session or requests.Session()
    headers = {"Accept": "application/json", "x-api-token": token}

    block_systems = _fetch_block_systems(settings, sess, headers)
    tenant_alerts = _fetch_tenant_alerts(settings, sess, headers, duration)

    ranked = _rank_systems_by_alerts(block_systems, tenant_alerts)
    critical_only = [summary for summary in ranked if summary.counts.critical > 0]
    top_alerts: Sequence[Mapping[str, Any]] = []
    top_types: Sequence[str] = []

    if ranked:
        top_system = ranked[0]
        top_alerts = _fetch_system_alerts(
            settings,
            sess,
            headers,
            system_id=top_system.system_id,
            duration=duration,
            limit=limit_alerts,
        )
        top_types = _extract_alert_types(top_alerts)

    return BlockAlertHotspotsResult(
        block_systems=block_systems,
        tenant_alerts=tenant_alerts,
        ranked_systems=ranked,
        critical_systems=critical_only,
        top_system_alerts=top_alerts,
        top_system_alert_types=top_types,
    )


def _fetch_block_systems(
    settings: Settings,
    session: requests.Session,
    headers: Mapping[str, str],
) -> List[Mapping[str, Any]]:
    url = f"{settings.api_base}/restapi/v1/tenants/{settings.tenant_id}/storage-systems"
    params = {"storage-type": "block"}
    resp = session.get(url, headers=headers, params=params, timeout=_DEFAULT_TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()
    data = payload.get("data") or payload.get("storageSystems") or []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, Mapping)]
    return []


def _fetch_tenant_alerts(
    settings: Settings,
    session: requests.Session,
    headers: Mapping[str, str],
    duration: str,
) -> List[Mapping[str, Any]]:
    url = f"{settings.api_base}/restapi/v1/tenants/{settings.tenant_id}/alerts"
    params = [
        ("duration", duration),
    ]
    for severity in _SEVERITY_ORDER:
        params.append(("severity", severity))
    resp = session.get(url, headers=headers, params=params, timeout=_DEFAULT_TIMEOUT)
    resp.raise_for_status()
    data = resp.json().get("data") or []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, Mapping)]
    return []


def _fetch_system_alerts(
    settings: Settings,
    session: requests.Session,
    headers: Mapping[str, str],
    *,
    system_id: str,
    duration: str,
    limit: Optional[int],
) -> List[Mapping[str, Any]]:
    url = f"{settings.api_base}/restapi/v1/tenants/{settings.tenant_id}/storage-systems/{system_id}/alerts"
    params: List[tuple[str, Any]] = [("duration", duration)]
    for severity in _SEVERITY_ORDER:
        params.append(("severity", severity))
    resp = session.get(url, headers=headers, params=params, timeout=_DEFAULT_TIMEOUT)
    resp.raise_for_status()
    data = resp.json().get("data") or []
    alerts: List[Mapping[str, Any]]
    if isinstance(data, list):
        alerts = [item for item in data if isinstance(item, Mapping)]
    else:
        alerts = []
    if limit is not None:
        return alerts[:limit]
    return alerts


def _rank_systems_by_alerts(
    block_systems: Sequence[Mapping[str, Any]],
    alerts: Sequence[Mapping[str, Any]],
) -> List[SystemAlertSummary]:
    name_to_system = {
        str(system.get("name")): system for system in block_systems if system.get("name")
    }
    counts: Dict[str, Dict[str, int]] = {name: {sev: 0 for sev in _SEVERITY_ORDER} for name in name_to_system}

    for alert in alerts:
        severity = str(alert.get("severity", "")).lower()
        if severity not in _SEVERITY_ORDER:
            continue
        candidate_names = [alert.get("resource"), alert.get("parentResource")]
        target_name = next((name for name in candidate_names if isinstance(name, str) and name in counts), None)
        if not target_name:
            continue
        counts[target_name][severity] += 1

    summaries: List[SystemAlertSummary] = []
    for name, severity_counts in counts.items():
        tally = SeverityCounts(
            critical=severity_counts["critical"],
            warning=severity_counts["warning"],
            info=severity_counts["info"],
        )
        if tally.total == 0:
            continue
        system = name_to_system[name]
        system_id = str(system.get("systemId") or system.get("storage_system_id"))
        summaries.append(SystemAlertSummary(system_id=system_id, name=name, counts=tally))

    return sorted(summaries, key=lambda summary: summary.counts.sort_key(), reverse=True)


def _extract_alert_types(alerts: Sequence[Mapping[str, Any]]) -> List[str]:
    if not alerts:
        return []
    types = {
        alert.get("category")
        or alert.get("resourceType")
        or alert.get("name")
        for alert in alerts
    }
    cleaned = [typ for typ in types if isinstance(typ, str) and typ]
    cleaned.sort()
    return cleaned
