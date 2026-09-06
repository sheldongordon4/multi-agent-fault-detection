ID: SOP-TRF-004
TITLE: Transformer Overcurrent and Thermal Protection
SECTION: 6.1 Transformer Protection Guidelines
URL: https://internal.example/sops/transformer_overcurrent_protection

This SOP describes how to evaluate and respond to overcurrent and thermal protection
operations on power transformers.

## Fault Signature Identification

This section provides the symmetrical component and electrical feature signatures used to
identify balanced three-phase and severe fault conditions before applying this SOP. All
feature values are expressed in per-unit or as dimensionless ratios unless otherwise stated.

### Zero-Sequence to Positive-Sequence Current Ratio (I0/I1)

| Range | Interpretation |
|---|---|
| < 0.05 (near 0.0) | No ground return current. Characteristic of balanced three-phase faults (LLL) where all three phases fault symmetrically with no ground path involvement. |
| 0.40 - 0.70 | Significant ground current. Characteristic of three-phase-to-ground (LLLG) faults where the fault path includes ground alongside all three phases. |
| > 0.70 | Very high ground current. Indicative of a low-impedance LLLG or severe ground fault event. |

### Negative-Sequence to Positive-Sequence Current Ratio (I2/I1)

| Range | Interpretation |
|---|---|
| < 0.05 (near 0.0) | Balanced condition. Consistent with LLL, LLLG, or sustained load-related overcurrent where all three phases carry similar current magnitudes. Near-zero I2/I1 combined with near-zero I0/I1 and deep voltage sag is the defining signature of a balanced three-phase fault. |

### Minimum Per-Unit Phase Voltage (minVa_pu)

| Range | Interpretation |
|---|---|
| < 0.10 pu | Severe voltage collapse across all phases. Consistent with bolted three-phase short-circuit faults (LLL or LLLG) where the fault impedance is very low. |
| 0.10 - 0.20 pu | Deep voltage sag consistent with high-severity three-phase fault events. |
| > 0.85 pu, with elevated current | Consistent with transformer thermal loading or sustained overcurrent rather than a short-circuit fault event. |

### Peak Phase Current Magnitude (maxIa)

| Range | Interpretation |
|---|---|
| 0.9 - 1.3 pu | Consistent with thermal overload where load exceeds the nameplate rating but no fault condition exists. |
| > 5 pu | High current surge. Consistent with a short-circuit fault condition. |
| > 7 pu | Very high current. Consistent with a bolted or low-impedance three-phase fault event requiring immediate protective device operation. |

### Fault Type Signatures

**LLL (Three-Phase Balanced Fault, no ground)**
- minVa < 0.08 pu across all phases; maxIa 5-10 pu; I0/I1 < 0.005 (near zero — no ground return); I2/I1 < 0.005 (near zero — balanced symmetric fault).
- Interpretation: Near-zero values for both I0/I1 and I2/I1 simultaneously with a deep voltage collapse and high current surge is the defining signature of a balanced LLL fault. The absence of both zero-sequence and negative-sequence current confirms no ground path and no phase unbalance. This event carries very high fault current and requires immediate transformer protection review. Differential and overcurrent element operation is expected and should be verified against protection settings.

**LLLG (Three-Phase-to-Ground Fault)**
- minVa < 0.05 pu; maxIa 6-10 pu; I0/I1 0.45-0.70 (elevated zero-sequence due to ground path); I2/I1 < 0.01 (near zero — all three phases affected equally, no unbalance).
- Interpretation: The combination of very high current, complete voltage collapse, and elevated I0/I1 with near-zero I2/I1 is characteristic of LLLG. The ground path drives the I0/I1 ratio above 0.5, while near-zero I2/I1 confirms balanced three-phase involvement. This is the most severe fault class: all three phases are faulted to ground simultaneously. Transformer differential protection should operate. Post-event thermal and insulation inspection is required before restoration.

**OPEN_3PH (Three-Phase Open Conductor)**
- minVa < 0.10 pu (complete de-energization); maxIa near 0 pu (no current path); I0/I1 0.30-0.55; I2/I1 0.30-0.50.
- Interpretation: Complete voltage loss with near-zero current distinguishes OPEN_3PH from short-circuit faults. Both sequence ratios are elevated due to the asymmetry of complete phase loss, but the defining feature is the absence of significant current surge despite voltage collapse. Transformer protection may operate due to voltage-related elements. Inspection for conductor failure, switch operation, or upstream device operation is required.

**Thermal Overload (load-related overcurrent)**
- minVa 0.85-0.96 pu (modest voltage sag under heavy load); maxIa 0.90-1.30 pu above normal operating level; I0/I1 < 0.01; I2/I1 < 0.01.
- Interpretation: Near-zero sequence ratios with only a modest voltage sag and elevated current are the defining features of a load-related thermal overload, distinguishing it from all short-circuit fault classes. A gradual current increase over time rather than an instantaneous surge confirms overload rather than fault.

## Conditions
- Transformer load approaching or exceeding nameplate MVA rating.
- SCADA trends showing elevated winding or oil temperature.
- Overcurrent relay elements operating during heavy load or fault events.

## Trip Criteria
- Sustained load at or above 100% of transformer rating for longer than the allowable thermal duration.
- Operation of transformer overcurrent or differential elements in accordance with the protection settings and manufacturer guidelines.

## Operator Actions
1. Verify transformer loading, temperature, and protection indications using SCADA and local readings.
2. Distinguish between load-related overcurrent and genuine internal faults by reviewing differential and gas protection indications where available.
3. If an internal fault is suspected, keep the transformer out of service and notify maintenance and engineering immediately.
4. For load-related overloads, reconfigure the system to reduce transformer loading, such as transferring load to parallel units where available.
5. After corrective actions, monitor transformer loading and temperature for a defined period to ensure conditions remain within acceptable limits.

## Notes
- Operating transformers above rated capacity for extended periods can significantly reduce equipment life.
- Always follow manufacturer recommendations and internal engineering standards when restoring transformers to service after protection operations.
