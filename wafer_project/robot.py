"""Mock API boundary; measured physical execution lives separately in pi5_driver."""

from typing import Protocol
from uuid import uuid4

from .models import LotTask
from .telemetry import utc_now


class RobotDriver(Protocol):
    def transfer(self, task: LotTask) -> dict: ...


class MockRobot:
    def transfer(self, task: LotTask) -> dict:
        # No motors, servos, GPIO, camera, or manufacturer SDK are accessed.
        return {
            "timestamp_utc": utc_now(),
            "trial_id": str(uuid4()),
            "lot_id": task.lot_id,
            "destination": task.destination,
            "controller": "mock",
            "outcome": "simulated",
            "message": "Command recorded only; no physical transfer was attempted",
        }
