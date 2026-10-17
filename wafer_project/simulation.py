"""SimPy experiment engine. Never imports a hardware driver or makes HTTP requests."""

import hashlib
import json
import math
from pathlib import Path

import simpy

from .models import LotTask
from .scheduler import choose_next
from .workload import SimulatedLot, validate_workload

CONTROLLERS = ("onboard_fifo", "external_fifo", "external_adaptive")


def load_simulation_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    validate_simulation_config(config)
    return config


def validate_simulation_config(config: dict) -> None:
    def number(value, name, minimum=0, strictly_positive=False):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name} must be a finite number")
        if value < minimum or (strictly_positive and value == 0):
            raise ValueError(f"{name} is outside its allowed range")

    for field in ("horizon_seconds", "poll_interval_seconds", "temperature_interval_seconds"):
        number(config[field], field, strictly_positive=True)
    number(config["temperature_warning_c"], "temperature_warning_c")
    number(config["failure_probability"], "failure_probability")
    if config["failure_probability"] > 1:
        raise ValueError("failure_probability must be at most one")
    stations = config["stations"]
    if not isinstance(stations, list) or not stations or any(
        not isinstance(station, str) or not station.strip() for station in stations
    ) or len(set(stations)) != len(stations):
        raise ValueError("stations must be a nonempty list of unique names")
    for field in ("arrival_gap_seconds", "transfer_seconds", "station_process_seconds"):
        interval = config["workload"][field]
        if not isinstance(interval, list) or len(interval) != 2:
            raise ValueError(f"{field} must contain minimum and maximum")
        for value in interval:
            number(value, field, strictly_positive=field != "arrival_gap_seconds")
        if interval[0] > interval[1]:
            raise ValueError(f"{field} minimum exceeds maximum")
    weights = config["workload"]["destination_weights"]
    if len(weights) != len(stations):
        raise ValueError("One destination weight is required per station")
    for weight in weights:
        number(weight, "destination weight")
    if sum(weights) <= 0:
        raise ValueError("Destination weights must have a positive sum")
    number(config["laptop_decision_seconds"], "laptop_decision_seconds")
    for field, value in config["network"].items():
        number(value, field)
    if not config["pi_profiles"] or not config["scenarios"]:
        raise ValueError("At least one Pi profile and scenario are required")
    for profile in config["pi_profiles"].values():
        for field in ("onboard_decision_seconds", "command_handling_seconds"):
            number(profile[field], field)
    thermal = config["thermal"]
    for field, value in thermal.items():
        number(value, field, strictly_positive=field == "time_constant_seconds")
    for field in ("idle_load", "onboard_active_load", "external_active_load"):
        if thermal[field] > 1:
            raise ValueError("Thermal loads must be fractions between zero and one")
    for scenario in config["scenarios"].values():
        number(scenario.get("initial_temperature_c", thermal["initial_c"]), "initial temperature")
        for field in ("station_outages", "network_outages"):
            for outage in scenario[field]:
                number(outage["start"], "outage start")
                number(outage["end"], "outage end")
                if outage["end"] <= outage["start"]:
                    raise ValueError("Outage end must follow its start")
                if field == "station_outages" and outage["station"] not in stations:
                    raise ValueError("Outage station is not configured")


class Simulation:
    def __init__(self, workload: list[SimulatedLot], config: dict,
                 pi_model: str, controller: str, scenario_name: str):
        validate_workload(workload, config["stations"])
        if controller not in CONTROLLERS:
            raise ValueError("Unknown controller")
        self.env = simpy.Environment()
        self.config = config
        self.profile = config["pi_profiles"][pi_model]
        self.scenario = config["scenarios"][scenario_name]
        self.controller = controller
        self.external = controller != "onboard_fifo"
        self.policy = "available_first" if controller == "external_adaptive" else "fifo"
        self.workload = sorted(workload, key=lambda lot: (lot.arrival_seconds, lot.lot_id))
        self.lots = {lot.lot_id: lot for lot in workload}
        self.queue: list[LotTask] = []
        self.busy_until = {station: 0.0 for station in config["stations"]}
        self.context = {
            "run_id": f"{pi_model}-{controller}-{scenario_name}-{workload[0].seed}",
            "pi_model": pi_model, "controller": controller,
            "scenario": scenario_name, "seed": workload[0].seed, "source": "synthetic",
        }
        self.rows = {
            lot.lot_id: {
                **self.context, "lot_id": lot.lot_id, "destination": lot.destination,
                "arrival_seconds": lot.arrival_seconds, "start_seconds": None,
                "completion_seconds": None, "queue_seconds": None, "transfer_seconds": None,
                "total_seconds": None, "command_seconds": None, "outcome": "not_arrived",
            } for lot in workload
        }
        self.temperatures = []
        self.temperature_c = self.scenario.get("initial_temperature_c", config["thermal"]["initial_c"])
        self.temperature_updated_at = 0.0
        self.cpu_load = config["thermal"]["idle_load"]
        self.network_blocked_seconds = 0.0

    def outage_end(self, field: str, station: str | None = None) -> float:
        ends = [self.env.now]
        for outage in self.scenario[field]:
            if outage["start"] <= self.env.now < outage["end"]:
                if station is None or outage["station"] == station:
                    ends.append(outage["end"])
        return max(ends)

    def availability(self) -> dict[str, bool]:
        return {
            station: end <= self.env.now and self.outage_end("station_outages", station) <= self.env.now
            for station, end in self.busy_until.items()
        }

    def update_temperature(self) -> None:
        thermal = self.config["thermal"]
        target = thermal["ambient_c"] + thermal["idle_rise_c"] + self.cpu_load * thermal["load_rise_c"]
        elapsed = self.env.now - self.temperature_updated_at
        self.temperature_c = target + (self.temperature_c - target) * math.exp(
            -elapsed / thermal["time_constant_seconds"]
        )
        self.temperature_updated_at = self.env.now

    def set_load(self, load: float) -> None:
        self.update_temperature()
        self.cpu_load = load

    def arrivals(self):
        for lot in self.workload:
            yield self.env.timeout(lot.arrival_seconds - self.env.now)
            self.queue.append(LotTask(lot.lot_id, lot.destination))
            self.rows[lot.lot_id]["outcome"] = "pending"

    def thermal_monitor(self):
        while True:
            self.update_temperature()
            self.temperatures.append({
                **self.context, "time_seconds": self.env.now,
                "temperature_c": self.temperature_c,
                "status": "simulated_warning" if self.temperature_c >= self.config["temperature_warning_c"]
                else "simulated_ok",
            })
            yield self.env.timeout(self.config["temperature_interval_seconds"])

    def command_delay(self, lot_id: str) -> float:
        if not self.external:
            return self.profile["onboard_decision_seconds"]
        # Stable, per-lot jitter: policy order cannot change the random network sample.
        digest = hashlib.sha256(f"{self.context['seed']}:{lot_id}".encode()).digest()
        unit = int.from_bytes(digest[:8], "big") / (2**64 - 1)
        return (
            self.config["laptop_decision_seconds"] + self.profile["command_handling_seconds"]
            + self.config["network"]["round_trip_seconds"]
            + unit * self.config["network"]["jitter_seconds"]
        )

    def controller_process(self):
        thermal = self.config["thermal"]
        while True:
            if self.external and self.queue:
                end = self.outage_end("network_outages")
                if end > self.env.now:
                    remaining = min(end, self.config["horizon_seconds"]) - self.env.now
                    self.network_blocked_seconds += max(0, remaining)
                    yield self.env.timeout(end - self.env.now)
                    continue
            decision = choose_next(self.queue, self.availability(), self.policy)
            if decision.task is None:
                yield self.env.timeout(self.config["poll_interval_seconds"])
                continue
            task = decision.task
            delay = self.command_delay(task.lot_id)
            self.set_load(0.4 if self.external else 0.8)
            yield self.env.timeout(delay)
            self.set_load(thermal["idle_load"])
            if self.external and self.outage_end("network_outages") > self.env.now:
                # No command was delivered; leave the lot queued. Never duplicate a transfer.
                continue
            if not self.availability()[task.destination]:
                continue
            self.queue.remove(task)
            lot = self.lots[task.lot_id]
            row = self.rows[task.lot_id]
            row.update(start_seconds=self.env.now, queue_seconds=self.env.now - lot.arrival_seconds,
                       command_seconds=delay, outcome="in_progress")
            self.busy_until[task.destination] = math.inf  # Reserve its receiving slot.
            self.set_load(thermal["external_active_load"] if self.external else thermal["onboard_active_load"])
            yield self.env.timeout(lot.transfer_seconds)
            # If an outage began in transit, wait rather than pretending delivery succeeded.
            while self.outage_end("station_outages", task.destination) > self.env.now:
                yield self.env.timeout(self.outage_end("station_outages", task.destination) - self.env.now)
            failed = lot.failure_draw < self.config["failure_probability"]
            row.update(
                completion_seconds=self.env.now,
                transfer_seconds=self.env.now - row["start_seconds"],
                total_seconds=self.env.now - lot.arrival_seconds,
                outcome="failed" if failed else "delivered",
            )
            self.busy_until[task.destination] = self.env.now + (0 if failed else lot.station_process_seconds)
            self.set_load(thermal["idle_load"])

    def run(self) -> tuple[dict, list[dict], list[dict]]:
        self.env.process(self.arrivals())
        self.env.process(self.thermal_monitor())
        self.env.process(self.controller_process())
        horizon = self.config["horizon_seconds"]
        self.env.run(until=horizon)
        trials = list(self.rows.values())
        finished = [row for row in trials if row["outcome"] in {"delivered", "failed"}]
        arrived = [row for row in trials if row["arrival_seconds"] < horizon]
        delivered = sum(row["outcome"] == "delivered" for row in trials)
        failed = sum(row["outcome"] == "failed" for row in trials)
        waiting = sum(row["outcome"] == "pending" for row in trials)
        active = sum(row["outcome"] == "in_progress" for row in trials)

        def average(field):
            return sum(row[field] for row in finished) / len(finished) if finished else None

        summary = {
            **self.context, "horizon_seconds": horizon, "arrived": len(arrived),
            "delivered": delivered, "failed": failed, "pending": waiting, "in_progress": active,
            "not_arrived": len(trials) - len(arrived),
            "throughput_per_minute": delivered / (horizon / 60),
            "delivery_fraction": delivered / len(arrived) if arrived else None,
            "handling_success_fraction": delivered / len(finished) if finished else None,
            "mean_queue_seconds_finished_only": average("queue_seconds"),
            "mean_total_seconds_finished_only": average("total_seconds"),
            "mean_command_seconds_finished_only": average("command_seconds"),
            "network_blocked_seconds": self.network_blocked_seconds,
            "max_temperature_c": max(row["temperature_c"] for row in self.temperatures),
            "temperature_warning_samples": sum(row["status"] == "simulated_warning" for row in self.temperatures),
        }
        assert len(arrived) == delivered + failed + waiting + active
        return summary, trials, self.temperatures
