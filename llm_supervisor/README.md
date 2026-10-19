# Pickup with optional AI image checks

The latest calibrated movement sequence is now used by both pickup versions. See [final working guide](../docs/working_pickup.md) and [generated PyDoc](pydoc/index.md). Motion equality is tested. The LLM version adds image checkpoints and optional natural-language station ordering; it does not generate joint targets. No physical execution occurred during this integration.

## Flags — the same meaning everywhere

| Flag | Behavior |
| --- | --- |
| none | Offline preview; no movement/API calls |
| `--execute` | Automatic execution; no per-move prompts |
| `--go` | Step by step; type literal `go` before each move |

No startup countdown. Every move requests **500 ms**, followed by 150 ms settling. API time is additional. On any runner Ctrl+C stops future dispatch; a sent movement may finish. In manual mode any response other than `go` stops.

## Calibration — fingers stay open

```bash
python3 llm_supervisor/calibration.py --go
python3 llm_supervisor/calibration.py --execute
```

Calibration never grips or transfers. It traverses green/deposition, blue/metrology, red/etch, with exact open pickup-height positions to help place/mark cubes. Use `--go` if you need time at pickup height; automatic mode has no pickup hold. `--cube etch` etc selects one station.

All-station calibration is 13 moves: 3 green, 5 blue, 5 red. Exact no-op moves are omitted, green's tiny approach/contact intermediate is removed, and later gripper-only openings merge into approaches. Raises before turns remain.

## Pickup without an LLM

```bash
python3 scripts/test_pickup_without_id4.py --execute
# Manual:
python3 scripts/test_pickup_without_id4.py --go
```

This uses the tested entry-point name, standard-library HTTP control, and the latest root `hardware/station_poses.json`. The normal mode makes no AI/camera calls. Older optional OpenCV flags remain separate from this workflow.

## Pickup with AI image checks

```bash
python3 llm_supervisor/pickup.py --execute
# Manual:
python3 llm_supervisor/pickup.py --go
```

Both pickup versions close their grippers with station-specific taught grip targets, lift, turn to the tray, lower, release, retract, turn back and return. The all-station run has **30 actual moves** after compaction. `--cube deposition` etc limits the run to one cube. A single-station run first establishes the base even if an all-station run can merge that station's start with the next approach.

Current calibration incorporated in both configurations:

- Raised base `{3:74, 5:-33.5, 6:-4}` for all stations, with their open gripper values. Old upright `{3:48,5:4,6:0}` is rejected.
- Etch contact **D3=76**, with raised/lift **D3=80** retained as approved.
- Deposition open approach is its exact pickup height, ID5=-56; no tiny intermediate -55.5 stop.
- Metrology/etch retain the distinct approach, lower and clearance raise movements.
- ID4/wheels excluded; ID3 >=30; no deferred universal D3<=48 cap applied.

The configurations are duplicated in `hardware/station_poses.json` and this folder's `station_poses.json`; tests compare complete movements to catch divergence. Shared `scripts/pickup_steps.py` removes unchanged commands. The AI runner imports this motion-only helper, not the non-LLM runner or any hardware SDK.

## AI observations and return behavior

| Check | Evidence | Effect |
| --- | --- | --- |
| Before grip | Recognizable full/partial target at the local pickup patch, including the bottom edge | Visible proceeds; absent/uncertain reverses and stops |
| After lift | Matching colored fragment remains close to the camera | `likely_carrying` proceeds; ambiguous/negative reverses and stops |
| After release at tray | Advisory target/support observation; no visible fingers required | Normal retract → turn back → start, even if observation is uncertain |

The weak carrying heuristic is **not confirmed gripping**. Color may remain visible even if an object is not attached. Missing targets or face/room-only views are uncertain; expected pose alone never proves success. Release observations never send the arm back to source pickup height.

Failed pre-release checks reverse acknowledged command waypoints to the entry/taught base and stop the whole run. A failed lift reverses lowering before reopening at source. No delivered-cube regrip occurs. In `--go` mode each reverse movement also requires go. Camera/API/robot transport errors, invalid outputs or interruption stop without blind reversal or retries. Reverse waypoints are commanded states, not measured trajectories.

For an approach-only test (one station required):

```bash
python3 llm_supervisor/pickup.py --cube deposition --approach-only --execute
```

Optional natural-language station order:

```bash
python3 llm_supervisor/pickup.py --execute --instruction "Collect red first, then green, then blue."
```

`--unavailable metrology` blocks that station; remaining unavailable work eventually stops. No LLM exception-diagnosis or recovery planner is implemented. Readiness, idle phone controls, an empty starting gripper, stable ID4 and the taught physical layout are operator preconditions.

## Camera-only API tools

```bash
python3 llm_supervisor/supervisor.py inspect-camera --live
python3 llm_supervisor/supervisor.py demo
```

The default offline demo is explicitly synthetic. Camera-only inspection reads one snapshot on port 8080 without movement. Color inventory is not station readiness. `plan --live --state example_state.json --instruction ...` gives advice only; that example state is synthetic and must reflect real conditions. `check-grip --live --station etch --before /path/before.jpg --after /path/after.jpg` remains a separate stronger saved-image advisory assessment, not the weak carrying check used by the motion runner.

Model: `gemini-3.5-flash-lite`. The local ignored `.env` loads automatically; an environment key takes precedence. No key prompt, training or SDK is needed. Explicit `--live` (advisory) or `--execute`/`--go` (AI motion) authorizes image requests. Keys and frames are not logged. Successful example API calls took roughly 1.4–2.4 seconds; no timing guarantee is implied.

Camera capture uses one JPEG/PNG capped at 5 MB and a five-second socket timeout. Provider HTTPS requests use `responseMimeType`/`responseJsonSchema`, with a 12-second socket timeout (not a total deadline). `--host` overrides the robot hostname; `--model` selects a compatible provider model. No continuous feed upload runs in the background.

[Official model](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite) · [Structured outputs](https://ai.google.dev/gemini-api/docs/generate-content/structured-output) · [Image inputs](https://ai.google.dev/gemini-api/docs/image-understanding)

## Findings, notes and tests

[Camera visibility findings](findings/camera_visibility/README.md) preserve the initial visibility limitation and photos. Subsequent bottom-edge detection succeeded, but full visual grip verification remains limited. [Calibration notes](calibration_notes.md) retain the operator's chronological changes, including notes-only photo poses that were not inserted into execution.

AI run logs in ignored `runs/` contain accepted commands, checkpoint assessments, request/sequence timings and outcomes. No images/credentials. Logs describe visual assessments, not measured physical grip success.

```bash
python3 -m unittest discover -s llm_supervisor -p 'test_*.py'
# Existing suite, including optional OpenCV tests:
.venv/bin/python -m unittest discover -s tests
```

**47 supervisor tests + 41 existing tests passed.** Tests mock network/motion, compare full AI/non-LLM dispatch, check manual/automatic flag semantics, exact latest targets, failed-check reversal and normal post-release return. The operator subsequently reported the corrected AI version worked on 2026-10-17. This is an operator-reported demonstration, not a measured success rate; final automated verification was offline.

## Camera timing correction

The first image checkpoint now happens at the **exact calibrated OPEN pickup-height pose immediately before Grip**, for every station. Metrology/etch first traverse the higher approach and lower to contact without calling AI. Green already approaches directly to that open contact pose. `--approach-only` now means move through the approach to open pickup height, inspect, then stop before closing; it does not stop high above the target. No motion targets were changed, only image-check timing.
