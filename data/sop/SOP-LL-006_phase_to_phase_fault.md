ID: SOP-LL-006
TITLE: Phase-to-Phase Fault Response
SECTION: 7.2 Short-Circuit Faults — No Ground Path
URL: https://internal.example/sops/phase_to_phase_fault

SYNTHETIC REFERENCE — generated for the MAFD knowledge base from standard
protection practice (IEEE C37 series conventions). Not an approved JPS
procedure; review and adopt through the utility's own document control before
any operational use.

This SOP describes how to respond to a phase-to-phase (LL) fault — two phase
conductors in contact with each other, with no path to ground.

Conditions:
- Two phase voltages are depressed; the third remains close to nominal.
- Negative-sequence ratio (I2/I1) is clearly elevated.
- Zero-sequence ratio (I0/I1) is LOW. This absence is the diagnostic feature: an
  LL fault has no ground return path, so no appreciable zero-sequence current
  circulates. If both I0 and I2 are elevated, the fault involves ground and
  SOP-LLG-007 applies instead.
- Phase overcurrent elements (50/51) operated without ground element operation.

Trip Criteria:
- Phase overcurrent pickup exceeded per the approved time-current curve.
- Instantaneous phase element operation for close-in faults.
- No ground element operation — its absence should be confirmed, not assumed.

Operator Actions:
1. Confirm from relay targets which two phases were involved, and specifically
   confirm that ground elements did NOT operate.
2. Common physical causes are conductor-to-conductor contact: galloping or
   swinging conductors in wind, a tree limb bridging two phases, a failed
   spacer, or animal or bird contact across insulators. Direct the patrol
   accordingly — this is a different search pattern from a ground fault.
3. Check whether the fault coincided with high wind or a storm. Conductor slap
   during wind is a classic transient LL cause and will often not leave physical
   evidence at the point of contact.
4. On lockout, patrol the section before re-energizing. Look upward at the
   conductor plane rather than at ground level.
5. Isolate and restore per SOP-FLISR-011 where the feeder allows sectionalizing.
6. Where conductor slap is suspected and recurs, refer to engineering for
   spacing, sag, or spacer-cable review.

Notes:
- LL faults carry high current and impose significant mechanical stress on
  conductors and equipment even when they clear quickly.
- An LL fault that evolves into LLG (ground involvement appearing after the
  initial contact) is common; if ground elements operate late in the event,
  treat the incident under SOP-LLG-007.
