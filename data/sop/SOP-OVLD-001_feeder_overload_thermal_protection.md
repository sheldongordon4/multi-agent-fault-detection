ID: SOP-OVLD-001
TITLE: Feeder Overload and Thermal Protection
SECTION: 3.1 Overload Trip Criteria
URL: https://internal.example/sops/feeder_overload_thermal_protection

This SOP describes how to identify and respond to overload conditions on distribution feeders
where thermal protection has operated or is at risk of operating.

Conditions:
- Feeder current trending above 80% of the continuous thermal rating.
- Sustained current at or above 100% of the feeder rating for several seconds.
- Historical or real-time SCADA traces showing gradual heating rather than instantaneous faults.

Trip Criteria:
- Normal operating guideline: keep continuous load at or below 80% of rated current.
- Overload alarm: if current remains between 90% and 100% of rating for more than 60 seconds.
- Overload trip: if current remains at or above 100% of rating for 4–6 seconds,
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
   trends for a defined observation period (for example, 15–30 minutes).
6. If overload conditions re-occur, escalate to planning or protection engineering to review
   longer-term load balancing, reconductoring, or equipment upgrades.

Notes:
- Repeated overload trips on the same feeder may indicate a need for system reconfiguration
  or updated coordination studies.
- Always follow local safety rules and lockout/tagout procedures before field inspections
  or equipment handling.
