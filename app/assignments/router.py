from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncConnection

from app.assignments import service as assign_service
from app.assignments.constants import Priority, WorkState
from app.assignments.schemas import (
    Assignment,
    AssignmentEvent,
    AssignmentEventListResponse,
    AssignmentListResponse,
    AssignmentUpdate,
    CommentCreate,
    Operator,
    OperatorCreate,
    OperatorListResponse,
    OperatorUpdate,
)
from app.assignments.service import StaleAssignmentVersion
from app.database import get_db_connection

# MAFD has no auth, so the acting operator is claimed by the console rather than
# authenticated (see app/assignments/models.py::Operator). Read it straight off
# the header — there is no session to hang it from.
ActorId = Annotated[
    str | None,
    Header(
        alias="X-Actor-Id",
        description="Id of the operator performing the action (roster, not authenticated).",
    ),
]

operators_router = APIRouter(prefix="/operators", tags=["operators"])
router = APIRouter(prefix="/assignments", tags=["assignments"])


# ── operators ────────────────────────────────────────────────────────────────


@operators_router.get(
    "",
    response_model=OperatorListResponse,
    summary="List the operator roster",
    description="Active operators with their current open-ticket count.",
)
async def list_operators(
    conn: Annotated[AsyncConnection, Depends(get_db_connection)],
    include_inactive: Annotated[bool, Query()] = False,
) -> dict[str, Any]:
    items = await assign_service.list_operators(include_inactive=include_inactive, conn=conn)
    return {"items": items, "count": len(items)}


@operators_router.post(
    "",
    response_model=Operator,
    status_code=status.HTTP_201_CREATED,
    summary="Add an operator to the roster",
)
async def create_operator(payload: OperatorCreate) -> dict[str, Any]:
    return await assign_service.create_operator(payload.model_dump())


@operators_router.patch(
    "/{operator_id}",
    response_model=Operator,
    summary="Update a roster entry",
)
async def update_operator(operator_id: str, payload: OperatorUpdate) -> dict[str, Any]:
    row = await assign_service.update_operator(operator_id, payload.model_dump(exclude_unset=True))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operator not found")
    return row


# ── assignments ──────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=AssignmentListResponse,
    summary="List fault tickets with their assignment",
    description=(
        "Fault tickets joined to their assignment row. Tickets with no row yet are "
        "returned as unassigned with severity-derived defaults."
    ),
)
async def list_assignments(
    conn: Annotated[AsyncConnection, Depends(get_db_connection)],
    work_state: Annotated[WorkState | None, Query()] = None,
    assignee_id: Annotated[str | None, Query()] = None,
    unassigned: Annotated[bool, Query(description="Only tickets with no assignee.")] = False,
    severity: Annotated[str | None, Query(pattern="^(low|medium|high)$")] = None,
    priority: Annotated[Priority | None, Query()] = None,
    q: Annotated[str | None, Query(description="Substring match on bus, fault or summary.")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    items = await assign_service.list_assignments(
        work_state=work_state.value if work_state else None,
        assignee_id=assignee_id,
        unassigned_only=unassigned,
        severity=severity,
        priority=priority.value if priority else None,
        search=q,
        limit=limit,
        offset=offset,
        conn=conn,
    )
    return {"items": items, "count": len(items)}


@router.get(
    "/{incident_id}",
    response_model=Assignment,
    summary="Get one ticket's assignment",
)
async def get_assignment(
    incident_id: str,
    conn: Annotated[AsyncConnection, Depends(get_db_connection)],
) -> dict[str, Any]:
    row = await assign_service.get_assignment(incident_id, conn=conn)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return row


@router.patch(
    "/{incident_id}",
    response_model=Assignment,
    summary="Assign, unassign, or change work state",
    description=(
        "Partial update. Send `expected_version` (from a prior read) to get a 409 "
        "instead of silently overwriting a change someone else made."
    ),
    responses={409: {"description": "The assignment changed since it was read."}},
)
async def update_assignment(
    incident_id: str,
    payload: AssignmentUpdate,
    actor_id: ActorId = None,
) -> dict[str, Any]:
    try:
        row = await assign_service.update_assignment(incident_id, payload, actor_id=actor_id)
    except StaleAssignmentVersion as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"This ticket was updated by someone else (version {exc.current_version}). "
                "Reload it and try again."
            ),
        ) from exc

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return row


@router.post(
    "/{incident_id}/comments",
    response_model=AssignmentEvent,
    status_code=status.HTTP_201_CREATED,
    summary="Comment on a ticket",
)
async def add_comment(
    incident_id: str,
    payload: CommentCreate,
    actor_id: ActorId = None,
) -> dict[str, Any]:
    row = await assign_service.add_comment(incident_id, payload.body, actor_id=actor_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return row


@router.get(
    "/{incident_id}/events",
    response_model=AssignmentEventListResponse,
    summary="Activity feed for one ticket",
)
async def list_events(
    incident_id: str,
    conn: Annotated[AsyncConnection, Depends(get_db_connection)],
) -> dict[str, Any]:
    items = await assign_service.list_events(incident_id, conn=conn)
    return {"items": items, "count": len(items)}
