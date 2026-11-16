"""
Ticket enrichment: the numbers an operator acts on must not be model output.

Confidence, customer impact and attribution are all facts the pipeline already
measured. The coordinator's LLM sees a summary of the detection and could
plausibly restate any of them — and a restated measurement is a paraphrase.
These tests pin that the values on the ticket come from the detection payload
and the customer table, and that a ticket survives their absence.
"""

import pytest

from app.faults import customers
from app.faults.schemas import FaultTicket
from app.faults.service import _enrich_ticket

BASE_TICKET = {
    "ticket_id": "T-1",
    "scenario": "feeder:ieee13",
    "bus_id": "b671",
    "fault_type": "SLG near b671 (~0.4 km)",
    "severity": "high",
    "status": "diagnosed",
    "summary": "Phase-A to ground.",
    "root_cause": "Elevated zero-sequence current.",
    "recommended_actions": ["Inspect b671"],
    "evidence": [],
    "kb_citations": [],
    "created_at": "2026-09-10T00:00:00Z",
}

DETECTION = {
    "feeder": "ieee13",
    "classification": {
        "fault_type": "SLG",
        "confidence": 0.94,
        "alternatives": [{"fault_type": "LLG", "confidence": 0.04}],
    },
    "attribution": [
        {
            "feature": "max_I0_I1_fault_b671",
            "bus": "b671",
            "family": "max_I0_I1_fault",
            "label": "zero-sequence current ratio",
            "meaning": "current returning through ground",
            "value": 0.368,
            "baseline": 0.003,
            "sigma": 121.0,
            "direction": "above",
        }
    ],
}


def _enriched(ticket=None, detection=None) -> dict:
    return _enrich_ticket(dict(ticket or BASE_TICKET), detection or DETECTION)


def test_confidence_comes_from_the_classifier():
    out = _enriched()
    assert out["fault_type_confidence"] == 0.94
    assert out["fault_type_alternatives"][0]["fault_type"] == "LLG"


def test_a_confidence_the_model_wrote_is_overwritten():
    """
    The one that matters.

    An LLM-invented confidence would be most wrong exactly where the classifier
    is least sure, which is the only situation the field exists to expose.
    """
    invented = {**BASE_TICKET, "fault_type_confidence": 1.0, "fault_type_alternatives": []}
    out = _enrich_ticket(invented, DETECTION)

    assert out["fault_type_confidence"] == 0.94
    assert out["fault_type_alternatives"], "runner-up was dropped in favour of the model's claim"


def test_customer_impact_is_looked_up_from_the_bus_the_ticket_names():
    """
    Not the bus detection ranked first.

    The coordinator can name a different bus from the top-buses list, and the
    ticket's bus is the one a crew is sent to.
    """
    out = _enriched({**BASE_TICKET, "bus_id": "b650"})

    assert out["customers_affected"] == customers.DOWNSTREAM_CUSTOMERS["b650"]
    assert out["customers_share"] == 1.0, "the feeder head must read as the whole feeder"


def test_a_fault_further_down_the_feeder_affects_fewer_customers():
    """Radial nesting is the property that makes the number worth ranking on."""
    head = _enriched({**BASE_TICKET, "bus_id": "b650"})["customers_affected"]
    tail = _enriched({**BASE_TICKET, "bus_id": "b675"})["customers_affected"]

    assert tail < head


def test_an_unmodelled_bus_reports_nothing_rather_than_zero():
    """
    "0 customers affected" reads as "nobody cares" and an operator would act on
    it. Absent means unknown.
    """
    out = _enriched({**BASE_TICKET, "bus_id": "b999"})

    assert out.get("customers_affected") is None
    assert out.get("customers_share") is None


def test_attribution_travels_from_the_detection_payload():
    out = _enriched()
    assert out["attribution"][0]["feature"] == "max_I0_I1_fault_b671"


def test_a_bare_detection_still_produces_a_valid_ticket():
    """Every enrichment is optional; none of them may cost the incident."""
    out = _enrich_ticket(dict(BASE_TICKET), {"feeder": "ieee13"})
    ticket = FaultTicket.model_validate(out)

    assert ticket.fault_type_confidence is None
    assert ticket.attribution == []
    assert ticket.fault_type == BASE_TICKET["fault_type"]


def test_the_enriched_ticket_validates_against_the_schema():
    ticket = FaultTicket.model_validate(_enriched())

    assert ticket.fault_type_confidence == 0.94
    assert ticket.attribution[0].bus == "b671"
    assert ticket.customers_affected == customers.DOWNSTREAM_CUSTOMERS["b671"]


@pytest.mark.parametrize("bus", sorted(customers.DOWNSTREAM_CUSTOMERS))
def test_every_modelled_bus_has_a_positive_customer_count(bus: str):
    assert customers.customers_affected(bus) > 0


def test_customer_counts_nest_by_radial_position():
    """
    b650 is the source, so nothing downstream of it can serve more customers.

    Pinned because the counts are placeholders: whoever replaces them with the
    utility's real figures has to preserve the nesting, or a leaf fault starts
    outranking a feeder-wide outage.
    """
    order = ["b650", "b632", "b671", "b684"]
    counts = [customers.DOWNSTREAM_CUSTOMERS[b] for b in order]

    assert counts == sorted(counts, reverse=True)
    assert customers.TOTAL_CUSTOMERS == customers.DOWNSTREAM_CUSTOMERS["b650"]
