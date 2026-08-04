from fastapi import APIRouter, status

from app.faults.schemas import DiagnoseRequest, FaultTicket
from app.faults.service import run_fault_diagnosis

router = APIRouter(prefix="/faults", tags=["faults"])


@router.post(
    "/diagnose",
    response_model=FaultTicket,
    status_code=status.HTTP_200_OK,
    summary="Diagnose a detected fault",
)
def diagnose_fault(req: DiagnoseRequest) -> dict:
    """
    Run the coordinator (kb_retrieve + LLM) on a detection result and return a
    FaultTicket. Detection runs upstream; this endpoint diagnoses its output.
    """
    detection = {
        "feeder": req.feeder,
        "incident_id": req.incident_id,
        "verdict": {"severity": req.severity, "anomalyScore": req.anomaly_score},
        "topBuses": [b.model_dump() for b in req.top_buses],
    }
    return run_fault_diagnosis(detection)
