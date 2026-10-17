"""Explicit local execution of measured Pi 5 motion plans; never runs on import."""

import importlib
import json
import sys
import time
from pathlib import Path
from threading import Event
from uuid import uuid4

from .models import LotTask
from .pi5_hardware import inspect_hardware, sdk_search_paths, transfer_preview
from .telemetry import utc_now


class HiwonderPi5Backend:
    def __init__(self, profile: dict):
        # Reuse the vendor image's SDK, not an unrelated PyPI package.
        for directory in reversed(sdk_search_paths(profile)):
            if directory not in sys.path:
                sys.path.insert(0, directory)
        mecanum = importlib.import_module("common.mecanum")
        board_module = importlib.import_module("common.ros_robot_controller_sdk")
        self.chassis = mecanum.MecanumChassis()
        self.board = board_module.Board()

    def drive(self, step: dict) -> None:
        self.chassis.set_velocity(step["speed_mm_s"], step["direction_deg"], 0)

    def servo(self, step: dict) -> None:
        self.board.pwm_servo_set_position(step["duration_s"], step["positions"])

    def stop(self) -> None:
        self.chassis.set_velocity(0, 0, 0)


class Pi5TransferRunner:
    def __init__(self, profile: dict, log_directory: Path,
                 backend_factory=HiwonderPi5Backend, inspector=inspect_hardware):
        self.profile = profile
        self.log_directory = log_directory
        self.backend_factory = backend_factory
        self.inspector = inspector
        self.cancelled = Event()

    def cancel(self) -> None:
        self.cancelled.set()

    def execute(self, task: LotTask, execute: bool = False) -> dict:
        preview = transfer_preview(task, self.profile)
        if not execute:
            return preview
        if preview["issues"]:
            raise ValueError("Transfer is not calibrated: " + "; ".join(preview["issues"]))
        hardware = self.inspector(self.profile)
        if not all(hardware.get(key) for key in (
            "model_matches", "memory_consistent_with_4gb", "python_supported", "vendor_modules_found"
        )):
            raise ValueError("Pi 5 / 4 GB runtime and vendor SDK must pass robot-check first")
        if self.cancelled.is_set():
            raise RuntimeError("Transfer was cancelled before execution")
        # Only one local process may execute a transfer on this robot at a time.
        import fcntl

        self.log_directory.mkdir(parents=True, exist_ok=True)
        lock_path = Path("/tmp/masterpi-pi5-wafer-motion.lock")
        with lock_path.open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("Another local transfer is already running") from exc
            result = {
                "trial_id": str(uuid4()), "target": self.profile["profile_id"],
                "lot_id": task.lot_id, "destination": task.destination,
                "calibration_id": preview["calibration_id"], "started_utc": utc_now(),
                "outcome": "not_started", "hardware_commands_sent": False,
                "physical_success_observed": None, "steps": [],
            }
            started = time.monotonic()
            backend = None
            try:
                backend = self.backend_factory(self.profile)
                result["hardware_commands_sent"] = True
                backend.stop()
                for step in preview["steps"]:
                    if self.cancelled.is_set():
                        raise InterruptedError("Operator cancelled transfer")
                    if time.monotonic() - started + step["duration_s"] > self.profile["limits"]["max_transfer_seconds"]:
                        raise TimeoutError("Transfer duration limit reached")
                    result["steps"].append({"name": step.get("name"), "phase": step["phase"], "started_utc": utc_now()})
                    if step["kind"] == "drive":
                        backend.drive(step)
                    else:
                        backend.stop()
                        backend.servo(step)
                    remaining = self.profile["limits"]["max_transfer_seconds"] - (time.monotonic() - started)
                    if remaining <= 0:
                        raise TimeoutError("Transfer duration limit reached")
                    if self.cancelled.wait(min(step["duration_s"], remaining)):
                        raise InterruptedError("Operator cancelled transfer")
                    backend.stop()
                    if step["duration_s"] > remaining:
                        raise TimeoutError("Transfer duration limit reached")
                    result["steps"][-1]["completed_utc"] = utc_now()
                # Command completion cannot prove that an object was actually delivered.
                result["outcome"] = "executed_unverified"
            except Exception as exc:
                result["outcome"] = "cancelled" if isinstance(exc, InterruptedError) else "failed"
                result["error"] = str(exc)
                raise
            finally:
                if backend is not None:
                    try:
                        backend.stop()
                    except Exception as exc:
                        result["stop_error"] = str(exc)
                        result["outcome"] = "stop_failed"
                result["elapsed_seconds"] = time.monotonic() - started
                result["finished_utc"] = utc_now()
                path = self.log_directory / f"physical-{result['trial_id']}.json"
                path.write_text(json.dumps(result, indent=2) + "\n")
                result["log_file"] = str(path)
            if result["outcome"] == "stop_failed":
                raise RuntimeError("Wheel stop command failed; inspect the physical robot and its trial log")
            return result
