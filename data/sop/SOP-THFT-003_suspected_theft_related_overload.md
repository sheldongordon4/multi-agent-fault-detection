ID: SOP-THFT-003
TITLE: Suspected Theft-Related Overload on Distribution Feeders
SECTION: 5.4 Non-Technical Loss and Overload Investigation
URL: https://internal.example/sops/suspected_theft_related_overload

This SOP describes how to investigate overload conditions that may be associated with
unauthorized connections, energy theft, or other non-technical losses on distribution feeders.

## Fault Signature Identification

This section provides the symmetrical component and electrical feature signatures that
characterize theft-related and non-technical-loss overload conditions. These conditions
share the same electrical profile as general feeder overload but exhibit specific temporal
and demand-accounting patterns that distinguish them from legitimate load growth.

The electrical signature of a theft-related or non-technical-loss overload is identical to a
general feeder overload in its symmetrical component profile:

| Feature | Range | Notes |
|---|---|---|
| Peak phase current (maxIa) | 0.90 - 1.20+ pu of feeder rating | Rises gradually and may be sustained at levels above those justified by billed demand. |
| Minimum phase voltage (minVa_pu) | 0.86 - 0.97 pu | Modest sag, suppressed by sustained high loading but within an acceptable operational range. A sag below 0.70 pu indicates a different fault condition and this SOP does not apply. |
| Zero-sequence current ratio (I0/I1) | < 0.02 | Unauthorized connections and theft-related overloads are balanced loading conditions; the absence of zero-sequence current confirms no ground fault involvement. A value above 0.10 suggests a concurrent fault condition requiring a different SOP. |
| Negative-sequence current ratio (I2/I1) | < 0.02 | Theft-related loading is typically distributed across phases without deliberate unbalancing. A value above 0.10 suggests phase unbalance inconsistent with a pure overload condition. |

Theft-related overload signature summary:

| Feature | Value |
|---|---|
| maxIa | 0.90 - 1.20+ pu (elevated current not supported by billed demand) |
| minVa | 0.86 - 0.97 pu (modest sustained voltage sag under heavy load) |
| I0/I1 | < 0.02 (near zero — balanced loading, no ground path) |
| I2/I1 | < 0.02 (near zero — balanced loading, no phase unbalance) |
| Temporal pattern | Persistent elevated loading that does not align with billing records, seasonal patterns, or known customer growth. Load may spike at specific periods correlated with unauthorized activity (for example, nighttime, holidays, or weekends in commercial or agricultural areas). |

### Key Differentiator from Legitimate Overload
A legitimate overload driven by load growth shows a corresponding increase in billed demand. A
theft-related overload shows elevated feeder loading without a proportional increase in metered
or billed demand. The electrical signatures are identical; the diagnostic is the
demand-accounting mismatch rather than the electrical feature profile.

### Distinguishing Theft-Related Overload from Short-Circuit Faults
Short-circuit faults produce instantaneous current surges above 3 pu with deep voltage sag
below 0.30 pu. Theft-related overloads produce sustained moderate current elevation with
modest voltage sag and near-zero sequence ratios. The temporal pattern (gradual, persistent,
potentially time-correlated) distinguishes overload from the abrupt onset of a fault event.

## Conditions
- Persistent high loading on a feeder without corresponding increases in billed demand.
- Overloads occurring primarily during specific periods that do not align with known customer behavior.
- SCADA data showing irregular load patterns, sudden step changes, or high load in areas with a history of theft.

## Trip Criteria
- Overload alarms or trips on feeders serving regions with known theft issues.
- Repeated overload events that do not correlate with legitimate customer growth or weather patterns.

## Operator Actions
1. Confirm the overload condition using SCADA trends and compare with historical loading.
2. Cross-check feeder loading with billing and metering data to identify discrepancies.
3. Notify the non-technical loss or revenue protection team to initiate a field investigation.
4. Where safe and permitted, reconfigure load or adjust switching to reduce stress on the affected feeder while investigations proceed.
5. Record all observations, including times, loading patterns, and any field reports of unauthorized connections.
6. After corrective actions in the field, monitor the feeder loading to confirm that overload conditions have been resolved.

## Notes
- Field investigations for theft must follow legal, regulatory, and safety requirements.
- Coordination with revenue protection, legal, and law enforcement teams may be required.
