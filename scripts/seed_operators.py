"""
Seed a starter operator roster.

Operators are roster entries, not user accounts — MAFD has no auth, so there are
no credentials to set here (see app/assignments/models.py::Operator). Idempotent:
matches on name, so re-running updates rather than duplicating.

    .venv/Scripts/python.exe scripts/seed_operators.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

import sqlalchemy as sa  # noqa: E402

from app.assignments.constants import OperatorRole  # noqa: E402
from app.assignments.models import Operator  # noqa: E402
from app.database import engine  # noqa: E402

# Parishes match the shading already on the console map (frontend/public/map).
ROSTER: list[dict] = [
    {
        "name": "K. Reid",
        "initials": "KR",
        "role": OperatorRole.CONTROL_ROOM,
        "parish": "Kingston",
        "capacity": 6,
        "on_shift": True,
    },
    {
        "name": "D. Chin",
        "initials": "DC",
        "role": OperatorRole.CONTROL_ROOM,
        "parish": "St. Andrew",
        "capacity": 6,
        "on_shift": True,
    },
    {
        "name": "M. Grant",
        "initials": "MG",
        "role": OperatorRole.FIELD_CREW,
        "parish": "St. Catherine",
        "capacity": 4,
        "on_shift": True,
    },
    {
        "name": "S. Palmer",
        "initials": "SP",
        "role": OperatorRole.FIELD_CREW,
        "parish": "Clarendon",
        "capacity": 4,
        "on_shift": False,
    },
    {
        "name": "A. Bennett",
        "initials": "AB",
        "role": OperatorRole.PROTECTION_ENG,
        "parish": "Kingston",
        "capacity": 3,
        "on_shift": True,
    },
    {
        "name": "R. Wallace",
        "initials": "RW",
        "role": OperatorRole.SUPERVISOR,
        "parish": "Kingston",
        "capacity": 8,
        "on_shift": True,
    },
]


async def seed() -> None:
    created = updated = 0

    async with engine.connect() as conn:
        for entry in ROSTER:
            values = {**entry, "role": str(entry["role"])}
            existing = await conn.execute(
                sa.select(Operator.id).where(Operator.name == values["name"])
            )
            row = existing.first()

            if row is None:
                await conn.execute(sa.insert(Operator).values(**values))
                created += 1
            else:
                await conn.execute(
                    sa.update(Operator).where(Operator.id == row[0]).values(**values)
                )
                updated += 1

        await conn.commit()

    print(f"Roster seeded: {created} created, {updated} updated.")


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
