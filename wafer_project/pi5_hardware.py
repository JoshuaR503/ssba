"""Pi 5 identity, vendor-module discovery and calibration previews, without motion."""

import json
import math
import platform
import sys
from importlib.machinery import PathFinder
from pathlib import Path

from .config import PROJECT_ROOT
from .models import LotTask
from .telemetry import PiCpuTemperatureReader

DEFAULT_PROFILE = PROJECT_ROOT / "hardware/pi5_4gb.json"


def load_profile(path: Path = DEFAULT_PROFILE) -> dict:
    path = path.resolve()
    profile = json.loads(path.read_text())
    if not isinstance(profile, dict):
        raise ValueError("Hardware profile must be a JSON object")
    if profile.get("profile_id") != "masterpi_pi5_4gb" or profile.get("ram_gb") != 4:
        raise ValueError("Only the confirmed MasterPi Pi 5 / 4 GB profile is supported")
    if profile.get("expected_model") != "Raspberry Pi 5" or type(profile.get("motion_enabled")) is not bool:
        raise ValueError("Invalid Pi 5 identity or motion setting")
    for name in ("sdk_root", "calibration_file"):
        if not isinstance(profile.get(name), str) or not profile[name].strip():
            raise ValueError(f"{name} must be a nonempty path")
    limits = profile.get("limits", {})
    if not isinstance(limits, dict):
        raise ValueError("Hardware limits must be a JSON object")
    for name in ("max_drive_speed_mm_s", "max_step_seconds", "max_transfer_seconds", "servo_pulse_min", "servo_pulse_max"):
        value = limits.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"Invalid hardware limit: {name}")
    if limits["max_drive_speed_mm_s"] > 100 or limits["max_step_seconds"] > 3:
        raise ValueError("Starter limits require speed at most 100 mm/s and steps at most 3 seconds")
    if not 500 <= limits["servo_pulse_min"] < limits["servo_pulse_max"] <= 2500:
        raise ValueError("Starter servo bounds must lie within 500..2500; calibrate narrower limits on the robot")
    profile["sdk_root"] = str(Path(profile["sdk_root"]).expanduser())
    profile["calibration_file"] = str((path.parent / profile["calibration_file"]).resolve())
    return profile


def sdk_search_paths(profile: dict) -> list[str]:
    root = Path(profile["sdk_root"])
    candidates = [root, root / "masterpi_sdk", root / "masterpi_sdk/common_sdk"]
    return [str(path) for path in candidates if path.is_dir()]


def find_vendor_modules(profile: dict) -> dict:
    # PathFinder discovers files without importing a vendor package or executing its code.
    common = PathFinder.find_spec("common", sdk_search_paths(profile) + sys.path)
    search = list(common.submodule_search_locations or []) if common else []
    result = {}
    for name in ("common.mecanum", "common.ros_robot_controller_sdk"):
        spec = PathFinder.find_spec(name, search) if search else None
        result[name] = spec.origin if spec else None
    return result


def inspect_hardware(profile: dict, model_path: Path = Path("/proc/device-tree/model"),
                     memory_path: Path = Path("/proc/meminfo")) -> dict:
    try:
        model = model_path.read_text().strip("\x00\n ")
    except (OSError, UnicodeError):
        model = None
    try:
        memory = next(line.split()[1] for line in memory_path.read_text().splitlines() if line.startswith("MemTotal:"))
        memory_gib = int(memory) / 1024**2
    except (OSError, ValueError, StopIteration, UnicodeError):
        memory_gib = None
    modules = find_vendor_modules(profile)
    return {
        "target": profile["profile_id"], "expected_ram_gb": 4,
        "detected_model": model, "os_visible_memory_gib": memory_gib,
        "model_matches": bool(model and model.startswith("Raspberry Pi 5 ")),
        "memory_consistent_with_4gb": memory_gib is not None and 2.5 <= memory_gib <= 4.5,
        "python_version": platform.python_version(), "python_supported": sys.version_info >= (3, 10),
        "machine": platform.machine(), "vendor_modules": modules,
        "vendor_modules_found": all(modules.values()),
        "motion_enabled": profile["motion_enabled"],
        "cpu_temperature": PiCpuTemperatureReader(model_path=model_path).read().to_dict(),
        "hardware_action_executed": False,
    }


def transfer_preview(task: LotTask, profile: dict) -> dict:
    calibration = json.loads(Path(profile["calibration_file"]).read_text())
    if not isinstance(calibration, dict):
        raise ValueError("Calibration must be a JSON object")
    routes = calibration.get("routes")
    if not isinstance(routes, dict) or task.destination not in routes:
        raise ValueError("No calibrated route is defined for this destination")
    route = routes[task.destination]
    steps, issues = [], []
    if calibration.get("calibrated") is not True:
        issues.append("Calibration has not been marked complete")
    identifier = calibration.get("calibration_id")
    if not isinstance(identifier, str) or not identifier.strip():
        issues.append("A calibration_id is required")
    if not profile["motion_enabled"]:
        issues.append("Hardware profile has motion_enabled=false")
    groups = [("pickup", calibration.get("pickup"))]
    if not isinstance(route, dict):
        raise ValueError("Each route must be an object")
    groups += [(name, route.get(name)) for name in ("outbound", "place", "return")]
    total = 0.0
    limits = profile["limits"]
    for phase, group in groups:
        if not isinstance(group, list) or not group:
            issues.append(f"{phase}: at least one calibrated step is required")
            continue
        for index, raw in enumerate(group):
            prefix = f"{phase}[{index}]"
            if not isinstance(raw, dict) or not isinstance(raw.get("kind"), str) or raw.get("kind") not in {"servo", "drive"}:
                issues.append(f"{prefix}: expected a servo or drive step")
                continue
            step = {**raw, "phase": phase}
            steps.append(step)
            duration = raw.get("duration_s")
            if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or not 0 < duration <= limits["max_step_seconds"]:
                issues.append(f"{prefix}: duration_s must be calibrated within the step limit")
            else:
                total += duration
            if raw["kind"] == "drive":
                speed, direction = raw.get("speed_mm_s"), raw.get("direction_deg")
                if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not math.isfinite(speed) or not 0 < speed <= limits["max_drive_speed_mm_s"]:
                    issues.append(f"{prefix}: speed_mm_s must be calibrated within the speed limit")
                if isinstance(direction, bool) or not isinstance(direction, (int, float)) or not math.isfinite(direction) or not 0 <= direction < 360:
                    issues.append(f"{prefix}: direction_deg must be calibrated within 0..359.999")
            else:
                positions = raw.get("positions")
                valid = isinstance(positions, list) and bool(positions)
                ids = []
                if valid:
                    for pair in positions:
                        if not isinstance(pair, list) or len(pair) != 2:
                            valid = False
                            break
                        servo_id, pulse = pair
                        if type(servo_id) is not int or not 1 <= servo_id <= 6 or type(pulse) is not int or not limits["servo_pulse_min"] <= pulse <= limits["servo_pulse_max"]:
                            valid = False
                            break
                        ids.append(servo_id)
                    valid = valid and len(set(ids)) == len(ids)
                if not valid:
                    issues.append(f"{prefix}: positions must be calibrated unique [servo_id, pulse] pairs")
    if total > limits["max_transfer_seconds"]:
        issues.append("Total planned duration exceeds the transfer limit")
    return {
        "target": profile["profile_id"], "lot_id": task.lot_id, "destination": task.destination,
        "calibration_id": identifier, "steps": steps, "planned_seconds": total,
        "ready_for_hardware_check": not issues, "issues": issues, "hardware_action_executed": False,
    }
