ID: SOP-FLISR-011
TITLE: Fault Location, Isolation and Service Restoration
SECTION: 8.1 Restoration Sequence
URL: https://internal.example/sops/fault_location_isolation_restoration

SYNTHETIC REFERENCE — generated for the MAFD knowledge base from standard
protection practice (IEEE C37 series conventions). Not an approved JPS
procedure; review and adopt through the utility's own document control before
any operational use.

This SOP describes the sequence used to restore supply after a feeder fault,
independent of the fault type. The fault-type SOPs (SOP-SLG-005 through
SOP-HIZ-010) describe how to identify and make safe a specific fault; this one
describes how to get customers back on afterwards.

The order is deliberate and must not be reversed: LOCATE, then ISOLATE, then
RESTORE. Restoring before isolating re-energizes the fault.

Conditions:
- A protective device has operated and locked out, or a section has been
  de-energized deliberately in response to a fault.
- The faulted section is known or can be narrowed by device operation, fault
  indicators, and the estimated fault location.

Trip Criteria:
- Not applicable. This procedure begins after protection has already operated.

Operator Actions:
1. LOCATE. Combine three independent sources rather than trusting any one:
   which devices operated and in what order, faulted-circuit indicators along the
   line, and the estimated distance-to-fault. Treat a distance estimate as a
   search prioritisation, not a coordinate — it assumes a homogeneous line and
   degrades with fault resistance and load.
2. Confirm the fault type from the relay record and follow the corresponding
   fault-type SOP for hazards specific to it — particularly the downed-conductor
   cases (SOP-SLG-005, SOP-OPEN-009, SOP-HIZ-010).
3. ISOLATE. Open the sectionalizing devices on both sides of the faulted section.
   Confirm each device's position individually; do not assume a ganged operation
   completed on all phases.
4. Establish and confirm clearances before any field work. Apply safety grounds
   at the work location and record them on the switching order.
5. RESTORE the healthy sections. Back-feed the downstream healthy section from an
   alternate source where the tie allows and loading permits — check that the
   receiving feeder can carry the transferred load within its continuous rating
   (SOP-OVLD-001) before closing the tie.
6. Repair the faulted section, then remove grounds and clearances in the reverse
   order they were applied, confirming each removal against the switching order.
7. Re-energize the repaired section and confirm normal voltage and balanced
   current on all three phases before returning the feeder to its normal
   configuration.
8. Record final configuration, and explicitly confirm that any temporary
   switching has been returned to normal. An unreturned temporary configuration
   invalidates the coordination study.

Notes:
- Load transferred to an adjacent feeder during restoration is a common cause of
  a subsequent overload trip on the receiving feeder. Check before closing, and
  monitor after.
- Every temporary protection setting change made to enable restoration must be
  logged and reverted (SOP-MISC-002).
