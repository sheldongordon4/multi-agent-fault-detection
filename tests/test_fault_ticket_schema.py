from app.faults.schemas import EvidenceWindow, FaultTicket, KBCitation


def test_fault_ticket_instantiation():
    ticket = FaultTicket(
        ticket_id="T-001",
        scenario="feeder:ieee13",
        bus_id="b671",
        fault_type="Ground fault (SLG/LLG) near b671",
        severity="high",
        status="diagnosed",
        summary="A single-line-to-ground fault was diagnosed on feeder ieee13 at b671.",
        root_cause="Elevated zero-sequence current indicates ground involvement.",
        recommended_actions=["Inspect b671 protection zone", "Verify relay settings"],
        evidence=[
            EvidenceWindow(
                start_timestamp="2026-06-30T00:00:00Z",
                end_timestamp="2026-06-30T00:00:01Z",
                metric="voltage",
                description="Deep sag at b671 with high I0/I1.",
            )
        ],
        kb_citations=[
            KBCitation(source_id="SOP-OVLD-001", title="Feeder Overload", section="3.1")
        ],
        created_at="2026-06-30T00:00:02Z",
    )

    assert ticket.ticket_id == "T-001"
    assert ticket.severity == "high"
    assert len(ticket.recommended_actions) == 2
    assert ticket.evidence[0].metric == "voltage"
    assert ticket.kb_citations[0].source_id == "SOP-OVLD-001"
