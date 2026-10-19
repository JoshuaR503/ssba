# Calibration notes

## 2026-10-17 — metrology camera pose

Operator-provided position to use **before taking the metrology picture**:

```text
Targets: {3: 70, 5: -31.5, 6: -46, 1: -40} | 500 ms
```

- ID1=-40: gripper open. This is a pre-photo observation pose, not a grip command.
- ID3=70, ID5=-31.5, ID6=-46: retain exactly as supplied.
- ID4 is omitted and remains excluded.
- Record only for now; do not change executable poses, checkpoint timing or the working baseline until the later calibration trial.
- This differs from the current metrology open approach (ID3=70, ID5=-47.5, ID6=-46, ID1=-40); the requested photo pose uses the raised ID5 value -31.5 while keeping the gripper open.

## Deferred D3 upper-limit request

The operator prefers D3=48 in the earlier start view `{1:-40, 3:48, 5:4, 6:0}` because that camera view does not show their face, and asked that D3 not go above 48. They explicitly deferred trying this change. Record the proposed maximum **48** alongside the existing minimum **30**, but do not claim the new maximum is enforced.

The newly supplied metrology photo pose explicitly has **D3=70**, which conflicts with a universal D3<=48 limit. Preserve both instructions as separate pending calibration notes; resolve the intended per-stage scope before implementing a global cap. Do not silently clamp 70 to 48. Existing pickup poses also exceed 48.

## 2026-10-17 — etch camera pose

Operator-provided position to use **before taking the etch picture**:

```text
Targets: {3: 80, 5: -29.5, 6: 32, 1: -42} | 500 ms
```

- Preserve ID3=80, ID5=-29.5, ID6=32 and open gripper ID1=-42 exactly.
- ID4 remains omitted/excluded.
- This is the raised etch arm position with the gripper open, not the contact pickup position. Relative to the existing trimmed open approach (ID3=76, ID5=-49.5, ID6=32, ID1=-42), ID3 and ID5 change; arm-base ID6 remains 32.
- Operator says the overall sequence was otherwise fine and wants the stated pre-photo positioning used. Treat this as a checkpoint-position note, not authorization to rewrite other pickup/lift/drop targets.
- No executable target was changed in this note-taking turn. The deferred universal D3<=48 preference also conflicts with this explicit D3=80 photo pose; do not silently clamp it.

## Clarification — notes only, calibration hold at actual pickup

The operator clarified that the metrology/etch pre-photo positions above are to be stored only. Do not insert those positions into the AI runner or move its photo checkpoints based on those notes. The calibration helper should travel through start/approach without prompting, then pause at the original taught pickup-height pose with the gripper OPEN, just before gripping. Enter retracts and advances; q stops in place. No gripping command, startup countdown or new D3 cap is added.

## Latest calibration trial — etch D3=76 and per-move go

Operator approved testing etch contact-height D3=76 instead of 80 in the calibration helper only. Etch contact is now `{3:76, 5:-60, 6:32, 1:-42}`; other reference targets and pickup execution remain unchanged. Every calibration move now requires the literal `go`; blank input stops without sending the next move. This supersedes the earlier pickup-only pause preference for calibration. Movement duration remains 500 ms; no startup countdown.

## Latest deposition calibration base

Operator selected deposition step 5 (“Turn empty arm back toward start”) as the new base. Its printed `{6:-4, 1:-30}` is a partial command; the preceding raised pose supplies ID3=74 and ID5=-33.5. Therefore the full deposition calibration start/return pose is **`{1:-30, 3:74, 5:-33.5, 6:-4}`**, at 500 ms. Applies to deposition calibration only in this change; other stations and both pickup runners are unchanged. This explicit selection uses D3=74; the previously discussed universal D3<=48 limit remains deferred, not enforced.

## Upright calibration base removed for every station

The operator reported their face visible after metrology step 1, `{1:-40,3:48,5:4,6:0}`. In the supplied terminal output, step 2 was printed but had not yet been approved, so step 1 is the last acknowledged physical command. Calibration now uses one raised arm base `{3:74,5:-33.5,6:-4}` for all stations, with the station-specific open gripper target. This replaces the former metrology/etch upright start/return and supersedes the deposition-only scope above. The camera framing of the replacement for all stations has not been independently verified. Other approach/contact/raised poses remain unchanged; this is not a universal D3 cap or guarantee that faces can never enter the camera. Both pickup runners are unchanged. Restart calibration to load it.

## Banned upright pose — applies to active pickup configurations too

Operator reiterated that `{3:48,5:4,6:0}` is banned. Both active station configuration files now use the chosen raised arm base `{3:74,5:-33.5,6:-4}` at every start/return, with each station's open ID1. Both motion payload validators explicitly reject the full banned pose. Earlier “pickup runners unchanged” notes are superseded for start/return only. Historical source photo data is retained as history, not an active movement instruction. Other pickup/approach/lift/drop targets remain unchanged.

## Calibration duplicate removal

Operator confirmed etch raised D3=80 is fine and the jerk went away. Preserve it. Calibration now drops exact commanded-state no-ops: deposition's former turn-back step 5 and final-base step 6 repeat the raised base already reached at step 4. When running all stations, metrology/etch starts keep only the necessary gripper opening change at the shared base. Their arm return steps remain because D3/D5/base genuinely change. Deposition's 0.5 ID5 approach/contact separation remains intact. Calibration has 16 actual moves total (4+6+6), each requiring go, with no startup wait. Pickup runners are unchanged.

## Latest approved simplification

Removed green's 0.5 ID5 approach/contact intermediate step and merged metrology/etch gripper-only openings into their following approach commands. Retained clearance raises and distinct arm turns/returns. All-station plan: 13 moves. New `--go` enables automatic execution with no prompts/holds; `--execute` keeps manual go per move. No startup countdown.
