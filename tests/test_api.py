"""
API integration tests: httpx.AsyncClient + ASGITransport, with dependency_overrides
and monkeypatched services (best-practices: real transport, fakes for external I/O).

ASGITransport does not run the app's lifespan, so the Kafka workers never start —
these tests hit the routes directly without any broker/DB running.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import app

_VALID_TICKET = {
    "ticket_id": "T-1",
    "scenario": "feeder:ieee13",
    "bus_id": "b671",
    "fault_type": "Ground fault (SLG/LLG) near b671",
    "severity": "high",
    "status": "diagnosed",
    "summary": "SLG fault on b671.",
    "root_cause": "High zero-sequence current.",
    "recommended_actions": ["Inspect b671", "Verify relay settings"],
    "evidence": [
        {
            "start_timestamp": "2026-06-30T00:00:00Z",
            "end_timestamp": "2026-06-30T00:00:01Z",
            "metric": "voltage",
            "description": "Deep sag at b671.",
        }
    ],
    "kb_citations": [{"source_id": "SOP-OVLD-001", "title": "Feeder Overload"}],
    "created_at": "2026-06-30T00:00:02Z",
}


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_health():
    async with await _client() as client:
        r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_diagnose_returns_fault_ticket(monkeypatch):
    import app.faults.router as router_mod

    monkeypatch.setattr(router_mod, "run_fault_diagnosis", lambda detection: _VALID_TICKET)

    body = {
        "feeder": "ieee13",
        "severity": "high",
        "top_buses": [{"bus": "b671", "minVa": 0.4, "maxI0I1": 0.31}],
    }
    async with await _client() as client:
        r = await client.post("/faults/diagnose", json=body)

    assert r.status_code == 200
    data = r.json()
    assert data["bus_id"] == "b671"
    assert data["severity"] == "high"  # serialized through response_model=FaultTicket


async def test_notifications_list_with_dependency_override(monkeypatch):
    from app.database import get_db_connection
    from app.notification import service as notif_service

    async def _fake_conn():
        yield None  # the fake service ignores the connection

    async def _fake_list(conn):
        return [
            {
                "id": "n1",
                "type": "faultticket.ready",
                "title": "Fault on b671",
                "body": "A high-severity fault ticket was raised.",
                "read": False,
                "incident_id": "ieee13:1",
                "bus_id": "b671",
                "severity": "high",
                "created_at": "2026-06-30T00:00:00Z",
            }
        ]

    app.dependency_overrides[get_db_connection] = _fake_conn
    monkeypatch.setattr(notif_service, "list_notifications", _fake_list)
    try:
        async with await _client() as client:
            r = await client.get("/notifications")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200
    data = r.json()
    assert data["unread_count"] == 1
    assert data["items"][0]["bus_id"] == "b671"
