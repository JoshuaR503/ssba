# Working pickup — operator guide

The operator reported the initial three-station non-LLM transfer worked, then completed physical calibration iterations and reported the corrected AI version worked on 2026-10-17. These are operator-reported demonstrations, not measured repeatability, grip accuracy or certification of project requirements. Current AI and non-LLM target sequences are regression-tested for equality.

## Commands from the Mac

```bash
cd "/Users/joshua/Desktop/ai-based wafer"
# No LLM:
python3 scripts/test_pickup_without_id4.py --execute
# With AI image checks:
python3 llm_supervisor/pickup.py --execute
# Placement guide, gripper stays open:
python3 llm_supervisor/calibration.py --go
```

Across these entry points, **`--execute` runs automatically** and **`--go` executes step by step**, requiring literal go before every movement. No flag previews only. Calibration with `--execute` passes through pickup height without holding. There is no startup countdown. Every move requests **500 ms**, followed by 150 ms settling; network/API time is additional. Stop and restart an already-running process to load source/configuration changes.

`--cube deposition`, `--cube metrology`, or `--cube etch` selects one station; default `all` runs green → blue/cyan → red. `--host` overrides raspberrypi.local. The non-LLM `--step` legacy alias remains available. Normal non-LLM execution uses the standard library only. Both call the existing Raspberry Pi vendor JSON-RPC service on port 9030, so run these commands on the Mac; no script upload is necessary. The Pi must be reachable and the vendor service already running.

## Current motion and placement

Start with empty gripper, cubes at the taught source positions, ready tray, mechanically stable ID4 and idle competing controls. In the front-view photos: green/deposition is center, blue/metrology right, red/etch left. The routine moves through open pickup position → close → lift → turn to tray → lower → release → retract empty → turn back → raised base. Distinct intermediate approaches remain where useful.

All three pickup cycles total **30 actual movements**. The shared `scripts/pickup_steps.py` removes unchanged commands and merges later gripper-only starts into approaches. Calibration totals **13 actual movements**, omitting grip and tray transfer, while keeping clearance raises. Green's old 0.5-unit approach/contact intermediate is removed. The first selected station always establishes the base from an unknown initial pose.

Common arm base: `{3:74,5:-33.5,6:-4}`. Gripper is opened to the selected station's value. The old upright `{3:48,5:4,6:0}` is explicitly rejected by both movement validators. ID3 >=30 always; a universal upper bound of 48 was discussed but deferred and is **not** enforced. Current approved poses deliberately exceed 48. ID4 and wheel commands are never included.

Stored reference values below are before ID5 trim; keys are servo IDs, not calibrated Cartesian coordinates or measured angles.

| Station | Pickup | Raised | Tray lower | Open / grip / release |
| --- | --- | --- | --- | --- |
| deposition (green) | 3:74, 5:-56, 6:-4 | 3:74, 5:-34, 6:-4 | 3:90, 5:-54, 6:90 | -30 / -2 / -24 |
| metrology (blue/cyan) | 3:70, 5:-60, 6:-46 | 3:70, 5:-32, 6:-46 | 3:90, 5:-70, 6:90 | -40 / -2 / -36 |
| etch (red) | 3:76, 5:-60, 6:32 | 3:80, 5:-30, 6:32 | 3:90, 5:-58, 6:90 | -42 / 6 / -44 |

Etch contact D3=76 and raised D3=80 are both retained as approved. ID5 +0.5 command-unit trim applies to raised/retract positions and distinct metrology/etch approaches. Green approaches its exact pickup-height pose. This is not a measured 0.5 mm or percentage height change.

Historical photos show ID4=20/4/0 in the three demonstrations; those values are provenance only, never commands. Metrology's original separate lift/start settings and return paths were derived; subsequent operator calibration selected the current shared base and etch contact change. See the source photo records and chronological calibration notes for details.

## AI differences

See [supervisor guide](../llm_supervisor/README.md). Image checks occur **at exact open pickup height immediately before closing**, after lift, and after release. The first check is not at the higher approach pose. Recognizable partial target fragments near the bottom edge can pass the pre-grip check. After lift the weaker color-continuity judgment is logged as **likely carrying**, not confirmed grip. Release is advisory, requires no finger visibility and continues the normal empty-arm return even if uncertain.

Failed pre-grip/carry image checks reverse acknowledged waypoints to start, then stop the run before later stations. Reversal lowers back to source before reopening if the lift check failed. After release the runner never reverses through source pickup height or regrips the delivered cube. Camera/API/robot transport failures, invalid output and Ctrl+C stop without blind return or retry. Step mode also prompts before reverse commands. No servo readback grip detection, extra squeezing, arbitrary model angles or LLM exception planner is implemented.

Non-LLM execution simply performs the target sequence. It stops on rejection, connection error or interruption without automatic recovery. A vendor result list starting with true acknowledges a command; it does not prove physical motion or a grasp. Ctrl+C stops future dispatch, not an already-sent movement.

## Configuration and dependencies

- `hardware/station_poses.json`: active non-LLM configuration; historical_pose_set is ignored for execution.
- `llm_supervisor/station_poses.json`: active AI copy; tests compare all dispatched targets against the non-LLM runner.
- `scripts/pickup_steps.py`: shared motion-only compaction, no network.
- `scripts/cube_vision.py`: retained optional legacy OpenCV known-zone selector, separate from cloud AI.
- `requirements-vision.txt`: optional OpenCV/NumPy dependencies for the legacy selector and its tests.

The baseline retains `--configure-vision`, `--vision`, `--vision-config`, `--distances-cm` and `--at-observation-pose`. Old local calibration/output was discarded; regenerate at the current observation pose with the robot already positioned there before using those optional flags. Camera calibration is local generated data, not part of this commit. Do not reuse the obsolete location labels or camera zones. The LLM setup uses its local ignored `.env` automatically; no credentials are committed.

## Evidence, limitations and monitoring

[Deposition](poses/deposition/README.md), [metrology](poses/metrology/README.md), [etch](poses/etch/README.md) and [historical poses](poses/raised-pose.md) retain source images/values, not executable instructions. [Camera findings](../llm_supervisor/findings/camera_visibility/README.md) document framing limitations. [Dimensional feasibility](robot-model/dimensional-feasibility.md) separates nominal geometry from unmeasured accuracy. The vendor source snapshot remains a local ignored reference, not a runtime dependency.

The read-only `scripts/watch_cpu_temperature.py` can be copied to the Pi and run with `ssh -t pi@raspberrypi.local 'python3 ~/watch_cpu_temperature.py'`. It reads CPU temperature, not servo/wiring/battery temperatures. A normal CPU reading cannot dismiss a burnt smell. Temperature monitoring is optional and never modifies motor state.

## Verification and PyDoc

```bash
.venv/bin/python -m unittest discover -s tests
python3 -m unittest discover -s llm_supervisor -p 'test_*.py'
PYTHONPATH=scripts python3 -m pydoc test_pickup_without_id4
```

The final offline suites have **41 existing tests + 47 supervisor tests**. They mock HTTP/camera/motion and check manual/automatic flags, full sequence equality, exact approved targets, no ID4, ID3 bounds, banned base rejection, checkpoint timing, reverse ordering and normal post-release return. No final cleanup test sent a physical command or provider request.

Generated [runner PyDoc](pydoc/test_pickup_without_id4.html), [motion helper PyDoc](pydoc/pickup_steps.html), [optional OpenCV PyDoc](pydoc/cube_vision.html) and [AI/calibration PyDoc](../llm_supervisor/pydoc/index.md) document the implementation. Every production function has a docstring. Regenerate HTML with `pydoc -w` using scripts/llm_supervisor in PYTHONPATH, from the desired documentation directory. Importing these modules for PyDoc sends no commands.
