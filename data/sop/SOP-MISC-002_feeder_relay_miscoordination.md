ID: SOP-MISC-002
TITLE: Feeder Relay Miscoordination Investigation
SECTION: 4.2 Relay Coordination and Nuisance Tripping
URL: https://internal.example/sops/feeder_relay_miscoordination

This SOP describes how to investigate and respond to suspected protection relay miscoordination
on distribution feeders and associated buses.

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
