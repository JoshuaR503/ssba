"""Seeded synthetic inputs, generated once and reused across controller/model trials."""

import math
import random
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SimulatedLot:
    seed: int
    lot_id: str
    destination: str
    arrival_seconds: float
    transfer_seconds: float
    station_process_seconds: float
    failure_draw: float
    source: str = "synthetic"

    def to_dict(self) -> dict:
        return asdict(self)


def generate_workload(seed: int, lots: int, config: dict) -> list[SimulatedLot]:
    if lots <= 0:
        raise ValueError("lots must be greater than zero")
    rng = random.Random(seed)
    settings = config["workload"]
    arrival = 0.0
    result = []
    for index in range(lots):
        if index:
            arrival += rng.uniform(*settings["arrival_gap_seconds"])
        result.append(SimulatedLot(
            seed=seed,
            lot_id=f"W{index + 1:03d}",
            destination=rng.choices(config["stations"], settings["destination_weights"])[0],
            arrival_seconds=arrival,
            transfer_seconds=rng.uniform(*settings["transfer_seconds"]),
            station_process_seconds=rng.uniform(*settings["station_process_seconds"]),
            failure_draw=rng.random(),
        ))
    return result


def validate_workload(workload: list[SimulatedLot], stations: list[str]) -> None:
    if not workload or len({lot.lot_id for lot in workload}) != len(workload):
        raise ValueError("Workload must be nonempty with unique lot IDs")
    if len({lot.seed for lot in workload}) != 1:
        raise ValueError("A trial must contain exactly one workload seed")
    for lot in workload:
        if not lot.lot_id.strip() or lot.destination not in stations:
            raise ValueError("Workload contains an invalid lot or destination")
        for name in ("arrival_seconds", "transfer_seconds", "station_process_seconds", "failure_draw"):
            value = getattr(lot, name)
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if lot.arrival_seconds < 0 or lot.transfer_seconds <= 0 or lot.station_process_seconds <= 0:
            raise ValueError("Arrival must be nonnegative and service durations positive")
        if not 0 <= lot.failure_draw <= 1:
            raise ValueError("failure_draw must be between zero and one")
