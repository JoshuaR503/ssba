"""Laptop HTTP client with timeouts and no automatic command retries."""

import math

import requests

from .config import Settings
from .models import LotTask
from .telemetry import TemperatureReading


class RobotClient:
    def __init__(self, settings: Settings):
        self.base_url = settings.robot_url
        self.timeout = settings.request_timeout_seconds

    def temperature(self) -> TemperatureReading:
        response = requests.get(f"{self.base_url}/temperature", timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Robot returned an invalid temperature response")
        fields = ("timestamp_utc", "device", "status", "source", "message")
        if any(not isinstance(data.get(field), str) for field in fields):
            raise ValueError("Robot returned invalid temperature metadata")
        value = data.get("temperature_c")
        status = data["status"]
        if status not in {"ok", "warning", "unavailable"}:
            raise ValueError("Robot returned an unknown temperature status")
        if status == "unavailable":
            if value is not None:
                raise ValueError("Unavailable temperature must be null")
        elif (
            isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not 0 <= value <= 150
        ):
            raise ValueError("Robot returned an invalid temperature value")
        return TemperatureReading(**{field: data[field] for field in fields}, temperature_c=value)

    def transfer(self, task: LotTask) -> dict:
        # Calling this explicitly sends a command. Nothing calls it during setup.
        response = requests.post(
            f"{self.base_url}/transfers",
            json={"lot_id": task.lot_id, "destination": task.destination},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()
