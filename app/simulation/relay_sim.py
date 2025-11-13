from datetime import datetime, timedelta
from typing import Dict, List

import random


def generate_relay_events(
    num_events: int = 5,
    start_time: datetime | None = None,
    interval_seconds: int = 5,
) -> List[Dict]:
    """
    Generate a simple set of relay protection events.

    27: undervoltage
    59: overvoltage
    50: instantaneous overcurrent
    51: time overcurrent
    """
    if start_time is None:
        start_time = datetime.utcnow()

    events: List[Dict] = []
    for i in range(num_events):
        ts = start_time + timedelta(seconds=i * interval_seconds)

        event = {
            "timestamp": ts.isoformat(),
            "feeder_id": "FEEDER-01",
            "27": random.choice([0, 1]),
            "59": random.choice([0, 1]),
            "50": random.choice([0, 1]),
            "51": random.choice([0, 1]),
        }
        events.append(event)

    return events


if __name__ == "__main__":
    relay_events = generate_relay_events(num_events=3)
    for evt in relay_events:
        print(evt)
