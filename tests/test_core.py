"""Offline behavioral checks for the starter scheduler, telemetry and mock API."""

import csv
import tempfile
import unittest
from pathlib import Path

from wafer_project.api import create_app
from wafer_project.config import Settings
from wafer_project.csv_log import CsvLog, TEMPERATURE_FIELDS
from wafer_project.models import LotTask
from wafer_project.scheduler import choose_next
from wafer_project.telemetry import PiCpuTemperatureReader


class SchedulerTests(unittest.TestCase):
    def test_blocked_head_does_not_block_available_first(self):
        tasks = [LotTask("W001", "ETCH"), LotTask("W002", "DEPOSITION")]
        stations = {"ETCH": False, "DEPOSITION": True}
        self.assertIsNone(choose_next(tasks, stations, "fifo").task)
        self.assertEqual(choose_next(tasks, stations, "available_first").task, tasks[1])

    def test_only_explicitly_eligible_alternatives_are_used(self):
        stations = {"ETCH": False, "ETCH_BACKUP": True}
        self.assertIsNone(choose_next([LotTask("W001", "ETCH")], stations, "available_first").task)
        task = LotTask("W001", "ETCH", ("ETCH_BACKUP",))
        self.assertEqual(choose_next([task], stations, "available_first").task.destination, "ETCH_BACKUP")
        self.assertIsNone(choose_next([task], stations, "fifo").task)


class TemperatureTests(unittest.TestCase):
    def test_millidegrees_and_warning_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model, sensor = root / "model", root / "temp"
            model.write_text("Raspberry Pi 5 Model B\x00")
            reader = PiCpuTemperatureReader(75, sensor, model)
            sensor.write_text("42500\n")
            self.assertEqual(reader.read().temperature_c, 42.5)
            self.assertEqual(reader.read().status, "ok")
            sensor.write_text("75000\n")
            self.assertEqual(reader.read().status, "warning")

    def test_missing_or_invalid_sensor_never_returns_fake_temperature(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model, sensor = root / "model", root / "temp"
            reader = PiCpuTemperatureReader(75, sensor, model)
            self.assertIsNone(reader.read().temperature_c)
            model.write_text("Raspberry Pi 5 Model B\x00")
            for value in (None, "invalid", "999999999"):
                if value is not None:
                    sensor.write_text(value)
                reading = reader.read()
                self.assertEqual(reading.status, "unavailable")
                self.assertIsNone(reading.temperature_c)

    def test_csv_keeps_missing_readings_blank_and_writes_one_header(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reading = PiCpuTemperatureReader(model_path=root / "missing").read()
            path = root / "temperature.csv"
            log = CsvLog(path, TEMPERATURE_FIELDS)
            log.append(reading.to_dict())
            log.append(reading.to_dict())
            with path.open(newline="") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["temperature_c"], "")


class ApiTests(unittest.TestCase):
    def test_mock_contract_and_station_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings("http://127.0.0.1:5000", 5, 5, 75, Path(directory),
                                {"ETCH": False, "DEPOSITION": True})
            client = create_app(settings).test_client()
            self.assertFalse(client.get("/health").json["hardware_control"])
            hardware = client.get("/hardware")
            self.assertEqual(hardware.status_code, 200)
            self.assertEqual(hardware.json["target"], "masterpi_pi5_4gb")
            self.assertFalse(hardware.json["hardware_action_executed"])
            self.assertEqual(client.post("/transfers", json=[]).status_code, 400)
            self.assertEqual(client.post("/transfers", json={
                "lot_id": "W001", "destination": "UNKNOWN"
            }).status_code, 400)
            self.assertEqual(client.post("/transfers", json={
                "lot_id": "W001", "destination": "ETCH"
            }).status_code, 409)
            result = client.post("/transfers", json={
                "lot_id": "W002", "destination": "DEPOSITION"
            })
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json["outcome"], "simulated")
            with (Path(directory) / "transfers.csv").open(newline="") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["controller"], "mock")


if __name__ == "__main__":
    unittest.main()
