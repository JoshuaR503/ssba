# MasterPi Pi 5 / 4 GB wafer-handling prototype

The Mac Python environment contains pandas, matplotlib, requests, Flask, SimPy,
scikit-learn, joblib, and Gunicorn.
This scaffold separates scheduling, communication, robot control, and CPU telemetry.
No application or robot movement is started by installation or by importing modules.

Documentation: [index and backup scope](docs/README.md) · [beginner AI prompt](docs/beginner_robot_prompt.md) · [project report](docs/comprehensive_project_report.md).

## Working physical pickup — 2026-10-17

The operator reported the calibrated non-LLM transfer and corrected AI image-check version worked. Current commands run from the Mac against the Pi vendor service:

```bash
python3 scripts/test_pickup_without_id4.py --execute
python3 llm_supervisor/pickup.py --execute
python3 llm_supervisor/calibration.py --go
```

Across these scripts, `--execute` is automatic and `--go` is step by step; no flags preview only. Movements are 500 ms, with no startup countdown. Green=deposition, blue/cyan=metrology, red=etch. ID4 is excluded and ID3 >=30. The AI checks at exact open pickup height before closing, uses a weak “likely carrying” color cue after lift, and treats release imagery as advisory. This is not measured grip confirmation or a validated fully autonomous system.

See [working guide](docs/working_pickup.md), [AI/calibration guide](llm_supervisor/README.md), [session results](docs/session_2026-10-17.md), and [PyDoc](llm_supervisor/pydoc/index.md). The scaffold adapter mentioned below is a separate subsystem from these vendor-RPC pickup scripts.

## Current status

For copying/installing the project on the robot, start with
[ROBOT_ONBOARDING.md](</Users/joshua/Desktop/ai-based wafer/ROBOT_ONBOARDING.md>).
The transfer bundle is dist/masterpi-wafer-pi5.zip; onboarding performs no movement.

- **AI integration:** an actual SECOM-trained quality classifier, analysis API and human
  review log are implemented. **RAG is excluded.** Local inference and HTTP integration
  are tested; the cloud container is prepared but not deployed. See
  [AI_INTEGRATION.md](</Users/joshua/Desktop/ai-based wafer/AI_INTEGRATION.md>) for real-data
  provenance, evaluation limitations and the cloud/local distinction.
- **Confirmed hardware:** MasterPi with Raspberry Pi 5 and 4 GB RAM. The active configuration
  targets this robot. A vendor-SDK adapter, read-only hardware check and calibrated local
  transfer runner are implemented. Calibration is incomplete and motion defaults to disabled.
  See [PHYSICAL_DESIGN.md](</Users/joshua/Desktop/ai-based wafer/PHYSICAL_DESIGN.md>) for
  the physical build and first robot session. The adapter has not been tested on the robot.
- **Hardware CPU monitoring: real readings only**, taken on a Raspberry Pi through Linux sysfs.
  On a Mac or when the sensor cannot be read, the value is `null` with status `unavailable`.
- **Station availability: manually configured mock state**, not live equipment status.
- **Software simulation: Pi 5 / 4 GB only**, with onboard FIFO, external FIFO,
  and external available-first controllers. Synthetic temperatures are kept separate from sensor data.
- Offline tests and software simulations run on the Mac. Physical commands are explicit,
  local to the Pi, and separate from the mock HTTP transfer endpoint.
- Python 3.10+ is needed by this scaffold; the existing Mac environment uses Python 3.12.
  Check the Pi's existing Python and vendor software before installing anything there.

## Files and responsibilities

| File | Responsibility |
| --- | --- |
| `config.json` | Robot address, station state, polling interval, advisory temperature threshold |
| `wafer_project/models.py` | Validate lot IDs and eligible destinations |
| `wafer_project/scheduler.py` | FIFO and available-first decisions; no command execution |
| `wafer_project/client.py` | Explicit HTTP calls from the laptop, with timeouts |
| `wafer_project/api.py` | Flask endpoints on the computer running the server |
| `wafer_project/robot.py` | Mock driver for offline API checks |
| `hardware/pi5_4gb.json`, `hardware/calibration.json` | Confirmed hardware profile and measured motion plans |
| `wafer_project/pi5_hardware.py` | Read-only hardware check and transfer preview |
| `wafer_project/pi5_driver.py` | Explicit local vendor-SDK execution and physical event logs |
| `data/lot_manifest.json`, `wafer_project/lot_records.py` | Explicit carrier-label to real SECOM dataset replay association |
| `wafer_project/telemetry.py` | Read the Pi CPU/SoC temperature |
| `wafer_project/csv_log.py` | CSV logging of temperature observations and simulated transfers |
| `wafer_project/analysis.py` | Generate a PNG from actual recorded temperature samples |
| `wafer_project/cli.py` | Commands that start work only when explicitly invoked |
| `simulation_config.json` | Editable, explicitly synthetic timings, outages and thermal assumptions |
| `wafer_project/workload.py` | Generate repeatable synthetic lot datasets |
| `wafer_project/simulation.py` | SimPy event engine for Pi 5/controller comparisons |
| `wafer_project/simulation_report.py` | Matched runs, CSV exports, provenance and charts |
| `data/example_tasks.json` | Illustrative tasks, not experimental measurements |
| `tests/test_core.py` | Optional offline checks; no physical robot or live network needed |

Network preview flow: laptop scheduler → explicit HTTP client → robot API → mock driver.
Physical execution flow: calibrated local plan → Pi 5 runner → vendor SDK.
Temperature flow: Pi CPU sensor → `/temperature` → laptop monitor → CSV → optional PNG.
The scheduler does not dispatch tasks automatically.

## Libraries and environment

Cursor is already configured to use `.venv/bin/python` in `.vscode/settings.json`.
In a new terminal, activate the existing environment:

```bash
cd "/Users/joshua/Desktop/ai-based wafer"
source .venv/bin/activate
```

`requirements.txt` is the laptop dependency list. `requirements-lock.txt` records the
currently installed environment for later reproducibility on a compatible Mac/Python.
`requirements-robot.txt` contains only Flask; monitoring and CSV logging use the standard
library. Do not copy the Mac `.venv` onto the robot. The Pi gets its own environment later,
preserving its manufacturer-provided hardware libraries until compatibility is checked.

## Run the software simulation

The current Pi 5 suite has completed **360 runs, 8,640 lot observations,
and 43,200 synthetic temperature samples**. The
[current results report](</Users/joshua/Desktop/ai-based wafer/data/simulations/pi5-4gb-2026-10-16/report.md>)
contains charts and per-scenario summaries. Earlier exploratory runs remain historical
records under data/simulations; they do not define the active hardware configuration.

From the activated project environment:

```bash
python -m wafer_project simulate
```

Defaults: **360 runs**, covering 1 Pi 5 profile × 3 controllers × 4 scenarios × 30 seeds,
with 24 lots per workload and a 600-second simulated observation window. These runs
advance a virtual SimPy clock; you do not wait 600 real seconds per trial.
The default output is a new timestamped directory under `data/simulations/`.

A smaller run, or an explicitly named new output directory:

```bash
python -m wafer_project simulate --seeds 3 --lots 12
python -m wafer_project simulate --output data/simulations/my-next-run --seeds 30 --lots 24
```

Existing nonempty output directories are refused to preserve previous experiments.

The four scenarios are normal operation, an ETCH station outage, an external network
outage, and a warm CPU. The Pi 5 profile contains illustrative decision/command timing,
physical transfer assumptions and an illustrative thermal model. Replace assumptions
with actual measurements as physical trials are collected. The confirmed model/RAM
does not turn simulation timings into hardware benchmarks.

For each seed the same arrivals, destinations, transfer durations, processing durations,
failure draws and per-lot network jitter are used in every matched controller run.
The scheduler reuses the starter's `choose_next` function. It never treats an ETCH lot
as eligible for DEPOSITION simply because that station is free.

Outputs include:

| File | Content |
| --- | --- |
| `workload.csv` | Generated synthetic input dataset, one row per seed/lot |
| `lot_results.csv` | Every lot outcome, including failures and unfinished work |
| `run_summary.csv` | Counts, throughput, finished-lot latency and temperature alerts per run |
| `aggregate_summary.csv` | Means and variability across seeds |
| `temperature_simulated.csv` | Virtual CPU temperature traces labeled synthetic |
| `comparison.png`, `temperature.png` | Throughput and thermal charts |
| `manifest.json` | Seeds, package versions, input checksum and complete assumptions |
| `report.md` | Results and explanation of metrics/limitations |

Transport-simulation inputs are synthetic and retained separately from the real Kaggle
SECOM dataset used by the AI classifier, so provenance can be reviewed.
Thermal alerts are advisory and do not simulate throttling. Network timing is modeled
with SimPy events, not real Wi-Fi or HTTP traffic. Throughput counts successful deliveries
within the fixed window; downstream station processing may finish after that window.

## Scheduling, mock API and real-sensor monitoring commands

Scheduling previews only; these never contact the robot:

```bash
python -m wafer_project plan --policy fifo
python -m wafer_project plan --policy available_first
```

The physical prototype config initially marks all mock stations available. To preview a
disruption, mark ETCH false in config.json: FIFO waits on W001; available-first selects
W002 for DEPOSITION. This state is manually entered, not inferred from a physical sensor.
Alternative stations are considered only when explicitly listed
in a lot's `alternatives` array. A station having a different process is not automatically
an eligible replacement.

Start the mock server explicitly on this computer:

```bash
python -m wafer_project serve
```

| Endpoint | Behavior |
| --- | --- |
| `GET /health` | Reports service state and `hardware_control: false` |
| `GET /temperature` | Reads the server computer's Pi CPU sensor; no CSV write |
| `GET /hardware` | Read-only Pi 5 identity, RAM and SDK-path inspection |
| `POST /transfers` | Validates a task and records a **simulated** transfer; no physical movement |

A transfer body contains `lot_id` and `destination`, for example
`{"lot_id": "W002", "destination": "DEPOSITION"}`. This endpoint remains mock-only;
the calibrated physical runner is invoked locally on the Pi using robot-run.
Simulated transfers are logged to `data/logs/transfers.csv` with `outcome=simulated`.
They are not successes, timing measurements, or real experimental trials.

Sample the local Pi CPU temperature, or the configured remote server:

```bash
python -m wafer_project monitor --samples 12 --interval 5
python -m wafer_project monitor --remote --samples 12 --interval 5
```

Both commands append `data/logs/temperature.csv`. On your Mac, local monitoring reports
`unavailable`. Remote monitoring reports the temperature of the **server computer**;
the server must eventually run on the Pi to measure the Pi. Network errors are also
recorded as unavailable observations. Missing values remain blank in CSV, never zero.
Sampling is finite; Ctrl+C stops it early. Only an explicit monitor command polls.

Later, when we set up the Pi, its server can bind to `0.0.0.0` on the local network using
`serve --host 0.0.0.0`. Set the Mac's `robot_url` to `http://<PI-IP>:5000`.
The starter Flask server is for local development and contains no authentication.
Remote physical execution is not enabled in this API. See PHYSICAL_DESIGN.md for the
explicit local physical command, calibration requirements and remaining remote-control work.

Plot recorded readings:

```bash
python -m wafer_project plot-temperature
```

This writes `data/results/temperature.png`. It refuses to plot when no valid readings exist.
All timestamps use UTC and temperatures use degrees Celsius.

## Temperature behavior

The reader verifies `/proc/device-tree/model` identifies a Raspberry Pi, then reads
`/sys/class/thermal/thermal_zone0/temp` and converts millidegrees to degrees Celsius.
An unreadable/missing sensor or invalid value produces an explicit unavailable result.
The configurable default warning of **75°C** is a project advisory setting, not a claimed
manufacturer limit. Warnings are displayed and logged; they do not control fans, shut down
the Pi, or stop a robot. This is CPU/SoC temperature, not room or wafer temperature.

References:
- [Linux thermal sysfs interface](https://docs.kernel.org/driver-api/thermal/sysfs-api.html)
- [Raspberry Pi thermal control](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html)
- [Hiwonder MasterPi documentation](https://docs.hiwonder.com/projects/MasterPi/en/latest/)

## Offline checks

The current suite has passed **30 tests**, including fake-backend physical-driver checks
and the carrier-to-SECOM replay link. A live local HTTP check also exercised W001's
linked record and left its AI recommendation pending human review. No physical motion
or cloud deployment was performed.

```bash
python -m unittest discover -s tests -v
```

Tests use temporary sensor files, Flask's in-process test client, and virtual SimPy clocks.
They do not start a live server, connect to a robot, or import hardware drivers.
They verify scheduling comparisons, outage handling, unfinished-work accounting,
repeatable input data, mock API behavior and temperature warning/missing-sensor behavior.
