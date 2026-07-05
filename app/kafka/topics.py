"""
MAFD Kafka topics (see docs/System_Architecture.md §5).

    raw.signals        per-bus SCADA time-series readings (firehose)
                       produced by: signal producer / simulation
                       consumed by: streaming svc (live UI chart)

    feeder.events      pre-reduced per-bus event rows (the output of feature
                       extraction; one row = one feeder snapshot)
                       produced by: event producer / feature extractor
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
