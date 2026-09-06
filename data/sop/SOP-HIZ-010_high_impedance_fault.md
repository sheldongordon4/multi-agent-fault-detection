ID: SOP-HIZ-010
TITLE: High-Impedance Fault Investigation
SECTION: 7.6 Short-Circuit Faults — Impedance-Limited
URL: https://internal.example/sops/high_impedance_fault

SYNTHETIC REFERENCE — generated for the MAFD knowledge base from standard
protection practice (IEEE C37 series conventions). Not an approved JPS
procedure; review and adopt through the utility's own document control before
any operational use.

This SOP describes how to respond to a suspected high-impedance fault (HIF) — a
fault whose current is limited by the resistance of the contact path rather than
by system impedance. It corresponds to impedance-limited short circuits
(non-bolted faults) in the detection model.

The defining problem: HIF current is often BELOW normal load current, so
overcurrent protection does not operate and the feeder continues to serve
customers normally while an energized conductor lies on the ground.

Conditions:
- A downed conductor resting on a poor-conducting surface: dry soil, sand,
  asphalt, concrete, gravel, or vegetation.
- Fault current typically a small fraction of available bolted fault current,
  frequently in the tens of amperes.
- Intermittent, erratic current with arcing signatures; harmonic content and
  randomness rather than a clean fundamental step.
- Voltage sag is mild or absent — this is why HIF does not look like a fault.
- No protective device operation.

Trip Criteria:
- Conventional overcurrent elements are NOT expected to operate and must not be
  relied upon for this condition.
- Dedicated high-impedance fault detection (arc-signature or harmonic-based),
  where fitted, provides an alarm rather than a trip in most schemes.
- Any alarm should be treated as credible and investigated on the ground.

Operator Actions:
1. Treat every report of a downed conductor as an energized high-impedance fault
   regardless of what SCADA and protection indicate. Public reports are often the
   only detection mechanism available for this condition.
2. Dispatch immediately and establish a safety perimeter. Do not wait for
   electrical confirmation that may never come.
3. De-energize the affected section if a downed conductor is confirmed or
   credibly reported. The decision to interrupt supply is justified by the
   hazard, not by the measured current.
4. Where HIF detection is fitted and has alarmed, correlate with any customer
   calls, weather, and recent switching before dismissing it.
5. After the conductor is made safe, inspect for the cause — insulator failure,
   pole damage, tree contact, or connector failure.
6. Record the event with measured current if available. HIF cases are valuable
   for tuning detection and are frequently under-recorded.

Notes:
- HIF is the highest public-safety-risk fault class precisely because the system
  tolerates it electrically. Step and touch potential near a downed energized
  conductor is lethal.
- Absence of a trip, absence of customer outage, and normal SCADA indications are
  all consistent with an active high-impedance fault. None of them clears a
  report.
