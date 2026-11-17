"""
Assignment tests.

Split in two: the route-level tests use ASGITransport with the service faked
(no infrastructure), and the integration tests run against a real Postgres per
the project's rule about not mocking the database. The integration block skips
itself when the dev database isn't listening, so the suite still passes offline.

The test that matters most is `test_assignment_survives_ticket_redelivery`: it
pins the invariant the whole feature rests on.
"""

import socket
from urllib.parse import urlparse

import pytest
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient

from backend.api.main import app
from backend.assignments.constants import Priority, WorkState
from backend.assignments.schemas import AssignmentUpdate
from backend.config import settings

_TICKET = {
    "ticket_id": "T-ASSIGN-1",
    "scenario": "feeder:ieee13",
    "bus_id": "b671",
    "fault_type": "SLG near b671 (~0.4 km)",
    "severity": "high",
    "status": "diagnosed",
    "summary": "Phase-A to ground on the 671 lateral.",
    "root_cause": "High zero-sequence current.",
    "recommended_actions": ["Inspect b671"],
    "evidence": [],
    "kb_citations": [],
    "created_at": "2026-09-04T00:00:00Z",
}

INCIDENT_ID = "test:assignments:b671"


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ── unit: severity-derived defaults ──────────────────────────────────────────


def test_default_priority_follows_severity_including_synonyms():
    from backend.assignments.service import default_priority

    assert default_priority("high") is Priority.P1
    assert default_priority("medium") is Priority.P2
    assert default_priority("low") is Priority.P3
    # The column stores the coordinator's raw string, so synonyms must map too.
    assert default_priority("critical") is Priority.P1
    assert default_priority("moderate") is Priority.P2
    # Unknown severity falls back the same way the backend schema does.
    assert default_priority("banana") is Priority.P2
    assert default_priority(None) is Priority.P2


def test_sla_budget_shrinks_as_severity_rises():
    from datetime import UTC, datetime

    from backend.assignments.service import default_due_at

    since = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
    high = default_due_at("high", since=since)
    medium = default_due_at("medium", since=since)
    low = default_due_at("low", since=since)

    assert high < medium < low
    assert (high - since).total_seconds() == 30 * 60


def test_projection_defaults_an_absent_assignment_row():
    """A ticket with no assignment row must read as unassigned, not as null."""
    from backend.assignments.service import _project

    row = _project(
        {
            "incident_id": INCIDENT_ID,
            "severity": "high",
            "work_state": None,
            "priority": None,
            "version": None,
        }
    )

    assert row["work_state"] == WorkState.UNASSIGNED.value
    assert row["priority"] == Priority.P1.value  # derived from severity
    assert row["version"] == 0


# ── routes (no infrastructure) ───────────────────────────────────────────────


async def test_list_assignments_with_dependency_override(monkeypatch):
    from backend.assignments import service as assign_service
    from backend.database import get_db_connection

    async def _fake_conn():
        yield None

    async def _fake_list(**kwargs):
        assert kwargs["unassigned_only"] is True
        return [
            {
                "incident_id": INCIDENT_ID,
                "ticket_id": "T-ASSIGN-1",
                "bus_id": "b671",
                "scenario": "feeder:ieee13",
                "fault_type": "SLG near b671",
                "severity": "high",
                "status": "diagnosed",
                "summary": "Phase-A to ground.",
                "created_at": "2026-09-04T00:00:00Z",
                "work_state": "unassigned",
                "priority": "p1",
                "assignee_id": None,
                "assignee_name": None,
                "assignee_initials": None,
                "due_at": None,
                "note": None,
                "version": 0,
                "updated_at": None,
            }
        ]

    app.dependency_overrides[get_db_connection] = _fake_conn
    monkeypatch.setattr(assign_service, "list_assignments", _fake_list)
    try:
        async with await _client() as client:
            r = await client.get("/assignments", params={"unassigned": True})
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["items"][0]["work_state"] == "unassigned"
    assert body["items"][0]["priority"] == "p1"


async def test_patch_returns_409_when_version_is_stale(monkeypatch):
    from backend.assignments import service as assign_service
    from backend.assignments.service import StaleAssignmentVersion

    async def _stale(*args, **kwargs):
        raise StaleAssignmentVersion(current_version=4)

    monkeypatch.setattr(assign_service, "update_assignment", _stale)

    async with await _client() as client:
        r = await client.patch(
            f"/assignments/{INCIDENT_ID}",
            json={"work_state": "in_progress", "expected_version": 2},
        )

    assert r.status_code == 409
    assert "version 4" in r.json()["detail"]


async def test_patch_returns_404_for_unknown_incident(monkeypatch):
    from backend.assignments import service as assign_service

    async def _missing(*args, **kwargs):
        return None

    monkeypatch.setattr(assign_service, "update_assignment", _missing)

    async with await _client() as client:
        r = await client.patch("/assignments/nope", json={"work_state": "blocked"})

    assert r.status_code == 404


async def test_patch_rejects_unknown_fields():
    """`extra=forbid` stops a typo'd field from being silently ignored."""
    async with await _client() as client:
        r = await client.patch(f"/assignments/{INCIDENT_ID}", json={"assigneeId": "x"})

    assert r.status_code == 422


# ── integration (real Postgres) ──────────────────────────────────────────────


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


@pytest.fixture
async def seeded_ticket():
    """
    A real fault ticket row, cleaned up afterwards.

    The shared async engine pools connections against whichever event loop first
    used them, so it is disposed around each test rather than leaking a
    connection into the next one's loop.
    """
    from backend.assignments.models import AssignmentEvent, Operator, TicketAssignment
    from backend.database import engine
    from backend.persistence.models import FaultTicketRecord
    from backend.persistence.service import upsert_ticket

    await engine.dispose()

    async def _cleanup():
        async with engine.connect() as conn:
            await conn.execute(
                sa.delete(AssignmentEvent).where(AssignmentEvent.incident_id == INCIDENT_ID)
            )
            await conn.execute(
                sa.delete(TicketAssignment).where(TicketAssignment.incident_id == INCIDENT_ID)
            )
            await conn.execute(
                sa.delete(FaultTicketRecord).where(FaultTicketRecord.incident_id == INCIDENT_ID)
            )
            await conn.execute(sa.delete(Operator).where(Operator.name == "Test Operator"))
            await conn.commit()

    await _cleanup()
    await upsert_ticket(INCIDENT_ID, _TICKET)

    async with engine.connect() as conn:
        result = await conn.execute(
            sa.insert(Operator)
            .values(name="Test Operator", initials="TO", role="control_room")
            .returning(Operator.id)
        )
        operator_id = result.scalar_one()
        await conn.commit()

    yield operator_id

    await _cleanup()
    await engine.dispose()


@requires_db
async def test_assignment_survives_ticket_redelivery(seeded_ticket):
    """
    THE regression test for this feature.

    Kafka is at-least-once, so `upsert_ticket` re-runs for an incident that has
    already been assigned. Because assignment lives in its own table, the
    redelivery must rewrite the diagnosis and leave the assignment untouched. If
    this ever fails, work state has leaked onto `fault_tickets`.
    """
    from backend.assignments import service as assign_service
    from backend.persistence.service import upsert_ticket

    operator_id = seeded_ticket

    await assign_service.update_assignment(
        INCIDENT_ID,
        AssignmentUpdate(assignee_id=operator_id, note="Crew dispatched."),
        actor_id=operator_id,
    )

    before = await assign_service.get_assignment(INCIDENT_ID)
    assert before["assignee_id"] == operator_id
    assert before["work_state"] == WorkState.ASSIGNED.value

    # The same ticket arrives again — a rebalance, a restart, a DLQ replay.
    await upsert_ticket(INCIDENT_ID, {**_TICKET, "summary": "Re-delivered summary."})

    after = await assign_service.get_assignment(INCIDENT_ID)
    assert after["summary"] == "Re-delivered summary."  # diagnosis was rewritten
    assert after["assignee_id"] == operator_id  # ownership was not
    assert after["work_state"] == WorkState.ASSIGNED.value
    assert after["note"] == "Crew dispatched."
    assert after["version"] == before["version"]


@requires_db
async def test_assigning_moves_state_and_writes_events(seeded_ticket):
    from backend.assignments import service as assign_service

    operator_id = seeded_ticket

    await assign_service.update_assignment(
        INCIDENT_ID, AssignmentUpdate(assignee_id=operator_id), actor_id=operator_id
    )
    row = await assign_service.get_assignment(INCIDENT_ID)

    # Assigning an untouched ticket implies it is now someone's work.
    assert row["work_state"] == WorkState.ASSIGNED.value
    assert row["assignee_name"] == "Test Operator"
    assert row["priority"] == Priority.P1.value  # seeded from "high"
    assert row["version"] == 1

    events = await assign_service.list_events(INCIDENT_ID)
    kinds = [e["kind"] for e in events]
    assert "assigned" in kinds
    assert "state_changed" in kinds
    assert events[0]["actor_name"] == "Test Operator"


@requires_db
async def test_unassigning_returns_the_ticket_to_the_queue(seeded_ticket):
    from backend.assignments import service as assign_service

    operator_id = seeded_ticket

    await assign_service.update_assignment(
        INCIDENT_ID, AssignmentUpdate(assignee_id=operator_id), actor_id=operator_id
    )
    await assign_service.update_assignment(
        INCIDENT_ID, AssignmentUpdate(assignee_id=None), actor_id=operator_id
    )

    row = await assign_service.get_assignment(INCIDENT_ID)
    assert row["assignee_id"] is None
    assert row["work_state"] == WorkState.UNASSIGNED.value


@requires_db
async def test_explicit_state_wins_over_the_implied_transition(seeded_ticket):
    """Assigning straight to In progress must not be overridden by the implication."""
    from backend.assignments import service as assign_service

    operator_id = seeded_ticket

    await assign_service.update_assignment(
        INCIDENT_ID,
        AssignmentUpdate(assignee_id=operator_id, work_state=WorkState.IN_PROGRESS),
        actor_id=operator_id,
    )

    row = await assign_service.get_assignment(INCIDENT_ID)
    assert row["work_state"] == WorkState.IN_PROGRESS.value


@requires_db
async def test_stale_expected_version_raises(seeded_ticket):
    from backend.assignments import service as assign_service
    from backend.assignments.service import StaleAssignmentVersion

    operator_id = seeded_ticket

    await assign_service.update_assignment(
        INCIDENT_ID, AssignmentUpdate(assignee_id=operator_id), actor_id=operator_id
    )

    # Someone else already moved it on; this caller still holds version 0.
    with pytest.raises(StaleAssignmentVersion):
        await assign_service.update_assignment(
            INCIDENT_ID,
            AssignmentUpdate(work_state=WorkState.BLOCKED, expected_version=0),
            actor_id=operator_id,
        )


@requires_db
async def test_no_op_patch_does_not_bump_the_version(seeded_ticket):
    from backend.assignments import service as assign_service

    operator_id = seeded_ticket

    await assign_service.update_assignment(
        INCIDENT_ID, AssignmentUpdate(assignee_id=operator_id), actor_id=operator_id
    )
    first = await assign_service.get_assignment(INCIDENT_ID)

    # Re-sending the value it already has changes nothing.
    await assign_service.update_assignment(
        INCIDENT_ID, AssignmentUpdate(assignee_id=operator_id), actor_id=operator_id
    )
    second = await assign_service.get_assignment(INCIDENT_ID)

    assert second["version"] == first["version"]
    events = await assign_service.list_events(INCIDENT_ID)
    assert [e["kind"] for e in events].count("assigned") == 1


@requires_db
async def test_open_count_excludes_resolved_work(seeded_ticket):
    from backend.assignments import service as assign_service

    operator_id = seeded_ticket

    await assign_service.update_assignment(
        INCIDENT_ID, AssignmentUpdate(assignee_id=operator_id), actor_id=operator_id
    )
    roster = {o["id"]: o for o in await assign_service.list_operators()}
    assert roster[operator_id]["open_count"] == 1

    await assign_service.update_assignment(
        INCIDENT_ID, AssignmentUpdate(work_state=WorkState.RESOLVED), actor_id=operator_id
    )
    roster = {o["id"]: o for o in await assign_service.list_operators()}
    assert roster[operator_id]["open_count"] == 0


@requires_db
async def test_comment_appends_without_creating_an_assignment(seeded_ticket):
    from backend.assignments import service as assign_service

    operator_id = seeded_ticket

    await assign_service.add_comment(
        INCIDENT_ID, "Recloser locked out after the third shot.", actor_id=operator_id
    )

    events = await assign_service.list_events(INCIDENT_ID)
    assert len(events) == 1
    assert events[0]["kind"] == "commented"
    assert events[0]["body"].startswith("Recloser locked out")

    # Commenting must not silently claim the ticket.
    row = await assign_service.get_assignment(INCIDENT_ID)
    assert row["work_state"] == WorkState.UNASSIGNED.value
    assert row["version"] == 0


@requires_db
async def test_priority_filter_finds_tickets_with_no_assignment_row(seeded_ticket):
    """
    Regression: the board *displays* a severity-derived priority for tickets that
    have never been written to, so the filter has to match on the same derived
    value. Filtering on the raw column alone hid exactly the urgent unassigned
    work the filter exists to surface.
    """
    from backend.assignments import service as assign_service

    # The seeded ticket is high severity and has no assignment row at all.
    untouched = await assign_service.get_assignment(INCIDENT_ID)
    assert untouched["version"] == 0
    assert untouched["priority"] == Priority.P1.value

    found = await assign_service.list_assignments(priority=Priority.P1.value, limit=500)
    assert INCIDENT_ID in {row["incident_id"] for row in found}

    # And it must not show up under a priority it does not have.
    others = await assign_service.list_assignments(priority=Priority.P4.value, limit=500)
    assert INCIDENT_ID not in {row["incident_id"] for row in others}


@requires_db
async def test_priority_filter_respects_an_operator_override(seeded_ticket):
    """Once an operator sets a priority, the stored value wins over the default."""
    from backend.assignments import service as assign_service

    await assign_service.update_assignment(
        INCIDENT_ID, AssignmentUpdate(priority=Priority.P4), actor_id=seeded_ticket
    )

    found = await assign_service.list_assignments(priority=Priority.P4.value, limit=500)
    assert INCIDENT_ID in {row["incident_id"] for row in found}

    stale = await assign_service.list_assignments(priority=Priority.P1.value, limit=500)
    assert INCIDENT_ID not in {row["incident_id"] for row in stale}


@requires_db
async def test_concurrent_first_writes_do_not_both_win(seeded_ticket):
    """
    Regression: `SELECT ... FOR UPDATE` locks nothing when the row does not exist,
    so two operators claiming the same untouched ticket both read version 0. The
    version guard on the upsert's conflict clause is what stops the second write
    silently overwriting the first and dispatching two crews to one fault.
    """
    import asyncio

    from backend.assignments import service as assign_service
    from backend.assignments.service import StaleAssignmentVersion

    operator_id = seeded_ticket

    async def claim(state: WorkState):
        return await assign_service.update_assignment(
            INCIDENT_ID,
            AssignmentUpdate(assignee_id=operator_id, work_state=state, expected_version=0),
            actor_id=operator_id,
        )

    results = await asyncio.gather(
        claim(WorkState.ASSIGNED),
        claim(WorkState.IN_PROGRESS),
        return_exceptions=True,
    )

    succeeded = [r for r in results if not isinstance(r, Exception)]
    conflicted = [r for r in results if isinstance(r, StaleAssignmentVersion)]

    # Exactly one write may land; the loser must be told, not silently dropped.
    assert len(succeeded) == 1, results
    assert len(conflicted) == 1, results

    final = await assign_service.get_assignment(INCIDENT_ID)
    assert final["version"] == 1
