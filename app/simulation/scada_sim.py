from datetime import datetime, timedelta
from typing import Dict, List

import math
import random


def generate_scada_stream(
    num_points: int = 10,
    start_time: datetime | None = None,
    interval_seconds: int = 1,
) -> List[Dict]:
    """
    Generate a simple synthetic SCADA stream.

    This is just a placeholder for the MVP:
    - Voltage fluctuates around 13.8 kV.
    - Current fluctuates around 200 A.
    - Frequency around 60 Hz.
    """
    if start_time is None:
        start_time = datetime.utcnow()

    data: List[Dict] = []
    for i in range(num_points):
        ts = start_time + timedelta(seconds=i * interval_seconds)

        # Normal-ish sinusoidal variation + noise
        voltage = 13.8 + 0.2 * math.sin(i / 3) + random.uniform(-0.05, 0.05)
        current = 200 + 10 * math.sin(i / 5) + random.uniform(-2, 2)
        frequency = 60 + 0.05 * math.sin(i / 10) + random.uniform(-0.01, 0.01)

        data.append(
            {
                "timestamp": ts.isoformat(),
                "bus_id": "BUS-01",
                "voltage_kv": round(voltage, 3),
                "current_a": round(current, 2),
                "frequency_hz": round(frequency, 3),
            }
        )

    return data


if __name__ == "__main__":
    stream = generate_scada_stream(num_points=5)
    for point in stream:
        print(point)
