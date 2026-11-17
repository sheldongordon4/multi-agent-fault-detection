"""
Repeat-offender detection.

The SOPs already say a repeated transient SLG at one location often precedes a
permanent failure. The tickets to prove it have been in Postgres all along;
nothing was reading them as a series. These tests run against a real database
per the project's rule about not mocking it, and skip when it is not listening.
"""

import socket
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

import pytest
import sqlalchemy as sa

from backend.config import settings
from backend.database import engine
from backend.persistence import service as persist_service
from backend.persistence.models import FaultTicketRecord

BUS = "b671"
PREFIX = "test:repeat:"


def _db_listening() -> bool:
    url = urlparse(str(settings.DATABASE_ASYNC_URL).replace("postgresql+asyncpg", "postgresql"))
    try:
        with socket.create_connection((url.hostname or "localhost", url.port or 5432), timeout=1):
            return True
    except OSError:
        return False


requires_db = pytest.mark.skipif(
    not _db_listening(), reason="dev Postgres not listening; run docker compose up -d db"
)


def _ticket(incident_id: str, fault_type: str, severity: str) -> dict:
    return {
        "ticket_id": incident_id,
        "scenario": "feeder:ieee13",
        "bus_id": BUS,
        "fault_type": fault_type,
        "severity": severity,
        "status": "diagnosed",
        "summary": "seeded",
        "root_cause": "seeded",
        "recommended_actions": [],
        "evidence": [],
        "kb_citations": [],
        "created_at": datetime.now(UTC).isoformat(),
    }


async def _counts(days: int) -> dict[str, int]:
    """Occurrences per fault code at the test bus, right now."""
    items = await persist_service.repeat_offenders(days=days, min_occurrences=1)
    return {i["fault_code"]: i["occurrences"] for i in items if i["bus_id"] == BUS}


@pytest.fixture
async def seeded_history():
    """
    Three SLGs and one LL at the same bus, plus one SLG long out of the window.

    Yields the counts as they were BEFORE seeding. The dev database holds real
    tickets from demo runs at the same buses, so the tests assert on the change
    this fixture caused rather than on absolute totals — otherwise they pass or
    fail depending on what someone last demoed.

    The shared async engine pools connections against whichever event loop first
    used them, so it is disposed around the test rather than leaked into the
    next one's loop.
    """
    before = await _counts(days=365 * 2)
    before_recent = await _counts(days=30)
    before = {"all_time": before, "recent": before_recent}

    rows = [
        # Same bus, same code, inside the window — the repeat.
        (f"{PREFIX}slg-1", "SLG near b671 (~0.4 km)", "medium", 1),
        (f"{PREFIX}slg-2", "SLG near b671 (~1.2 km)", "high", 3),
        (f"{PREFIX}slg-3", "SLG near b671", "low", 6),
        # Same bus, different code — must not join the SLG group.
        (f"{PREFIX}ll-1", "LL near b671", "medium", 2),
        # Same bus and code but outside the lookback.
        (f"{PREFIX}slg-old", "SLG near b671", "high", 400),
    ]

    async with engine.begin() as conn:
        for incident_id, fault_type, severity, days_ago in rows:
            await conn.execute(
                sa.insert(FaultTicketRecord).values(
                    incident_id=incident_id,
                    ticket_id=incident_id,
                    scenario="feeder:ieee13",
                    bus_id=BUS,
                    fault_type=fault_type,
                    severity=severity,
                    status="diagnosed",
                    summary="seeded",
                    raw=_ticket(incident_id, fault_type, severity),
                    created_at=datetime.now(UTC) - timedelta(days=days_ago),
                )
            )
    yield before
    async with engine.begin() as conn:
        await conn.execute(
            sa.delete(FaultTicketRecord).where(FaultTicketRecord.incident_id.like(f"{PREFIX}%"))
        )
    await engine.dispose()


# ── unit: severity ranking (no database) ─────────────────────────────────────


def test_worst_severity_understands_the_coordinator_vocabulary():
    """
    The enum has three values; what reaches the database has more.

    "critical", "severe" and "moderate" are all in the real ticket history, and
    ranking the raw strings scores every one as unknown — so a group holding a
    critical fault reported as its mildest member.
    """
    assert persist_service._worst(["low", "critical", "low"]) == "high"
    assert persist_service._worst(["low", "moderate"]) == "medium"
    assert persist_service._worst(["low", "low"]) == "low"


def test_worst_severity_of_nothing_is_nothing():
    assert persist_service._worst([]) is None
    assert persist_service._worst([None, ""]) is None


def test_alphabetical_order_would_get_this_wrong():
    """The reason the ranking exists: Postgres sorts "low" after "high"."""
    assert max(["high", "low"]) == "low"
    assert persist_service._worst(["high", "low"]) == "high"


def test_cadence_is_measured_across_the_incidents_not_the_window():
    """
    The bug this replaced: dividing the 365-day lookback by 20 occurrences
    reported twenty faults inside four days as one every eighteen days.

    N incidents have N-1 gaps, so a pair a day apart recurs every one day.
    """
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)

    assert persist_service._cadence_days(now - timedelta(days=4), now, 5) == 1.0
    assert persist_service._cadence_days(now - timedelta(days=1), now, 2) == 1.0

    # Nothing to average across.
    assert persist_service._cadence_days(now, now, 1) is None
    assert persist_service._cadence_days(now, now, 3) is None, "a replay is not a cadence"
    assert persist_service._cadence_days(None, now, 3) is None


# ── integration ──────────────────────────────────────────────────────────────


def _find(items: list[dict], code: str) -> dict | None:
    return next((i for i in items if i["bus_id"] == BUS and i["fault_code"] == code), None)


@requires_db
async def test_repeats_are_grouped_by_bus_and_fault_code(seeded_history):
    """
    The distance estimate moves between events, so grouping on the whole
    `fault_type` string would put every occurrence in its own bucket.
    """
    slg = _find(await persist_service.repeat_offenders(days=30), "SLG")

    assert slg is not None, "three SLGs at one bus were not recognised as a repeat"
    # Three differently-worded fault_type strings collapsed into one group.
    assert slg["occurrences"] - seeded_history["recent"].get("SLG", 0) == 3


@requires_db
async def test_a_different_fault_at_the_same_bus_is_a_different_offender(seeded_history):
    """
    A bus with unrelated faults is a busy bus; a bus with three of the same is
    a defect nobody has found. Only the second is worth an inspection.
    """
    items = await persist_service.repeat_offenders(days=30, min_occurrences=1)

    assert _find(items, "SLG")["occurrences"] - seeded_history["recent"].get("SLG", 0) == 3
    assert _find(items, "LL")["occurrences"] - seeded_history["recent"].get("LL", 0) == 1


@requires_db
async def test_the_lookback_window_excludes_old_incidents(seeded_history):
    """A fault from last year is history, not a pattern."""
    recent = _find(await persist_service.repeat_offenders(days=30), "SLG")
    all_time = _find(await persist_service.repeat_offenders(days=365 * 2), "SLG")

    added_recent = recent["occurrences"] - seeded_history["recent"].get("SLG", 0)
    added_all_time = all_time["occurrences"] - seeded_history["all_time"].get("SLG", 0)

    assert added_recent == 3, "the 400-day-old incident leaked into a 30-day window"
    assert added_all_time == 4, "widening the window did not pick the old incident up"


@requires_db
async def test_min_occurrences_filters_one_off_faults(seeded_history):
    """The default exists so a single fault does not present as a trend."""
    items = await persist_service.repeat_offenders(days=30, min_occurrences=2)
    ll = _find(items, "LL")

    assert _find(items, "SLG") is not None
    if seeded_history["recent"].get("LL", 0) == 0:
        assert ll is None, "a single LL was reported as a repeat offender"


@requires_db
async def test_the_group_reports_its_worst_severity_not_its_latest(seeded_history):
    """
    Postgres sorts severity strings alphabetically, which puts "low" above
    "medium". A group containing a high-severity fault has to read as high.
    """
    assert _find(await persist_service.repeat_offenders(days=30), "SLG")["worst_severity"] == "high"


@requires_db
async def test_the_group_carries_its_customer_impact_and_recent_incidents(seeded_history):
    """It drives a dispatch decision and a link list, so both have to be there."""
    slg = _find(await persist_service.repeat_offenders(days=30), "SLG")

    assert slg["customers_affected"] == 6400  # b671, per backend/faults/customers.py
    assert slg["recent_incident_ids"], "no incidents to link to"
    # Seeded 6, 3 and 1 days ago: a 5-day span across 2 gaps.
    assert slg["mean_days_between"] == pytest.approx(2.5, abs=0.1)
    assert len(slg["recent_incident_ids"]) <= 5, "the link list is capped, not an export"
    assert slg["first_seen"] < slg["last_seen"]


@requires_db
async def test_the_endpoint_is_reachable_and_not_shadowed_by_the_id_route():
    """
    `/tickets/{incident_id}` would capture "repeat-offenders" as an id and
    answer 404 if the routes were declared the other way round.
    """
    from httpx import ASGITransport, AsyncClient

    from backend.api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/tickets/repeat-offenders", params={"days": 30})

    assert response.status_code == 200
    body = response.json()
    assert body["window_days"] == 30
    assert isinstance(body["items"], list)
