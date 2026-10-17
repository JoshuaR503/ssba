"""Explicit entry points; no automatic robot dispatch or monitoring on import."""

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

from .config import PROJECT_ROOT, load_settings, positive_number
from .csv_log import CsvLog, TEMPERATURE_FIELDS
from .models import LotTask
from .scheduler import choose_next
from .telemetry import PiCpuTemperatureReader, unavailable_reading


def main() -> int:
    parser = argparse.ArgumentParser(description="MasterPi Pi 5 / 4 GB: calibrated hardware, simulation and AI analysis")
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "config.json")
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="Print one scheduling decision; send no commands")
    plan.add_argument("--tasks", type=Path, default=PROJECT_ROOT / "data/example_tasks.json")
    plan.add_argument("--policy", choices=["fifo", "available_first"], default="fifo")
    serve = commands.add_parser("serve", help="Start the mock API explicitly")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=5000)
    for command in ("robot-check", "robot-plan", "robot-run"):
        robot = commands.add_parser(command, help={
            "robot-check": "Read Pi 5 identity, RAM, temperature and SDK paths without motion",
            "robot-plan": "Preview calibrated transfer steps without importing vendor drivers",
            "robot-run": "Preview a physical transfer; --execute enables calibrated local motion",
        }[command])
        robot.add_argument("--profile", type=Path, default=PROJECT_ROOT / "hardware/pi5_4gb.json")
        if command != "robot-check":
            robot.add_argument("--lot-id", default="W001")
            robot.add_argument("--destination", choices=["ETCH", "DEPOSITION", "METROLOGY"], default="ETCH")
        if command == "robot-run":
            robot.add_argument("--execute", action="store_true")
    monitor = commands.add_parser("monitor", help="Read CPU temperature and append CSV samples")
    monitor.add_argument("--remote", action="store_true", help="Read the configured robot URL")
    monitor.add_argument("--samples", type=int, default=1, help="Finite number of readings")
    monitor.add_argument("--interval", type=float, help="Seconds between readings")
    plot = commands.add_parser("plot-temperature", help="Plot an existing temperature CSV")
    plot.add_argument("--csv", type=Path)
    plot.add_argument("--output", type=Path, default=PROJECT_ROOT / "data/results/temperature.png")
    simulate = commands.add_parser("simulate", help="Run matched software-only Pi/controller trials")
    simulate.add_argument("--simulation-config", type=Path, default=PROJECT_ROOT / "simulation_config.json")
    simulate.add_argument("--output", type=Path)
    simulate.add_argument("--seeds", type=int, default=30)
    simulate.add_argument("--lots", type=int, default=24)
    simulate.add_argument("--starting-seed", type=int, default=20261012)
    train_ai = commands.add_parser("ai-train", help="Train and evaluate the SECOM quality model")
    train_ai.add_argument("--dataset", type=Path, default=PROJECT_ROOT / "data/datasets/secom/uci-secom.csv")
    train_ai.add_argument("--output", type=Path, default=PROJECT_ROOT / "data/ai/secom-v1")
    fetch_ai = commands.add_parser("ai-download", help="Download the real public Kaggle SECOM CSV")
    fetch_ai.add_argument("--output", type=Path, default=PROJECT_ROOT / "data/datasets/secom")
    serve_ai = commands.add_parser("ai-serve", help="Start the trained AI API; no RAG or robot control")
    serve_ai.add_argument("--artifacts", type=Path, default=PROJECT_ROOT / "data/ai/secom-v1")
    serve_ai.add_argument("--database", type=Path, default=PROJECT_ROOT / "data/ai/reviews.sqlite3")
    serve_ai.add_argument("--host", default="127.0.0.1")
    serve_ai.add_argument("--port", type=int, default=5051)
    demo_ai = commands.add_parser("ai-demo", help="Send a held-out SECOM record to the trained AI API")
    demo_ai.add_argument("--url", default="http://127.0.0.1:5051")
    demo_ai.add_argument("--sample", type=Path, default=PROJECT_ROOT / "data/ai/secom-v1/demo_input.json")
    demo_ai.add_argument("--output", type=Path, default=PROJECT_ROOT / "data/ai/secom-v1/demo_http_result.json")
    for command in ("lot-payload", "lot-analyze"):
        lot = commands.add_parser(command, help="Prepare or analyze a carrier's linked SECOM replay record")
        lot.add_argument("--lot-id", required=True)
        lot.add_argument("--manifest", type=Path, default=PROJECT_ROOT / "data/lot_manifest.json")
        if command == "lot-analyze":
            lot.add_argument("--url", default="http://127.0.0.1:5051")
            lot.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        if args.command in {"lot-payload", "lot-analyze"}:
            from .lot_records import prepare_lot_analysis

            prepared = prepare_lot_analysis(args.lot_id, args.manifest)
            if args.command == "lot-payload":
                result = prepared
            else:
                import requests
                from .ai_client import AiClient
                from uuid import uuid4

                try:
                    prediction = AiClient(args.url).analyze(prepared["payload"])
                except requests.RequestException as exc:
                    raise ValueError(f"AI API request failed: {exc}") from exc
                result = {key: value for key, value in prepared.items() if key != "payload"}
                result["prediction"] = prediction
                output = args.output or PROJECT_ROOT / "data/ai/lot-analyses" / f"{uuid4()}.json"
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
                result["saved_to"] = str(output)
            print(json.dumps(result, indent=2, allow_nan=False))
            return 0
        if args.command in {"robot-check", "robot-plan", "robot-run"}:
            from .pi5_hardware import inspect_hardware, load_profile, transfer_preview

            profile = load_profile(args.profile)
            if args.command == "robot-check":
                result = inspect_hardware(profile)
            else:
                task = LotTask.from_dict({"lot_id": args.lot_id, "destination": args.destination},
                                         {"ETCH": True, "DEPOSITION": True, "METROLOGY": True})
                if args.command == "robot-plan":
                    result = transfer_preview(task, profile)
                else:
                    import signal
                    from .pi5_driver import Pi5TransferRunner

                    settings = load_settings(args.config)
                    if not settings.stations.get(task.destination, False):
                        raise ValueError("Destination is marked unavailable in config.json")
                    runner = Pi5TransferRunner(profile, settings.log_directory)
                    old_handlers = {}
                    if args.execute:
                        for signum in (signal.SIGINT, signal.SIGTERM):
                            old_handlers[signum] = signal.signal(signum, lambda *_: runner.cancel())
                    try:
                        result = runner.execute(task, execute=args.execute)
                    finally:
                        for signum, handler in old_handlers.items():
                            signal.signal(signum, handler)
            print(json.dumps(result, indent=2))
            return 0
        if args.command == "ai-download":
            from .ai_data import download_secom
            import requests

            try:
                print(json.dumps(download_secom(args.output), indent=2))
            except requests.RequestException as exc:
                raise ValueError(f"Dataset download failed: {exc}") from exc
            return 0
        if args.command == "ai-train":
            from .ai_training import train_secom

            print(json.dumps(train_secom(args.dataset, args.output), indent=2))
            return 0
        if args.command == "ai-serve":
            import os
            from .ai_api import create_ai_app

            if not 1 <= args.port <= 65535:
                raise ValueError("port must be between 1 and 65535")
            token = os.environ.get("AI_API_TOKEN")
            if args.host not in {"127.0.0.1", "localhost", "::1"} and not token:
                raise ValueError("Set AI_API_TOKEN before listening outside localhost")
            create_ai_app(args.artifacts, args.database, token).run(
                host=args.host, port=args.port, debug=False, use_reloader=False)
            return 0
        if args.command == "ai-demo":
            from .ai_client import AiClient
            import requests

            try:
                result = AiClient(args.url).analyze(json.loads(args.sample.read_text()))
            except requests.RequestException as exc:
                raise ValueError(f"AI API request failed: {exc}") from exc
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
            print(json.dumps(result, indent=2))
            return 0
        if args.command == "simulate":
            from datetime import datetime, timezone
            from .simulation_report import run_suite

            output = args.output or PROJECT_ROOT / "data/simulations" / datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%fZ")
            result = run_suite(args.simulation_config, output, args.seeds, args.lots, args.starting_seed)
            print(json.dumps(result, indent=2))
            return 0
        settings = load_settings(args.config)
        if args.command == "plan":
            data = json.loads(args.tasks.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                raise ValueError("Task file must contain a JSON list")
            tasks = [LotTask.from_dict(row, settings.stations) for row in data]
            if len({task.lot_id for task in tasks}) != len(tasks):
                raise ValueError("Task lot IDs must be unique")
            decision = choose_next(tasks, settings.stations, args.policy)
            print(json.dumps(asdict(decision), indent=2))
        elif args.command == "serve":
            from .api import create_app

            if not 1 <= args.port <= 65535:
                raise ValueError("port must be between 1 and 65535")
            print("Mock robot only: no hardware control is implemented.")
            create_app(settings).run(host=args.host, port=args.port, debug=False, use_reloader=False)
        elif args.command == "monitor":
            if args.samples <= 0:
                raise ValueError("samples must be greater than zero")
            interval = positive_number(
                args.interval if args.interval is not None else settings.temperature_interval_seconds,
                "interval",
            )
            reader = PiCpuTemperatureReader(settings.temperature_warning_c)
            client = None
            if args.remote:
                from .client import RobotClient

                client = RobotClient(settings)
            log = CsvLog(settings.log_directory / "temperature.csv", TEMPERATURE_FIELDS)
            for index in range(args.samples):
                started = time.monotonic()
                if client is None:
                    reading = reader.read()
                else:
                    import requests

                    try:
                        reading = client.temperature()
                    except (requests.RequestException, ValueError) as exc:
                        reading = unavailable_reading(settings.robot_url, "http", str(exc))
                log.append(reading.to_dict())
                print(json.dumps(reading.to_dict()))
                if index + 1 < args.samples:
                    time.sleep(max(0, interval - (time.monotonic() - started)))
        elif args.command == "plot-temperature":
            from .analysis import plot_temperature

            csv_path = args.csv if args.csv is not None else settings.log_directory / "temperature.csv"
            plot_temperature(csv_path, args.output, settings.temperature_warning_c)
            print(f"Saved {args.output}")
    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        parser.exit(1, f"Error: {exc}\n")
    except KeyboardInterrupt:
        print("\nStopped.")
        return 130
    return 0
