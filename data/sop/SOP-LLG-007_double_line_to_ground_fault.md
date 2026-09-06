ID: SOP-LLG-007
TITLE: Double Line-to-Ground Fault Response
SECTION: 7.3 Short-Circuit Faults — Two Phases and Ground
URL: https://internal.example/sops/double_line_to_ground_fault

SYNTHETIC REFERENCE — generated for the MAFD knowledge base from standard
protection practice (IEEE C37 series conventions). Not an approved JPS
procedure; review and adopt through the utility's own document control before
any operational use.

This SOP describes how to respond to a double line-to-ground (LLG) fault — two
phase conductors faulted to ground, either simultaneously or by evolution from a
single-phase or phase-to-phase fault.

Conditions:
- Two phase voltages are deeply depressed; the third is affected but less so.
- BOTH sequence ratios are elevated: zero-sequence (I0/I1) confirms ground
  involvement, negative-sequence (I2/I1) confirms unbalance. The presence of both
  together is what separates LLG from LL (ground absent) and from a balanced
  three-phase fault (both near zero).
- Both phase and ground overcurrent elements operated.

Trip Criteria:
- Phase and ground overcurrent pickup exceeded per the coordination study.
- Instantaneous elements typically operate: LLG fault current is generally higher
  than SLG at the same location.
- Lockout after the programmed reclose sequence indicates a permanent fault.

Operator Actions:
1. Confirm from relay targets that both phase and ground elements operated, and
   identify which two phases were involved.
2. Treat this as a severe fault. LLG imposes higher current and greater thermal
   and mechanical stress than SLG, and is more likely to have caused equipment
   damage at the fault point.
3. Consider evolution: many LLG faults begin as something else. Review the event
   record for whether ground involvement appeared at inception or later. An
   evolving fault points to a mechanism that is progressing, such as a failing
   insulator or an encroaching tree.
4. On lockout, patrol before re-energizing. Treat any conductor on the ground as
   energized.
5. Inspect for physical damage at the fault location before restoration —
   conductor annealing, burnt hardware, damaged insulators, and pole damage are
   more likely here than with a lower-current fault.
6. Isolate and restore per SOP-FLISR-011.
7. Escalate to protection engineering if the measured fault current materially
   exceeds the coordination study's assumptions for that location.

Notes:
- Structural damage at the fault point is common. Restoration should not proceed
  on electrical indications alone without a visual inspection.
- LLG close to the substation can approach three-phase fault levels and should be
  reviewed against equipment interrupting ratings.
