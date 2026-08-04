from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncConnection

from app.database import get_db_connection
from app.persistence import service as persist_service
from app.persistence.schemas import TicketDetail, TicketListResponse

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.get("", response_model=TicketListResponse, summary="List fault ticket history")
async def list_tickets(
    conn: Annotated[AsyncConnection, Depends(get_db_connection)],
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> dict[str, Any]:
    items = await persist_service.list_tickets(limit=limit, conn=conn)
    return {"items": items, "count": len(items)}


@router.get("/{incident_id}", response_model=TicketDetail, summary="Get one fault ticket")
async def get_ticket(
    incident_id: str,
    conn: Annotated[AsyncConnection, Depends(get_db_connection)],
) -> dict[str, Any]:
    ticket = await persist_service.get_ticket(incident_id, conn=conn)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return ticket
