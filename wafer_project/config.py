"""Load settings without opening connections or accessing robot hardware."""

import json
import math
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    robot_url: str
    request_timeout_seconds: float
    temperature_interval_seconds: float
    temperature_warning_c: float
    log_directory: Path
    stations: dict[str, bool]
    hardware_profile: Path | None = None


def positive_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be finite and greater than zero")
    return result


def load_settings(path: Path = PROJECT_ROOT / "config.json") -> Settings:
    path = path.resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Configuration must be a JSON object")
    url = data.get("robot_url")
    if not isinstance(url, str):
        raise ValueError("robot_url must be a URL string")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("robot_url must be an HTTP or HTTPS URL")
    if parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValueError("robot_url must contain only a scheme, host and optional port")
    stations = data.get("stations")
    if not isinstance(stations, dict) or not stations or any(
        not isinstance(name, str) or not name.strip() or type(available) is not bool
        for name, available in stations.items()
    ):
        raise ValueError("stations must map station names to true or false")
    log_directory = data.get("log_directory")
    if not isinstance(log_directory, str) or not log_directory.strip():
        raise ValueError("log_directory must be a nonempty path")
    warning = positive_number(data.get("temperature_warning_c"), "temperature_warning_c")
    hardware_profile = data.get("hardware_profile", "hardware/pi5_4gb.json")
    if not isinstance(hardware_profile, str) or not hardware_profile.strip():
        raise ValueError("hardware_profile must be a nonempty path")
    if warning > 150:
        raise ValueError("temperature_warning_c must be at most 150")
    return Settings(
        robot_url=url.rstrip("/"),
        request_timeout_seconds=positive_number(
            data.get("request_timeout_seconds"), "request_timeout_seconds"
        ),
        temperature_interval_seconds=positive_number(
            data.get("temperature_interval_seconds"), "temperature_interval_seconds"
        ),
        temperature_warning_c=warning,
        log_directory=path.parent / log_directory,
        stations=stations,
        hardware_profile=path.parent / hardware_profile,
    )
