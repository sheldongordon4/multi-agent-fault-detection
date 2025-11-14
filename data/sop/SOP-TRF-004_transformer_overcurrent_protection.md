ID: SOP-TRF-004
TITLE: Transformer Overcurrent and Thermal Protection
SECTION: 6.1 Transformer Protection Guidelines
URL: https://internal.example/sops/transformer_overcurrent_protection

This SOP describes how to evaluate and respond to overcurrent and thermal protection
operations on power transformers.

Conditions:
- Transformer load approaching or exceeding nameplate MVA rating.
- SCADA trends showing elevated winding or oil temperature.
- Overcurrent relay elements operating during heavy load or fault events.

Trip Criteria:
- Sustained load at or above 100% of transformer rating for longer than the allowable
  thermal duration.
- Operation of transformer overcurrent or differential elements in accordance with the
  protection settings and manufacturer guidelines.

Operator Actions:
1. Verify transformer loading, temperature, and protection indications using SCADA and local readings.
2. Distinguish between load-related overcurrent and genuine internal faults by reviewing
   differential and gas protection indications where available.
3. If an internal fault is suspected, keep the transformer out of service and notify
   maintenance and engineering immediately.
4. For load-related overloads, reconfigure the system to reduce transformer loading, such
   as transferring load to parallel units where available.
5. After corrective actions, monitor transformer loading and temperature for a defined period
   to ensure conditions remain within acceptable limits.

Notes:
- Operating transformers above rated capacity for extended periods can significantly reduce
  equipment life.
- Always follow manufacturer recommendations and internal engineering standards when
  restoring transformers to service after protection operations.
