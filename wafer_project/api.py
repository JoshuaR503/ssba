"""Flask application factory. Importing this module never starts the server."""

from flask import Flask, jsonify, request

from .config import Settings
from .csv_log import CsvLog, TRANSFER_FIELDS
from .models import LotTask
from .robot import MockRobot
from .telemetry import PiCpuTemperatureReader
from .pi5_hardware import DEFAULT_PROFILE, inspect_hardware, load_profile


def create_app(settings: Settings) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
    reader = PiCpuTemperatureReader(settings.temperature_warning_c)
    robot = MockRobot()
    transfers = CsvLog(settings.log_directory / "transfers.csv", TRANSFER_FIELDS)

    @app.get("/health")
    def health():
        return jsonify(status="ok", robot_mode="mock", hardware_control=False,
                       target_hardware="masterpi_pi5_4gb")

    @app.get("/hardware")
    def hardware():
        return jsonify(inspect_hardware(load_profile(settings.hardware_profile or DEFAULT_PROFILE)))

    @app.get("/temperature")
    def temperature():
        # Read-only snapshot. CSV sampling is handled explicitly by the monitor CLI.
        return jsonify(reader.read().to_dict())

    @app.post("/transfers")
    def transfer():
        if not request.is_json:
            return jsonify(error="Expected application/json"), 415
        try:
            task = LotTask.from_dict(request.get_json(), settings.stations)
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        if not settings.stations[task.destination]:
            return jsonify(error="Destination is marked unavailable"), 409
        result = robot.transfer(task)
        transfers.append(result)
        return jsonify(result)

    return app
