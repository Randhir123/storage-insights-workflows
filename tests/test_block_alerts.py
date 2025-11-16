import types
from typing import Any, Iterable

from src.workflows.block_alerts import (
    BlockAlertHotspotsResult,
    SeverityCounts,
    analyze_block_alert_hotspots,
)


class StubTokenManager:
    def get_token(self) -> str:  # pragma: no cover - trivial
        return "stub-token"


class StubResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.status_code = 200

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:  # pragma: no cover - no-op for success
        return None


class StubSession:
    def __init__(self, responses: Iterable[dict[str, Any]]) -> None:
        self._responses = iter(responses)
        self.request_log: list[dict[str, Any]] = []

    def get(self, url: str, headers: dict[str, str], params: Any, timeout: int) -> StubResponse:
        self.request_log.append({"url": url, "params": params})
        return StubResponse(next(self._responses))


def _build_payload(data: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "tenantID": "tenant",
        "startTimestamp": 0,
        "endTimestamp": 0,
        "data": data,
        "status": 200,
        "message": "success",
        "path": "/",
        "method": "GET",
    }


def test_analyze_block_alert_hotspots_ranks_systems_by_severity():
    storage_systems = {
        "data": [
            {"systemId": "alpha", "name": "Alpha"},
            {"systemId": "beta", "name": "Beta"},
        ]
    }
    tenant_alerts = _build_payload(
        [
            {"resource": "Alpha", "severity": "critical"},
            {"resource": "Alpha", "severity": "warning"},
            {"resource": "Beta", "severity": "critical"},
            {"resource": "Beta", "severity": "info"},
        ]
    )
    alpha_system_alerts = _build_payload(
        [
            {"category": "CAPACITY", "severity": "critical"},
            {"category": "GENERAL", "severity": "warning"},
        ]
    )

    session = StubSession([storage_systems, tenant_alerts, alpha_system_alerts])
    result = analyze_block_alert_hotspots(
        duration="7d",
        settings=types.SimpleNamespace(api_base="https://example.com", tenant_id="tenant"),
        session=session,
        token_manager=StubTokenManager(),
    )

    assert isinstance(result, BlockAlertHotspotsResult)
    assert len(result.ranked_systems) == 2
    assert result.ranked_systems[0].system_id == "alpha"
    assert result.ranked_systems[0].counts == SeverityCounts(critical=1, warning=1, info=0)
    assert result.ranked_systems[1].counts == SeverityCounts(critical=1, warning=0, info=1)
    assert result.top_system_alert_types == ["CAPACITY", "GENERAL"]
    assert len(result.top_system_alerts) == 2


def test_analyze_block_alert_hotspots_handles_no_matches():
    storage_systems = {"data": [{"systemId": "alpha", "name": "Alpha"}]}
    tenant_alerts = _build_payload([])
    system_alerts = _build_payload([])

    session = StubSession([storage_systems, tenant_alerts, system_alerts])
    result = analyze_block_alert_hotspots(
        settings=types.SimpleNamespace(api_base="https://example.com", tenant_id="tenant"),
        session=session,
        token_manager=StubTokenManager(),
    )

    assert result.ranked_systems == []
    assert result.top_system_alerts == []
    assert result.top_system_alert_types == []
