ID: SOP-MISC-002
TITLE: Feeder Relay Miscoordination Investigation
SECTION: 4.2 Relay Coordination and Nuisance Tripping
URL: https://internal.example/sops/feeder_relay_miscoordination

This SOP describes how to investigate and respond to suspected protection relay miscoordination
on distribution feeders and associated buses.

SECTION 2 — Fault Signature Identification

This section provides the symmetrical component and electrical feature signatures used to
identify the fault class before applying this SOP. All feature values are expressed in
per-unit or as dimensionless ratios unless otherwise stated.

Zero-sequence to positive-sequence current ratio (I0/I1):
- Values near 0.0 (< 0.05): No ground path involvement. Consistent with balanced three-phase
  faults (LLL, LLLG) or line-to-line faults (LL) where no ground return current flows.
- Values between 0.15 and 0.40: Moderate ground involvement. Consistent with open-conductor
  faults (OPEN_1PH, OPEN_2PH) where a phase is lost but the fault path is resistive or air.
- Values above 0.50: Strong ground involvement. Consistent with single-line-to-ground (SLG)
  or line-to-line-to-ground (LLG) faults where a direct ground path carries significant
  zero-sequence current.
- Values at or near 1.0: Very strong ground path. Characteristic of a bolted or low-impedance
  SLG fault. I0 approaches I1 in magnitude when most fault current flows through ground.

Negative-sequence to positive-sequence current ratio (I2/I1):
- Values near 0.0 (< 0.05): Balanced or symmetric condition. Consistent with balanced
  three-phase faults (LLL, LLLG) or overload conditions.
- Values between 0.15 and 0.35: Moderate unbalance. Consistent with open-conductor faults
  (OPEN_1PH, OPEN_2PH) where one or two phases are lost.
- Values between 0.40 and 0.60: Strong unbalance without dominant ground involvement.
  Characteristic of line-to-line (LL) faults where two phases are shorted but no ground
  return path is present.
- Values above 0.40 together with elevated I0/I1: Both ground involvement and phase unbalance
  present. Characteristic of line-to-line-to-ground (LLG) faults.

Minimum per-unit phase voltage (minVa_pu):
- Values above 0.85 pu: No significant fault. Consistent with overload or normal operation.
- Values between 0.50 and 0.85 pu: Partial voltage sag. Consistent with open-conductor faults
  (OPEN_1PH, OPEN_2PH) where partial load remains on surviving phases.
- Values below 0.25 pu: Deep voltage sag. Consistent with short-circuit fault conditions
  (SLG, LL, LLG) where the faulted phase collapses.
- Values near 0.0 pu: Complete voltage collapse on the affected phase. Consistent with
  bolted short-circuit faults.

Peak phase current magnitude (maxIa):
- Values below 0.5 pu above normal: Low fault current. Consistent with open-conductor faults
  (OPEN_1PH, OPEN_2PH) or high-impedance fault conditions where no large current surge occurs.
- Values between 2 and 5 pu: Moderate fault current surge. Consistent with impedance-type
  short-circuit faults (SLG, LL, LLG at higher impedance).
- Values above 5 pu: High fault current surge. Consistent with bolted or low-impedance
  short-circuit faults.

Fault type signatures applicable to this SOP:

SLG (Single Line-to-Ground):
  minVa typically < 0.10 pu; maxIa typically 3 to 7 pu; I0/I1 typically 0.7 to 1.0
  (near unity for bolted faults); I2/I1 typically 0.05 to 0.20.
  Interpretation: The near-unity I0/I1 ratio is the primary ground-fault indicator. Deep
  voltage sag on one phase with elevated current confirms a solid ground path. Relay
  miscoordination should be checked if multiple devices operated during clearing.

LL (Line-to-Line):
  minVa typically 0.15 to 0.25 pu on affected phases; maxIa typically 3 to 6 pu;
  I0/I1 typically < 0.02 (near zero, no ground path); I2/I1 typically 0.40 to 0.60.
  Interpretation: The near-zero I0/I1 distinguishes LL from ground-involved faults.
  Elevated I2/I1 confirms strong phase unbalance. Deep sag with high current and no
  zero-sequence confirms a phase-to-phase fault. Relay coordination check is required
  if the fault was not cleared by the nearest downstream device.

LLG (Line-to-Line-to-Ground):
  minVa typically 0.05 to 0.15 pu; maxIa typically 4 to 7 pu;
  I0/I1 typically 0.35 to 0.60; I2/I1 typically 0.35 to 0.55.
  Interpretation: Elevated both I0/I1 and I2/I1 simultaneously indicates a mixed fault
  with both ground involvement and phase unbalance. This is characteristic of LLG events.
  The combined sequence component elevation distinguishes LLG from pure SLG (dominant I0/I1)
  or pure LL (dominant I2/I1, near-zero I0/I1).

OPEN_1PH (Single Phase Open Conductor):
  minVa typically 0.55 to 0.70 pu; maxIa typically 0.05 to 0.25 pu (low, no surge);
  I0/I1 typically 0.15 to 0.30; I2/I1 typically 0.15 to 0.25.
  Interpretation: Low current magnitude distinguishes open-conductor faults from short-circuit
  faults. Moderate elevation of both sequence ratios reflects the asymmetry of the lost phase.
  Voltage sag is partial rather than deep because surviving phases remain energized. A nuisance
  relay operation with low fault current and moderate sag is characteristic of this fault type.

OPEN_2PH (Two Phase Open Conductor):
  minVa typically 0.35 to 0.50 pu; maxIa typically 0.10 to 0.30 pu;
  I0/I1 typically 0.25 to 0.45; I2/I1 typically 0.25 to 0.40.
  Interpretation: Higher sequence ratios than OPEN_1PH due to loss of two phases.
  Voltage sag is more pronounced. Current remains low. Relay trips with low current and
  significant sequence unbalance characterize this fault type.

Conditions:
- Multiple protective devices operate for the same event in a way that does not match the
  intended coordination study.
- Upstream devices trip for faults that should have been cleared by downstream devices.
- Nuisance trips occur with no clear corresponding fault on the primary equipment.

Trip Criteria:
- Unintended upstream trips during downstream faults or overloads.
- Trips that violate documented time-current coordination curves.
- Repeated relay operations without corresponding equipment damage or clear cause.

Operator Actions:
1. Confirm which relays and breakers operated and in what sequence, using SCADA and relay event logs.
2. Compare actual operations with the approved coordination study and time-current curves.
3. Verify that all protection settings in the relay are up to date and match the latest study.
4. If miscoordination is confirmed, temporarily adjust settings only under the guidance of
   protection engineering.
5. Document all changes, including rationale and responsible engineer, and schedule a full
   coordination review if repeated issues occur.
6. Restore normal settings once the underlying configuration or loading issue has been resolved.

Notes:
- Unapproved setting changes can create hidden reliability and safety risks.
- Always coordinate changes with the protection engineering group and follow change management policies.
