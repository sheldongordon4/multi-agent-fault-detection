"""add operator assignments

Adds the ticket-assignment tables: operators (a roster, NOT user accounts —
MAFD has no auth), ticket_assignments (one row per incident, created lazily on
first write) and assignment_events (append-only activity log, comments
included).

ticket_assignments is deliberately separate from fault_tickets: the persistence
handler upserts that table wholesale on every Kafka redelivery, so assignment
state stored there would be silently reset. Nothing in app/kafka/ writes here.

Revision ID: 0002_assignments
Revises: 0001_initial
Create Date: 2026-09-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_assignments"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operators",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("initials", sa.String(length=4), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("parish", sa.String(length=64), nullable=True),
        sa.Column("capacity", sa.Integer(), server_default="5", nullable=False),
        sa.Column("on_shift", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="operators_pkey"),
    )

    op.create_table(
        "ticket_assignments",
        sa.Column("incident_id", sa.String(length=128), nullable=False),
        sa.Column("assignee_id", sa.String(length=26), nullable=True),
        sa.Column("work_state", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=8), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("incident_id", name="ticket_assignments_pkey"),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["fault_tickets.incident_id"],
            name="ticket_assignments_incident_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["assignee_id"],
            ["operators.id"],
            name="ticket_assignments_assignee_id_fkey",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ticket_assignments_assignee_id_idx", "ticket_assignments", ["assignee_id"])
    op.create_index("ticket_assignments_work_state_idx", "ticket_assignments", ["work_state"])

    op.create_table(
        "assignment_events",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("incident_id", sa.String(length=128), nullable=False),
        sa.Column("actor_id", sa.String(length=26), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("from_value", sa.String(length=64), nullable=True),
        sa.Column("to_value", sa.String(length=64), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="assignment_events_pkey"),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["operators.id"],
            name="assignment_events_actor_id_fkey",
            ondelete="SET NULL",
        ),
    )
    op.create_index("assignment_events_incident_id_idx", "assignment_events", ["incident_id"])
    op.create_index("assignment_events_created_at_idx", "assignment_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("assignment_events_created_at_idx", table_name="assignment_events")
    op.drop_index("assignment_events_incident_id_idx", table_name="assignment_events")
    op.drop_table("assignment_events")

    op.drop_index("ticket_assignments_work_state_idx", table_name="ticket_assignments")
    op.drop_index("ticket_assignments_assignee_id_idx", table_name="ticket_assignments")
    op.drop_table("ticket_assignments")

    op.drop_table("operators")
