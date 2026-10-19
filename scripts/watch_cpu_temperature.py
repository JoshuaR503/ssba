#!/usr/bin/env python3
"""Read-only Pi CPU monitor. No dependencies, services, or motor commands.

Run on Pi: python3 watch_cpu_temperature.py
Ctrl+C stops. Alerts appear only in this terminal; BEL sound depends on settings.
Thresholds below are project early warnings, not hardware safety limits.
"""
from collections import deque
from datetime import datetime
from pathlib import Path
import sys
import time

SENSOR = Path('/sys/class/thermal/thermal_zone0/temp')


def classify(temp, rate):
    """Return a project early-warning label from Celsius and Celsius/minute."""
    if temp >= 80:
        return 'HOT: thermal throttling range; pause heavy work and check cooling'
    if temp >= 75:
        return 'HIGH: approaching thermal throttling range'
    if temp >= 65:
        return 'WARM: check cooling and CPU workload'
    if rate is not None and rate >= 3:
        return 'RISING FAST: at least 3 C/min over the last minute'
    return 'OK'


def main():
    """Read the CPU sensor every five seconds; print a rolling one-minute trend.

    Return 1 on sensor error or 0 on interruption. This does not measure servo,
    battery or wiring temperatures and does not control cooling or movement.
    """
    history = deque()
    previous = 'OK'
    last_alert = float('-inf')
    print('CPU only | every 5s | trend after 60s | Ctrl+C stops', flush=True)
    try:
        while True:
            now = time.monotonic()
            try:
                temp = int(SENSOR.read_text().strip()) / 1000
            except (OSError, ValueError) as exc:
                print(f'ERROR: cannot read CPU sensor: {exc}', file=sys.stderr, flush=True)
                return 1
            history.append((now, temp))
            while len(history) > 1 and now - history[1][0] >= 60:
                history.popleft()
            elapsed = now - history[0][0]
            rate = (temp - history[0][1]) * 60 / elapsed if elapsed >= 60 else None
            status = classify(temp, rate)
            trend = 'collecting trend' if rate is None else f'{rate:+.1f} C/min'
            print(f'{datetime.now().astimezone():%H:%M:%S} | {temp:.1f} C | {trend} | {status}', flush=True)
            if status != 'OK' and (status != previous or now - last_alert >= 60):
                print('\aALERT: ' + status, flush=True)
                last_alert = now
            previous = status
            time.sleep(5)
    except KeyboardInterrupt:
        print('\nMonitor stopped.', flush=True)
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
