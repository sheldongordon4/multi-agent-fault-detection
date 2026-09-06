ID: SOP-OVLD-001
TITLE: Feeder Overload and Thermal Protection
SECTION: 3.1 Overload Trip Criteria
URL: https://internal.example/sops/feeder_overload_thermal_protection

This SOP describes how to identify and respond to overload conditions on distribution feeders
where thermal protection has operated or is at risk of operating.

SECTION 2 — Fault Signature Identification

This section provides the symmetrical component and electrical feature signatures that
distinguish overload conditions from short-circuit fault events. All feature values are
expressed in per-unit or as dimensionless ratios unless otherwise stated.

The definitive electrical signature of a feeder overload condition is the simultaneous
presence of the following four characteristics:

1. Elevated peak phase current (maxIa): Current above normal operating level, typically
   between 0.90 pu and 1.30 pu of feeder rating. Unlike short-circuit faults, overload
   current rises gradually rather than instantaneously. Current above 1.20 pu of rating
   approaching or exceeding the thermal limit triggers this SOP.

2. Modest voltage sag (minVa_pu): Voltage remains between 0.85 pu and 0.97 pu. The voltage
   sag under overload is gradual and modest because the feeder impedance produces a proportional
   voltage drop under heavy load. A voltage sag deeper than 0.70 pu is inconsistent with
   pure overload and suggests a concurrent short-circuit fault.

3. Near-zero zero-sequence current ratio (I0/I1 < 0.02): Overload conditions involve balanced
   or near-balanced loading across all three phases. Zero-sequence current is absent or
   negligible because no ground return path exists. A value above 0.15 indicates ground
   involvement inconsistent with a pure overload condition.

4. Near-zero negative-sequence current ratio (I2/I1 < 0.02): Overload is a balanced load
   condition. Negative-sequence current is absent because load is distributed approximately
   equally across all three phases. A value above 0.15 indicates phase unbalance inconsistent
   with a pure overload condition.

Overload signature summary:
  maxIa: 0.90 to 1.30 pu (elevated, gradual rise over time)
  minVa: 0.85 to 0.97 pu (modest, voltage proportional to current times feeder impedance)
  I0/I1: < 0.02 (near zero — no ground return)
  I2/I1: < 0.02 (near zero — balanced three-phase loading)
  Temporal pattern: Gradual current rise over seconds to minutes, not instantaneous surge

Distinguishing overload from short-circuit fault:
- Short-circuit faults produce instantaneous current surges (typically above 3 pu) with
  deep voltage sag (typically below 0.30 pu) and may produce elevated sequence ratios
  depending on fault type.
- Overload produces a gradual current increase, modest voltage sag, and near-zero sequence
  ratios. SCADA traces showing a gradual heating pattern are diagnostic of overload.
- If I0/I1 or I2/I1 exceeds 0.15 while current is elevated, a concurrent fault condition
  should be investigated before treating the event as a pure overload.

Conditions:
- Feeder current trending above 80% of the continuous thermal rating.
- Sustained current at or above 100% of the feeder rating for several seconds.
- Historical or real-time SCADA traces showing gradual heating rather than instantaneous faults.

Trip Criteria:
- Normal operating guideline: keep continuous load at or below 80% of rated current.
- Overload alarm: if current remains between 90% and 100% of rating for more than 60 seconds.
- Overload trip: if current remains at or above 100% of rating for 4 to 6 seconds,
  or follows the defined time-current curve in the protection settings.
- Instantaneous or definite-time elements may trip faster above 120% of rated current.

Operator Actions:
1. Verify from SCADA or local measurements that the trip was caused by sustained overload,
   not a short-circuit or protection miscoordination.
2. Review feeder loading on all downstream circuits and identify any new or shifted loads.
3. Where possible, transfer non-critical load to alternate feeders to reduce current on the
   affected feeder.
4. Confirm that relay and breaker protection settings match the latest approved coordination
   study and equipment nameplate ratings.
5. After load has been reduced, re-energize the feeder and monitor current and temperature
   trends for a defined observation period (for example, 15 to 30 minutes).
6. If overload conditions re-occur, escalate to planning or protection engineering to review
   longer-term load balancing, reconductoring, or equipment upgrades.

Notes:
- Repeated overload trips on the same feeder may indicate a need for system reconfiguration
  or updated coordination studies.
- Always follow local safety rules and lockout/tagout procedures before field inspections
  or equipment handling.
