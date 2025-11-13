from datetime import datetime

from app.models.fault_ticket import FaultTicket


def test_fault_ticket_instantiation():
    ticket = FaultTicket(
        ticket_id="T-001",
        scenario_id="Overload Trip",
        root_cause="Overcurrent condition on feeder",
        summary="Feeder overloaded causing protective trip.",
        details={
            "bus_id": "BUS-01",
            "max_current_a": 350,
            "relay_flags": {"50": 1, "51": 1},
        },
        recommendations=["Inspect feeder load", "Verify relay settings"],
        kb_citations=["SOP-OVERCURRENT-01"],
    )

    assert ticket.ticket_id == "T-001"
    assert ticket.scenario_id == "Overload Trip"
    assert isinstance(ticket.created_at, datetime)
    assert isinstance(ticket.detected_at, datetime)
    assert "max_current_a" in ticket.details
    assert len(ticket.recommendations) == 2
