# Robot calibration and AI-assisted cube pickup

The project began with a fixed sequence for picking up cubes and placing them in a tray. After calibration produced a working transfer, Gemini image checks were added to assess whether the expected cube was visible before pickup and whether it appeared to remain with the arm after lifting. The final demonstration covered deposition, metrology and etch.

## 1. Calibrating the pickup positions

Calibration started by manually adjusting the arm until the gripper could reach each cube, pick it up and place it in the tray. Wheel movement was left out to keep the experiment focused on the arm. 

During these tests, **D4 was found to be unresponsive**. The other servo settings had to be adjusted around its position, with the assumption that D4 would stay in place. The robot could still complete a limited pickup task, but the damaged joint restricted its movement and made the setup less reliable.

The calibration records consisted of photographs showing the robot’s pose and screenshots showing the corresponding servo IDs and settings. These were sorted into the steps for each cube: approach, grip, lift, turn, lower and release. Further changes were recorded as testing continued.

The cubes represented three stations:

| Station | Cube | Location when facing the robot |
| --- | --- | --- |
| Deposition | Green | Center |
| Metrology | Blue/cyan | Right |
| Etch | Red | Left |

Labels and outlines on the box marked the pickup locations. The cubes had to be placed at these marks because the program repeated saved movements; it could not calculate a new pickup position if a cube moved elsewhere.

A calibration script then moved the arm through the positions with the gripper open. This allowed the cube locations to be checked and adjusted without running a full pickup. 

The saved positions worked for the demonstrated layout, but the arm was unstable and D4 remained unresponsive. Sending the same command therefore did not guarantee exactly the same physical position.

**The lack of servo-position readings created substantial additional software work.** The control interface used in the experiment did not report where the servos actually were. Supporting more independent movement would have required software to record the starting position, track every command and estimate the arm’s position after each move. The need for this became clear during AI integration. A fixed pickup routine could repeat saved commands, but calculating a new pickup or adjusting the arm required a dependable estimate of the arm and camera positions. Without it, an AI observation could not easily be translated into a physical movement.

Position tracking and a more complete physical calibration could have been investigated, but there was not enough time to design, implement and test them after the need became apparent. This was one of the project’s main difficulties and substantially restricted the AI features. The final implementation checked images around the existing pickup sequence instead of calculating new movements independently, and instead relying on hard coded positions.

## 2. Choosing a role for AI

Once the hard-coded transfer worked, several possible AI uses were considered:

| Possible AI use | Purpose |
| --- | --- |
| Cube detection | Check whether the expected cube is visible before pickup. |
| Pickup assessment | Compare images before and after lifting to assess whether the cube appears to be carried. |
| Release observation | Inspect the tray after release for evidence that the cube was deposited. |
| Instruction interpretation | Convert an instruction such as “collect red first” into a station order. |
| Station selection | Choose the next station using supplied availability information. |
| Exception explanation and recovery suggestions | Explain unexpected situations and suggest responses.  |

The strongest demonstrated addition was **using an image assessment to decide whether the taught pickup should proceed**. Carrying and release assessments were also recorded, but the camera could not support reliable physical confirmation. Optional instruction-based ordering and availability checks existed in the software; the saved physical trial described below used the normal three-station sequence.

The AI therefore acted as an image checker around the existing program. The local script retained the movement targets and recovery rules. Gemini did not calculate new joint targets or steer the arm continuously.

## 3. Connecting Gemini and recalibrating for the camera

The AI experiment was kept in a separate `llm_supervisor` folder so the working non-LLM pickup remained available. The setup used **Gemini 3.5 Flash-Lite** through HTTP requests. 

A second calibration problem appeared: **a position suitable for approaching a cube was not necessarily suitable for seeing it**. At the higher approach poses, the camera often showed the room, the box or the operator rather than the target. This caused the AI to reject a pickup before the gripper had reached the useful viewing position.

The wide-angle, fisheye-like view and the camera’s mounting relative to the gripper made framing difficult. The available evidence did not establish a calibrated lens-distortion model, but it clearly showed the practical problem: the camera could often see only a small part of the cube near the bottom edge, and could not reliably see the robot's own gripper around it. A complete view of the grip was unavailable in the tested setup; partial cube recognition was still possible.

The correction was to take the first image **at the calibrated open pickup position, immediately before closing the gripper**. 

The recognition rule also changed to accept a recognizable partial cube, rather than requiring the full object. Expected color alone was not intended to be sufficient: colored lighting, robot LEDs or an unrelated surface could resemble the target.

## 4. Missing position feedback and the limits of grip detection

The program could send servo targets, but **no reliable working method of reading the actual servo positions was established during the experiment**. A command acknowledgement showed that the robot service accepted the request. It did not show whether a servo reached the target or whether the gripper held anything.

That missing information prevented reliable calculation of the gripper’s actual location from the implemented system. The unresponsive D4 and mechanical instability added uncertainty. In theory, the arm, camera and work area could have been mapped and calibrated more completely, but that work was not completed within the available time. It would have required physical measurements and validation, not simply more saved target values.

A grip check based on the gripper stopping between fully open and fully closed was considered. Without established position or contact feedback, an extra closing command could not provide that measurement. Instead, the experiment relied on images. 

The original image rule required a cube visibly held between the fingers and clear of the surface. Because the camera could not reliably show that view, this rule repeatedly returned `uncertain`. It was replaced with a weaker before-and-after comparison: a matching cube fragment remaining near the camera after lifting could support a `likely_carrying` result.

Release had the same limitation. Sending an opening command did not establish that the cube had left the gripper. AI interpretation of the tray image provided an estimate, but the limited view could not always distinguish a released cube from one still attached.

Initially, an uncertain release triggered a return through the pickup sequence, even though the cube might already have been delivered. Release observations became **advisory** instead: after opening, the arm follows the normal retract, turn and return sequence. Failed pre-grip or carrying checks can reverse the acknowledged waypoints and stop. Connection failures and invalid responses stop in place.

A second camera could have provided an external view of the fingers, cube and tray. This was a proposed improvement, not a tested solution.

## 5. Result labels and collected evidence

Structured labels made the image responses usable by the program and preserved the reason for each decision:

| Label | Purpose |
| --- | --- |
| `visible`, `absent`, `uncertain` | Separate target recognition, apparent absence and insufficient evidence before gripping |
| `full_cube`, `recognizable_partial_cube`, `insufficient` | Identify whether recognition relied on a complete cube, a fragment or inadequate evidence |
| `likely_carrying`, `not_carrying`, `uncertain` | Record the after-lift assessment without claiming verified grip feedback |
| `likely_released`, `target_still_visible`, `uncertain` | Describe the release image; visibility alone does not establish attachment |
| `weak_visual_color_continuity_not_confirmed_grip` | Explicitly identify the carrying check as a visual estimate |

Movement labels such as pickup, lift and release connected each set of servo targets to its intended action. The first camera checkpoint retained the historical JSON name `approach`, although its final position was immediately before gripping at pickup height.

The AI runner collected JSONL records containing accepted movement targets, station and checkpoint names, model results, written evidence, API timings and cycle outcomes. Camera frames were sent for interpretation but were not stored in these runtime logs. The separate photo records preserved the calibration evidence. Credentials remained excluded from Git.

## 6. Results from the saved runs

The records show both useful recognition and failed checks. The sequence below explains why each change was made; these development attempts used changing rules and are not a controlled accuracy benchmark.

| Saved run, UTC filename prefix | Recorded result | What it showed |
| --- | --- | --- |
| `000857` | Green approach `uncertain`, 1.377 s | Framing/distortion prevented recognition |
| `001247` | Green approach `absent`, 1.487 s; red object reported | Expected station color mattered |
| `001431` | Green partial cube `visible`, 1.635 s | A bottom-edge fragment could be recognized |
| `001509` | Approach passed; grip `uncertain` | Requiring visible fingers exceeded the camera’s view |
| `002638` | Carrying passed; release `uncertain`; reversed | Release failure policy needed to change |
| `002931` | Green visibility, carrying and release passed; normal return | Complete single-station AI cycle |
| `003211` and `005947` | Green completed; metrology check failed at high approach | First image was being taken at the wrong pose |
| `010507` | All three cycles completed after checkpoint correction | Complete three-station AI run |

The final file is `20261018T010507959894Z.jsonl`: **October 17 at approximately 6:05 PM Pacific**, expressed as October 18 in UTC. It contains **30 accepted movements, nine image checkpoints and three station-completion records**, with no `stopped` event. The recorded interval from first accepted movement to final completion is approximately **38.23 seconds**; this excludes any time before the first acknowledgement.

| Station | Before grip | After lift | Release observation | Recorded cycle time |
| --- | --- | --- | --- | --- |
| deposition | `visible` | `likely_carrying` | `likely_released` | 12.929 s |
| metrology | `visible` | `likely_carrying` | `target_still_visible` | 13.398 s |
| etch | `visible` | `likely_carrying` | `likely_released` | 12.657 s |

All nine model calls in that run took between **1.324 and 2.053 seconds**, totaling **14.349 seconds** of reported API time. API latency is additional to movement and settling. Metrology’s `target_still_visible` release label did not prove it was still held; its evidence described a cube resting in the tray, and the advisory policy allowed normal return.

### Actual JSON evidence

These are exact selected event objects from the final saved run, not reconstructed model responses. They show command acceptance, partial recognition, the weaker carrying assessment, release uncertainty terminology and completion.

```json
{
  "time_utc": "2026-10-18T01:05:08.716080+00:00",
  "type": "move_accepted",
  "station": "deposition",
  "step": 1,
  "targets": {
    "1": -30,
    "3": 74,
    "5": -33.5,
    "6": -4
  },
  "duration_ms": 500
}
```

```json
{
  "time_utc": "2026-10-18T01:05:11.126261+00:00",
  "type": "checkpoint",
  "station": "deposition",
  "checkpoint": "approach",
  "result": {
    "status": "visible",
    "pickup_area_visible": true,
    "appearance_consistent": true,
    "evidence_type": "recognizable_partial_cube",
    "evidence": "The top face of the green cube is clearly visible at the bottom of the frame, showing the expected green color and geometry."
  },
  "api_elapsed_seconds": 1.473
}
```

```json
{
  "time_utc": "2026-10-18T01:05:27.927263+00:00",
  "type": "checkpoint",
  "station": "metrology",
  "checkpoint": "grip",
  "result": {
    "status": "likely_carrying",
    "target_color_visible_near_camera": true,
    "appearance_matches_before": true,
    "clearly_left_on_source": false,
    "evidence": "Image 1 shows the blue target cube near the bottom edge of the frame before gripping. Image 2 shows a matching blue target-colored object fragment in the same relative position near the bottom edge of the frame after the lift, with no evidence that the object was left behind on the source.",
    "suggested_action": "continue",
    "verification_type": "weak_visual_color_continuity_not_confirmed_grip"
  },
  "api_elapsed_seconds": 2.053
}
```

```json
{
  "time_utc": "2026-10-18T01:05:31.871894+00:00",
  "type": "checkpoint",
  "station": "metrology",
  "checkpoint": "release",
  "result": {
    "status": "target_still_visible",
    "evidence": "The blue-green target cube is visible resting within the tray area."
  },
  "api_elapsed_seconds": 1.496
}
```

```json
{
  "time_utc": "2026-10-18T01:05:46.946605+00:00",
  "type": "station_finished",
  "station": "etch",
  "outcome": "cycle_completed_release_observation_likely_released",
  "elapsed_seconds": 12.657
}
```

### AI versus no AI

| Aspect | Calibrated pickup without LLM | Pickup with AI |
| --- | --- | --- |
| Motion | Same taught sequence; 30 movements across all stations | Same taught sequence; 30 movements |
| Physical feedback | No verified servo-state or grip feedback | Same limitation |
| Camera interpretation | None in normal execution | Three image checkpoints per station |
| Missing-object decision | Continues the taught sequence unless another execution error occurs | Failed pre-grip/carry assessment reverses and stops |
| Release | Opens and returns; operator verifies | Opens, records advisory assessment and returns |
| Runtime record | Terminal target/acceptance messages | JSONL accepted movements, assessments, timings and outcomes |
| Demonstrated result | Transfer success was reported by the operator | Final saved all-station run completed, with operator-reported success |

There is no equivalent saved non-AI JSONL trial in these records. The following is an **illustrative command payload generated by the non-AI interface**, not a fabricated execution log:

```json
{
  "jsonrpc": "2.0",
  "method": "SetPWMServo",
  "params": [500, 1, -30, 3, 74, 5, -33.5, 6, -4],
  "id": 1
}
```

This requests a pose. Even an accepted response would not establish that the robot reached it. No matched, repeated AI/non-AI trials are available to calculate a success-rate difference or measured time penalty. The results establish a working demonstration and additional observations, not that AI improved pickup accuracy by a measured amount.

## 7. Outcome and remaining work

The non-LLM version demonstrated a calibrated transfer sequence. The AI version added decisions based on camera observations, including stopping a pickup when the expected cube was missing or could not be recognized. The final saved run completed all three stations with nine image checkpoints.

The difference was therefore **a fixed movement routine versus that same routine with image-based conditions for continuing**. The AI version did not establish autonomous grasp planning, measured position accuracy or confirmed grip sensing. The missing joint-position data, unstable hardware and restricted camera view limited those possibilities.

Offline verification passed **41 project tests and 47 supervisor tests**, covering matching motion sequences, approved targets, excluded ID4, checkpoint timing, manual/automatic flags and return behavior. These were software checks with mocked hardware and API calls, not physical reliability measurements. Scripts were documented, PyDoc was generated, obsolete experimental files were removed and local commits separated the implementation stages.

The remaining experimental gap is a repeated comparison under the same conditions: cube present, cube missing, wrong color and unsuccessful grip. Recording the physical outcome alongside the AI label would show how often the added check helped and how often it stopped a valid pickup. The existing development logs used changing rules, so they cannot establish that success rate.

Stabilizing or replacing D4, establishing usable servo feedback and testing a second camera would address the main hardware limitations. A measured arm-and-camera calibration could then support investigation of pickups beyond the taught locations.

### Supporting records

- [Working pickup guide](working_pickup.md): commands and final targets.
- [Calibration history](../llm_supervisor/calibration_notes.md): recorded pose changes and observations.
- [Supervisor guide](../llm_supervisor/README.md): API setup and checkpoint behavior.
- [Camera findings](../llm_supervisor/findings/camera_visibility/README.md): external photographs and onboard-view limitations.
- Photo records: [deposition](poses/deposition/README.md), [metrology](poses/metrology/README.md), [etch](poses/etch/README.md).
- [Dimensional feasibility](robot-model/dimensional-feasibility.md): available geometry and missing measurements.
- [Final three-station JSONL run](../llm_supervisor/runs/20261018T010507959894Z.jsonl): local runtime evidence, excluded from Git. Selected events are reproduced above.
