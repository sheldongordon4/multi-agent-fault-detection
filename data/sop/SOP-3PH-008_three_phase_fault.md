ID: SOP-3PH-008
TITLE: Balanced Three-Phase Fault Response
SECTION: 7.4 Short-Circuit Faults — Balanced (LLL / LLLG)
URL: https://internal.example/sops/three_phase_fault

SYNTHETIC REFERENCE — generated for the MAFD knowledge base from standard
protection practice (IEEE C37 series conventions). Not an approved JPS
procedure; review and adopt through the utility's own document control before
any operational use.

This SOP describes how to respond to a balanced three-phase fault (LLL), with or
without ground involvement (LLLG). It is the least common fault type on
distribution and generally the most severe.

Conditions:
- All three phase voltages collapse together, deeply and symmetrically.
- BOTH sequence ratios are near zero. This is the counter-intuitive signature and
  the one most often misread: a balanced fault produces almost no negative- or
  zero-sequence current, because the fault itself is symmetrical. Deep sag with
  no sequence unbalance means three-phase, not "no fault".
- Phase overcurrent elements operate, typically instantaneous.
- Fault current is the highest of any fault type at a given location.

Trip Criteria:
- Instantaneous phase overcurrent operation is expected for close-in faults.
- Time overcurrent per the coordination study for faults further out.
- Any operation approaching equipment interrupting rating requires engineering
  review before the equipment is returned to service.

Operator Actions:
1. Confirm the balanced signature: all three phases depressed, sequence ratios
   near zero. If one phase is materially different from the others, reclassify.
2. Treat as the highest-severity electrical event on the feeder. Check for
   equipment damage indications at the substation as well as on the line.
3. Consider the most common causes in order: switching error, safety grounds
   left connected after maintenance, equipment failure (a failed transformer,
   cable termination, or switchgear), and vehicle or crane contact.
4. If maintenance or switching was in progress on the affected section, STOP and
   confirm with the crew and the switching order holder before any restoration
   attempt. Re-energizing onto connected safety grounds endangers people.
5. Do not attempt repeated reclosing. A permanent three-phase fault subjects
   equipment to the highest available fault current on each attempt.
6. Verify breaker and interrupter condition before returning to service.
   Interrupting a three-phase fault is the most demanding duty the device
   performs.
7. Escalate to protection engineering and to operations management. Record fault
   current magnitude against the study assumptions.

Notes:
- LLLG behaves electrically much like LLL; the ground path adds zero-sequence
  current but the defining deep balanced sag is the same.
- A three-phase fault on a feeder that has just been worked on should be treated
  as a switching or grounding error until proven otherwise.
