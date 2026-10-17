"""Append timestamped observations; missing temperatures remain blank in CSV."""

import csv
from pathlib import Path
from threading import Lock

TEMPERATURE_FIELDS = (
    "timestamp_utc", "device", "temperature_c", "status", "source", "message"
)
TRANSFER_FIELDS = (
    "timestamp_utc", "trial_id", "lot_id", "destination", "controller", "outcome", "message"
)


class CsvLog:
    def __init__(self, path: Path, fields: tuple[str, ...]):
        self.path = path
        self.fields = fields
        self._lock = Lock()

    def append(self, row: dict) -> None:
        # Supports concurrent Flask requests within one server process.
        # Use one process per log file; this is not a cross-process lock.
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            has_data = self.path.exists() and self.path.stat().st_size > 0
            with self.path.open("a", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=self.fields)
                if not has_data:
                    writer.writeheader()
                writer.writerow(row)
