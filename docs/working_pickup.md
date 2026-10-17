# Working MasterPi pickup baseline

The operator reported that the updated three-station cycle worked on 2026-10-17. This commit preserves that behavior and adds documentation. It does not certify the broader project requirements or claim measured grasp accuracy. The assistant's earlier network attempt stopped at step 1 with “No route to host”; physical success is based on the operator's later report.

## Run from the Mac

The existing entry point stays `scripts/test_pickup_without_id4.py`. It calls the Raspberry Pi vendor service over LAN; the script does not need to be uploaded to the Pi. The Pi must already run the vendor HTTP JSON-RPC service on port 9030. Use the taught physical layout, an empty gripper, a ready tray and stable ID4. Keep competing phone/autonomous controls idle.

```bash
cd "/Users/joshua/Desktop/ai-based wafer"
python3 scripts/test_pickup_without_id4.py
python3 scripts/test_pickup_without_id4.py --execute
```

The first command previews only. The second starts one complete cycle after five seconds, with no `go` prompts. The project's `.venv/bin/python` can replace `python3`. Normal execution requires only the standard library. No installation, cloud AI, API key, wheel control or scheduler is involved.

Station order is **deposition (green), metrology (blue/cyan), etch (red)**. Each station follows start → open approach → lower → grip → lift → turn to tray → lower → release → retract empty → turn back → return to start. All three produce 33 commands. Each move requests **500 ms**, followed by **150 ms settling**, in addition to network time; the five-second countdown occurs once.

## Command-line options

| Option | Effect |
| --- | --- |
| no options | Validate and print all 33 commands; no movement |
| `--execute` | Send the printed plan once after countdown |
| `--cube deposition`, `metrology`, or `etch` | Select one 11-command station cycle; default `all` |
| `--host HOST` | Override `raspberrypi.local`; movement uses port 9030 |
| `--step` | Optional per-command `go` confirmation; requires `--execute` for motion |
| `--vision` | Select one calibrated station using local camera snapshots |
| `--configure-vision` | Draw/save three camera zones; sends no movement |
| `--at-observation-pose` | Required operator assertion for camera modes |
| `--vision-config PATH` | Calibration JSON path; default `hardware/camera_pickup_zones.json` |
| `--distances-cm D M E` | Three calibration distances in centimeters, deposition/metrology/etch order |

Examples:

```bash
python3 scripts/test_pickup_without_id4.py --cube etch
python3 scripts/test_pickup_without_id4.py --cube etch --execute
python3 scripts/test_pickup_without_id4.py --host raspberrypi.local --execute
```

## Pose configuration and provenance

`hardware/station_poses.json` is the required runtime data file. `pose_set` must equal `station-photos-v6`. `stations` is the only active pose map; its insertion order determines the all-station sequence. `historical_pose_set` preserves older values as provenance and is never used to build movements. `record` paths refer to local photo archives, not runtime dependencies. Those image archives are excluded from this focused commit.

Targets are app command values, not measured degrees, millimeters or percentages. The runner adds **+0.5 to ID5** for approach, lift and empty-arm retract. Contact and tray-lowering settings stay exact. Unspecified joints retain their previous command. Source screenshots show ID4=20/4/0 for deposition/metrology/etch respectively; these observations do not become commands. ID4 is omitted throughout.

| Station | Source screenshots | Start | Approach | Pickup | Raised | Tray lower | Open / grip / release |
| --- | --- | --- | --- | --- | --- | --- | --- |
| deposition (green) | IMG_0992–1005 | 1:4, 3:60, 5:-6, 6:-4 | 3:74, 5:-56, 6:-4 | 3:74, 5:-56, 6:-4 | 3:74, 5:-34, 6:-4 | 3:90, 5:-54, 6:90 | -30 / -2 / -24 |
| metrology (blue/cyan) | IMG_1008–1020 | 1:4, 3:48, 5:4, 6:0 | 3:70, 5:-48, 6:-46 | 3:70, 5:-60, 6:-46 | 3:70, 5:-32, 6:-46 | 3:90, 5:-70, 6:90 | -40 / -2 / -36 |
| etch (red) | IMG_1022–1038 | 1:4, 3:48, 5:4, 6:0 | 3:76, 5:-50, 6:32 | 3:80, 5:-60, 6:32 | 3:80, 5:-30, 6:32 | 3:90, 5:-58, 6:90 | -42 / 6 / -44 |

Table entries are stored reference values **before clearance trim**. Metrology has no exact start screenshot: it uses the latest etch start. Its pre-turn lift uses ID3=70/ID5=-32 from the later tray-turn screenshot, retaining pickup base=-46; that intermediate is derived. Empty-arm return paths were also derived, not supplied as new photo pairs. The operator's reported working run does not remove these provenance distinctions.

## Validation, dispatch and stopping

`build_steps` copies the reference poses and validates the entire selected plan before any network request. `payload` allows only IDs 1, 3, 5, 6, finite targets in [-90,90], ID3 >=30 and duration=500. It formats JSON-RPC `SetPWMServo` params as `[500, id, target, ...]`.

`main` dispatches sequential HTTP POSTs to `http://HOST:9030/`, with a five-second request timeout. A vendor result list starting with literal `true` and no error is accepted. Acceptance confirms the service response, not actual grip, position or release. Each accepted command waits 0.65 seconds before the next dispatch.

Rejection, caught network failure, Ctrl+C or EOF stops future commands. There is no automatic retry, return, release or recovery. A command already sent may finish; a failed response does not prove the command was ignored. In step mode any answer other than `go` cancels. Main returns 0 for preview/completion/step cancellation and 1 for caught execution or vision errors; argparse/configuration errors can terminate earlier.

There is no joint feedback, collision detection, force sensing, grip verification or live correction. Omitting ID4 does not electrically isolate it or mechanically lock it. The tested sequence assumes the taught robot/cube/tray arrangement. The final etch demonstration rests red above the other cubes; this is not a general stacking planner.

Terminal colors use ANSI when stdout is a terminal; `NO_COLOR` disables them. Redirected logs remain plain text.

## Optional camera mode

This mode is retained separately from the operator-reported working `--execute` sequence. It selects a saved station, then plays that station's pose sequence; it does not calculate a new grasp for arbitrary cube locations. It uses no external AI or ultrasonic depth. Optional dependencies are in `requirements-vision.txt`:

```bash
python3 -m pip install -r requirements-vision.txt
```

Before calibration, manually establish the observation pose `{1:4, 3:48, 5:4, 6:0}` with ID4 left untouched. The flag asserts readiness; it does not move or measure the arm. Draw each cube tightly, confirm in the image window, and enter positive measured distances when prompted.

```bash
python3 scripts/test_pickup_without_id4.py --configure-vision --at-observation-pose
python3 scripts/test_pickup_without_id4.py --vision --at-observation-pose
python3 scripts/test_pickup_without_id4.py --vision --at-observation-pose --execute
```

Calibration and overlay images are machine/layout-specific outputs and are excluded from this commit. Old calibration lacks the current version/observation pose and is rejected before camera reads. Camera snapshots use port 8080, a four-second timeout and an 8 MB cap. OpenCV detects calibrated LAB color in each ROI, checks area and centrality, requires three samples stable within eight pixels, and ranks by measured station distance. The locked station is rechecked after countdown before sending movement. A changed layout, camera pose or joint sag invalidates the calibration assumptions.

## Python API and generated PyDoc

- `duration_for(label)`: fixed 500 ms.
- `joint_pose(raw)`: copy JSON targets with integer IDs.
- `build_steps(selection='all')`: validate and return labeled target dictionaries; no network.
- `color(text, code)`: optional terminal formatting.
- `payload(joints, request_id, duration_ms=500)`: validate and encode; no network.
- `main()`: CLI, optional camera selection, preview and guarded dispatch.

Every runner/helper function has a docstring. [Runner PyDoc](pydoc/test_pickup_without_id4.html) and [optional vision helper PyDoc](pydoc/cube_vision.html) are generated directly from these modules. Regenerate from the repository root:

```bash
PYTHONPATH=scripts python3 -m pydoc test_pickup_without_id4
PYTHONPATH=scripts python3 -m pydoc cube_vision
```

For HTML, run `python3 -m pydoc -w test_pickup_without_id4 cube_vision` with the repository's absolute `scripts` path in `PYTHONPATH`, from `docs/pydoc`. Importing either module for documentation sends no robot commands. The runner imports its versioned pose file, so preserve the repository folder layout.

## Verification

```bash
python3 -m unittest discover -s tests -p 'test_station_pickup.py'
# Optional vision tests also require requirements-vision.txt:
python3 -m unittest discover -s tests
```

Tests use mocked HTTP, sleep and camera access; they send no robot commands. They cover exact contact/release regression values, all 33 commands at 500 ms, ID exclusion/ID3 bounds, invalid later-station rejection before dispatch, stopping on service rejection, stale camera calibration, and synthetic vision selection. During documentation, executable AST comparison confirmed that comments/docstrings did not change either Python module's behavior.
