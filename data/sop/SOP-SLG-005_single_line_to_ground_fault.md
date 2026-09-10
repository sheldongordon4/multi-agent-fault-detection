ID: SOP-SLG-005
TITLE: Single Line-to-Ground Fault Response
SECTION: 7.1 Short-Circuit Faults — Ground Involved
URL: https://internal.example/sops/single_line_to_ground_fault

SYNTHETIC REFERENCE — generated for the MAFD knowledge base from standard
protection practice (IEEE C37 series conventions). Not an approved JPS
procedure; review and adopt through the utility's own document control before
any operational use.

This SOP describes how to respond to a single line-to-ground (SLG) fault on a
distribution feeder — one phase conductor in contact with ground, a grounded
structure, or the neutral.

SLG is the most common fault on overhead distribution, typically the majority of
all feeder faults. Most are transient (a flashover that clears on interruption)
but a persistent SLG is the signature most associated with a downed conductor,
which is why this procedure treats patrol before re-energization as mandatory
rather than discretionary.

Conditions:
- One phase voltage collapses while the other two remain near nominal.
- Zero-sequence current ratio (I0/I1) is clearly elevated — this is what
  distinguishes a ground fault from a phase-to-phase fault.
- Negative-sequence ratio (I2/I1) is also elevated: an SLG is an unbalanced
  fault, so both sequence quantities appear together.
- Ground overcurrent elements (50N/51N) or a residual relay have operated.

Trip Criteria:
- Ground overcurrent pickup exceeded for the time defined by the ground
  time-current curve in the approved coordination study.
- Instantaneous ground element operation for close-in, high-current faults.
- Recloser cycles through its programmed sequence; lockout after the final shot
  indicates a permanent fault.

Operator Actions:
1. Confirm from relay targets and SCADA which phase was involved and whether
   ground elements operated. A ground element operation with a healthy
   phase-to-phase signature is the confirming evidence for SLG.
2. Determine whether the recloser locked out or held. A hold indicates a
   transient fault; a lockout must be treated as a permanent fault with a
   possible downed conductor.
3. On lockout, DO NOT test-close before patrol. Dispatch a patrol of the faulted
   section and treat any conductor on the ground as energized regardless of
   indications.
4. Use the estimated fault location to prioritise the patrol, but do not let it
   narrow the patrol to the exclusion of the rest of the protected section — a
   location estimate is an estimate.
5. Where the feeder can be sectionalized, isolate the faulted section and restore
   unaffected customers upstream and downstream per SOP-FLISR-011.
6. After the fault is found and cleared, verify insulation resistance or perform
   the local equivalent test before re-energizing.
7. If patrol finds nothing and the fault does not recur on a controlled
   re-energization, record it as transient and monitor for repetition — repeated
   transient SLG at the same location often precedes a permanent failure.

Notes:
- Public safety takes precedence over restoration time. A downed energized
  conductor is the single highest-consequence outcome of an SLG.
- High-impedance ground faults may produce very little current and may not
  operate ground overcurrent at all — see SOP-HIZ-010.
- Repeated SLG on the same phase and section suggests a specific defect
  (cracked insulator, tree contact, animal path) rather than random events.
