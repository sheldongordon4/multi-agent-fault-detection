from pydantic import BaseModel


class BusListResponse(BaseModel):
    """Buses currently held in the streaming service's rolling buffers."""

    items: list[str]
    count: int
