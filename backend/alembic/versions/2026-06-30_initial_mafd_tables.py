"""initial mafd tables

Creates the persistence-layer tables: notifications (operator alerts) and
fault_tickets (the validated FaultTicket history, keyed by incident_id for
idempotency). Hand-written and static/reversible per project conventions.

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("read", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("incident_id", sa.String(length=128), nullable=True),
        sa.Column("bus_id", sa.String(length=64), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="notifications_pkey"),
    )
    op.create_index("notifications_incident_id_idx", "notifications", ["incident_id"])
    op.create_index("notifications_bus_id_idx", "notifications", ["bus_id"])

    op.create_table(
        "fault_tickets",
        sa.Column("incident_id", sa.String(length=128), nullable=False),
        sa.Column("ticket_id", sa.String(length=128), nullable=False),
        sa.Column("scenario", sa.String(length=64), nullable=True),
        sa.Column("bus_id", sa.String(length=64), nullable=True),
        sa.Column("fault_type", sa.String(length=128), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("incident_id", name="fault_tickets_pkey"),
    )
    op.create_index("fault_tickets_bus_id_idx", "fault_tickets", ["bus_id"])


def downgrade() -> None:
    op.drop_index("fault_tickets_bus_id_idx", table_name="fault_tickets")
    op.drop_table("fault_tickets")
    op.drop_index("notifications_bus_id_idx", table_name="notifications")
    op.drop_index("notifications_incident_id_idx", table_name="notifications")
    op.drop_table("notifications")
