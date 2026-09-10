"""
MAFD Kafka topics (see docs/System_Architecture.md §5).

    raw.signals        3-phase waveform FRAMES, one cycle per bus per message
                       (app/ml/waveform.py) — not scalar SCADA readings
                       produced by: waveform producer / (later) the SCADA tap
                       consumed by: extraction svc (-> feeder.events) AND
                                    streaming svc (per-cycle RMS -> live chart),
                                    two independent groups, both at-most-once

    feeder.events      per-bus event rows (one row = one feeder snapshot)
                       produced by: extraction svc, or scripts/produce_events.py
                                    replaying pre-reduced rows offline
                       consumed by: detection svc

    anomalies.detected one event per fault (verdict + most-disturbed buses)
                       produced by: detection svc (event IsolationForest)
                       consumed by: coordinator svc

    faulttickets       one validated FaultTicket per incident
                       produced by: coordinator svc
                       consumed by: notification svc, persistence svc (separate groups)

Partitioned by feeder / incident_id so per-feeder ordering holds.
"""

RAW_SIGNALS = "raw.signals"
FEEDER_EVENTS = "feeder.events"
ANOMALIES_DETECTED = "anomalies.detected"
FAULT_TICKETS = "faulttickets"
