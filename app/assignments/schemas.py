from datetime import datetime

from pydantic import BaseModel, Field

from app.assignments.constants import EventKind, OperatorRole, Priority, WorkState


class OperatorBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    initials: str = Field(min_length=1, max_length=4)
    role: OperatorRole = OperatorRole.CONTROL_ROOM
    parish: str | None = Field(default=None, max_length=64)
    capacity: int = Field(default=5, ge=1, le=99)
    on_shift: bool = False
    active: bool = True


class OperatorCreate(OperatorBase):
    pass


class OperatorUpdate(BaseModel):
    """Every field optional — a PATCH only carries what changed."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    initials: str | None = Field(default=None, min_length=1, max_length=4)
    role: OperatorRole | None = None
    parish: str | None = Field(default=None, max_length=64)
    capacity: int | None = Field(default=None, ge=1, le=99)
    on_shift: bool | None = None
    active: bool | None = None


class Operator(OperatorBase):
    id: str
    created_at: datetime

    model_config = {"from_attributes": True}


class OperatorWithLoad(Operator):
    """Roster entry plus the open-ticket count, aggregated in SQL."""

    open_count: int = 0


class OperatorListResponse(BaseModel):
    items: list[OperatorWithLoad]
    count: int


class AssignmentEvent(BaseModel):
    id: str
    incident_id: str
    actor_id: str | None = None
    actor_name: str | None = None
    kind: EventKind
    from_value: str | None = None
    to_value: str | None = None
    body: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AssignmentEventListResponse(BaseModel):
    items: list[AssignmentEvent]
    count: int


class Assignment(BaseModel):
    """
    A fault ticket joined to its assignment row.

    Ticket columns are a projection of `fault_tickets`; everything from
    `work_state` down comes from `ticket_assignments`, which may not exist yet —
    an unassigned ticket is the LEFT JOIN's NULL side, defaulted here.
    """

    incident_id: str
    ticket_id: str
    bus_id: str | None = None
    scenario: str | None = None
    fault_type: str | None = None
    severity: str | None = None
    # The coordinator's diagnostic status, NOT the workflow state below.
    status: str | None = None
    summary: str | None = None
    created_at: datetime

    work_state: WorkState = WorkState.UNASSIGNED
    priority: Priority = Priority.P3
    assignee_id: str | None = None
    assignee_name: str | None = None
    assignee_initials: str | None = None
    due_at: datetime | None = None
    note: str | None = None
    version: int = 0
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class AssignmentListResponse(BaseModel):
    items: list[Assignment]
    count: int


class AssignmentUpdate(BaseModel):
    """
    A partial write. Omitted fields are left alone; `assignee_id` is explicitly
    nullable, so `{"assignee_id": null}` unassigns.
    """

    assignee_id: str | None = None
    work_state: WorkState | None = None
    priority: Priority | None = None
    due_at: datetime | None = None
    note: str | None = None

    # Optimistic concurrency: send the version you read. Omit to force the write.
    expected_version: int | None = None

    model_config = {"extra": "forbid"}


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
