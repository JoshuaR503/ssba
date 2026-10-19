# Robot dimensions and pose prediction — preliminary report

This report establishes what can be modeled from the available evidence. It is not a calibrated simulation or a measured accuracy result. No motion commands or executable changes were made.

## Dimensions and evidence

| Quantity | Value | Evidence and limitation |
| --- | --- | --- |
| Overall product dimensions | 185 × 162 × 343 mm | Manufacturer nominal specification; overall height depends on pose, and these are not a wheel contact polygon or a chassis CAD drawing. |
| Product mass | 1100 g | Manufacturer nominal figure; actual cables, controller, battery and payload configuration need verification. |
| L1 in inverse kinematics | 80 mm | Active numeric constant in the downloaded robot source. |
| L1 used by arm wrapper | 93 mm | Wrapper adds 13 mm to L1. Coordinate origin must be matched before interpreting this as height above the table. |
| L2 | 65 mm | Active source constant, joint-to-joint model length. |
| L3 | 62 mm | Active source constant, joint-to-joint model length. |
| L4 for gripper version | 100 mm | Active source constant to modeled gripper endpoint; actual cube contact point depends on opening and placement. |
| L2 + L3 + L4 | 227 mm | Sum of model lengths; theoretical straight-chain length, not guaranteed usable horizontal reach. |

Manufacturer source: [Hiwonder MasterPi specifications](https://www.hiwonder.com/products/masterpi), checked 2026-10-17.

Local sources: `robot-reference/MasterPi/masterpi_sdk/kinematics_sdk/kinematics/inversekinematics.py` and `arm_move_ik.py`. Some source comments mention lengths inconsistent with the active constants. The table uses the executed numeric constants; these still need physical verification.

Exact dimensions of every bracket, wheel contact location, gripper opening, camera-to-tool transform, cube, tray and station surface have not been established. Photographs with changing viewpoints do not provide those measurements by themselves.

## What the recorded poses establish

- Deposition: green cube at the center, demonstrated grip, lift, turn, lower and release. Displayed ID4 is 20.
- Metrology: blue/cyan cube at the right, demonstrated grip and transfer. Exact start and separate pre-turn lift controls are missing. Displayed ID4 is 4.
- Etch: red cube at the left, all seven stages have control screenshots. Displayed ID4 is 0. Final photos show red supported above the other cubes in the tray.

These batches are separate demonstrations with different displayed ID4 settings. Their geometry cannot be treated as one fixed-elbow calibration without verifying the actual joint position. ID4 commands remain excluded. All documented ID3 settings in these three batches meet the minimum 30 constraint; that alone does not establish clearance or stability during transitions.

## What a model can predict

With measured link lengths, physical joint zeros/signs, and a fixed or observed ID4 angle, forward kinematics can calculate joint centers, tool position and orientation for each saved command. A dimensioned side/top view can compare the predicted pose to each photo. Interpolating between commands allows approximate swept-volume clearance checks against the box, tray, chassis and other cubes.

The app numbers must first be mapped through the command-to-pulse conversion and calibration offsets to physical joint angles. Treating the displayed numbers directly as geometric angles would produce unsupported coordinates. A successful API response establishes command acceptance, not measured joint position.

A geometric model cannot by itself predict grip friction, gear backlash, load-induced sag, servo stalls, oscillation or tipping under acceleration. Quantitative tipping analysis also needs wheel support locations, component masses/centers of mass, payload mass and a motion profile. Reducing a move from 2000 to 500 ms can increase dynamic loading; endpoint photos cannot characterize that transition.

## ID4 uncertainty sensitivity

For an ideal revolute joint with a downstream tool point at distance r, an angle difference Δθ moves that point by 2r sin(|Δθ|/2). Using the source-model maximum downstream length L3 + L4 = 162 mm:

| Hypothetical physical ID4 angle difference | Maximum endpoint displacement in this ideal chain |
| --- | ---: |
| 1 degree | 2.8 mm |
| 5 degrees | 14.1 mm |
| 10 degrees | 28.2 mm |

These are geometric sensitivity estimates, not measured errors, confidence intervals, or a claim that app units equal physical degrees. Tool orientation also changes. A loose joint can therefore matter at cube scale even when its numerical change looks small. Model it as an uncertain joint angle, not automatically as a rigid zero-angle link.

## Accuracy assessment and minimum calibration

There is currently no defensible millimeter accuracy or pickup-success percentage. The photos show that individual demonstrated poses can work; they do not measure repeatability.

To establish accuracy:

1. Measure joint-center distances, gripper contact geometry, cube edge length, station height/position and tray geometry in a common robot coordinate frame.
2. Establish physical joint zeros/signs and actual ID4 angle/range without sending ID4 commands. Fix the camera viewpoint or calibrate the onboard camera-to-arm transform.
3. Fit the model to some measured poses and reserve others for independent validation.
4. Repeat pickups from the same layout and report endpoint error, repeatability, minimum observed clearance and pickup success separately. Report sample counts, loads and movement times.

A useful deliverable is therefore feasible: dimensioned nominal geometry, pose-by-pose predicted views, uncertainty envelopes for ID4, and a comparison against measured validation poses. Exact physical outcomes remain unverified until those measurements exist.

Related evidence: [deposition](../poses/deposition/README.md), [metrology](../poses/metrology/README.md), [etch](../poses/etch/README.md).
