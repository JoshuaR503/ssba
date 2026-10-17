"""Read the Raspberry Pi CPU/SoC temperature through Linux sysfs.

No drivers, subprocesses, simulated readings, or background threads are used.
"""

import math
import socket
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class TemperatureReading:
    timestamp_utc: str
    device: str
    temperature_c: float | None
    status: str
    source: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


def unavailable_reading(device: str, source: str, message: str) -> TemperatureReading:
    return TemperatureReading(utc_now(), device, None, "unavailable", source, message)


class PiCpuTemperatureReader:
    def __init__(
        self,
        warning_c: float = 75,
        temperature_path: Path = Path("/sys/class/thermal/thermal_zone0/temp"),
        model_path: Path = Path("/proc/device-tree/model"),
    ):
        if not math.isfinite(warning_c) or not 0 < warning_c <= 150:
            raise ValueError("warning_c must be finite and between 0 and 150")
        self.warning_c = warning_c
        self.temperature_path = temperature_path
        self.model_path = model_path

    def read(self) -> TemperatureReading:
        device = socket.gethostname()
        source = "raspberry_pi_sysfs"
        try:
            model = self.model_path.read_text(encoding="utf-8").strip("\x00\n ")
        except (OSError, UnicodeError):
            return unavailable_reading(
                device, source, "Raspberry Pi CPU sensor unavailable on this computer"
            )
        if "Raspberry Pi" not in model:
            return unavailable_reading(device, source, "This computer is not a Raspberry Pi")
        try:
            # Linux exposes this reading in thousandths of a degree Celsius.
            temperature_c = int(self.temperature_path.read_text().strip()) / 1000
            if not 0 <= temperature_c <= 150:
                raise ValueError("Sensor value outside the supported range")
        except (OSError, ValueError, UnicodeError) as exc:
            return unavailable_reading(device, source, f"CPU sensor could not be read: {exc}")
        warning = temperature_c >= self.warning_c
        return TemperatureReading(
            utc_now(), device, temperature_c,
            "warning" if warning else "ok", source,
            "Above configured advisory threshold" if warning else "CPU sensor read successfully",
        )
