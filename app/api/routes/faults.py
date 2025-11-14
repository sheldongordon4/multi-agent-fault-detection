# app/api/routes/faults.py
from fastapi import APIRouter
from pydantic import BaseModel

from app.services.coordinator_service import run_fault_diagnosis

router = APIRouter(prefix="/faults", tags=["faults"])


class DiagnoseRequest(BaseModel):
    scenario: str
    bus_id: str
    window_sec: int = 300


@router.post("/diagnose")
def diagnose_fault(req: DiagnoseRequest):
    """
    Run the LLM coordinator: detect_signal + kb_retrieve, and return a FaultTicket.
    """
    ticket = run_fault_diagnosis(
        scenario=req.scenario,
        bus_id=req.bus_id,
        window_sec=req.window_sec,
    )
    return ticket
