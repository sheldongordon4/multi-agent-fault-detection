ID: SOP-OPEN-009
TITLE: Open Conductor and Single-Phasing Response
SECTION: 7.5 Series Faults — Open Conductor (1PH / 2PH / 3PH)
URL: https://internal.example/sops/open_conductor

SYNTHETIC REFERENCE — generated for the MAFD knowledge base from standard
protection practice (IEEE C37 series conventions). Not an approved JPS
procedure; review and adopt through the utility's own document control before
any operational use.

This SOP describes how to respond to an open-conductor (series) fault — one, two,
or all three phases interrupted without a short circuit. Causes include a broken
conductor, a blown fuse on one phase, a failed connector or splice, and a single
pole of a switch or breaker failing to close.

An open conductor is the hardest fault class to detect and among the most
dangerous, because it produces UNBALANCE WITHOUT FAULT CURRENT. Overcurrent
protection may not operate at all.

Conditions:
- Current on the affected phase falls toward zero while its voltage remains
  present or floats at an intermediate value, backfed through connected load.
- Negative-sequence current and voltage are elevated; zero-sequence may be
  present depending on the grounding and load configuration.
- Downstream three-phase customers experience single-phasing.
- No overcurrent operation, or an unexplained fuse operation on one phase only.

Trip Criteria:
- Negative-sequence overcurrent (46) or voltage-unbalance elements, where fitted.
- Broken-conductor / current-unbalance detection where fitted.
- Note explicitly: standard phase and ground overcurrent elements may NEVER
  operate for this condition. Absence of a trip is not evidence of a healthy
  feeder.

Operator Actions:
1. Treat any suspected broken conductor as ENERGIZED AND ON THE GROUND until a
   patrol proves otherwise. A conductor open at the source end can still be
   energized from the load side.
2. Understand the backfeed path before approaching: three-phase motors,
   distributed generation, and customer generators can energize an open
   conductor from the load side even after the feeder breaker is open. Confirm
   the section is isolated on ALL sides and grounded before any work.
3. Confirm the affected phase from SCADA phase currents; the near-zero current
   with intact voltage is the identifying pattern.
4. Notify downstream three-phase customers where practical. Single-phasing
   damages three-phase motors quickly through overheating and can destroy them
   within minutes.
5. Patrol the section for a broken conductor, a failed splice or connector, or an
   open fuse or switch pole. Check switch and recloser pole positions
   individually rather than assuming ganged operation succeeded.
6. Do not restore by closing the open device until the cause is identified. If a
   fuse operated on one phase only, find out why before replacing it.
7. Escalate persistent or repeated single-phasing to engineering — a marginal
   connector will recur.

Notes:
- OPEN_2PH and OPEN_3PH follow the same procedure with progressively more of the
  feeder de-energized. OPEN_3PH may present simply as loss of supply.
- The public-safety profile of a broken conductor is comparable to a
  high-impedance fault (SOP-HIZ-010) and should be handled with the same urgency.
