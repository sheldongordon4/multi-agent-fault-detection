"""
How many customers a fault takes out.

Severity ranks incidents by anomaly score, which is the model's confidence that
something is wrong — not a measure of how much it matters. A utility does not
dispatch on anomaly score. It dispatches on customers affected, and it reports
to its regulator in the same unit. "High severity at b650" and "14,200 customers
out at Kingston" describe the same event, and only one of them tells a control
room which truck to send first.

RADIAL POSITION IS THE WHOLE POINT
----------------------------------
On a radial feeder everything downstream of a fault loses supply, so the count
is not a property of the bus — it is the size of the subtree below it. b650 sits
at the source, so a fault there takes the entire feeder; b675 is a leaf and
takes only its own spot load. That is why a low-severity fault at the head can
outrank a high-severity one at the tail, which is exactly the judgement an
operator is making and the reason this number belongs on the ticket.

SYNTHETIC COUNTS — REPLACE BEFORE OPERATIONAL USE
-------------------------------------------------
JPS does not publish per-feeder customer counts, so the numbers below are
invented at plausible magnitudes for the towns the buses are mapped to (see the
frontend's bus-locations.ts, which is placeholder in the same way and for the
same reason). The NESTING is real — it follows the IEEE13 radial topology — but
no individual figure is. Replace `DOWNSTREAM_CUSTOMERS` with the utility's own
per-section counts and nothing else here has to change.
"""

from __future__ import annotations

# bus_id -> customers fed through that bus, including everything downstream.
#
# Nested by radial position: b650 (source) >= b632 >= b671 >= {b684, b675}.
# A fault at the source is a feeder-wide outage; a fault at a leaf is a street.
DOWNSTREAM_CUSTOMERS: dict[str, int] = {
    "b650": 14200,  # feeder head at Kingston — the whole feeder
    "b632": 11800,  # primary trunk, Spanish Town
    "b671": 6400,  # mid-feeder tap, Mandeville
    "b684": 1750,  # lateral, Portmore
    "b675": 980,  # spot load, Montego Bay
}

# Used when a ticket names a bus the table does not know: a retrained model, a
# different feeder, or an unparsed id. Deliberately not zero — reporting "0
# customers affected" for a real fault reads as "nobody cares" rather than as
# "unknown", and an operator would act on it.
UNKNOWN_BUS_CUSTOMERS: int | None = None

# Everything the modelled feeder serves. The head bus by definition.
TOTAL_CUSTOMERS: int = max(DOWNSTREAM_CUSTOMERS.values(), default=0)


def customers_affected(bus_id: str | None) -> int | None:
    """
    Customers downstream of `bus_id`, or None when the bus is not modelled.

    None rather than 0 so callers can distinguish "no impact" from "no data" —
    the UI shows the first as a number and the second as nothing at all.
    """
    if not bus_id:
        return UNKNOWN_BUS_CUSTOMERS
    return DOWNSTREAM_CUSTOMERS.get(bus_id.strip(), UNKNOWN_BUS_CUSTOMERS)


def impact_share(bus_id: str | None) -> float | None:
    """Fraction of the feeder's customers affected, 0..1, or None if unknown."""
    count = customers_affected(bus_id)
    if count is None or TOTAL_CUSTOMERS <= 0:
        return None
    return round(count / TOTAL_CUSTOMERS, 4)
