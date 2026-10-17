#!/usr/bin/env python3
"""Run the photo-taught MasterPi three-station transfer prototype.

Run from the Mac project directory. With no arguments, print the complete plan
without sending movement commands. ``--execute`` transfers green/deposition,
blue/metrology, then red/etch into the tray and returns the empty arm after each
transfer. ``--cube`` selects one station; ``--step`` enables optional prompts.

Every movement requests 500 ms, followed by 150 ms settling. A five-second
countdown precedes automatic execution. Targets come from the version-matched
``hardware/station_poses.json`` file relative to this script, not the shell cwd.
ID5 receives +0.5 command units on approach, lift, and empty-arm retract only.

Only servo IDs 1 (gripper), 3 (wrist pitch), 5 (shoulder), and 6 (arm base) may
be commanded. ID3 must remain >=30. ID4 and wheel commands are excluded; omission
does not electrically disable or mechanically stabilize the damaged ID4 joint.

Optional vision selects one known station from manually calibrated camera zones;
it is taught-pose playback, not arbitrary-position visual servoing or an AI API.
That mode lazily imports ``cube_vision`` and requires OpenCV/NumPy. Normal
preview and execution use only the Python standard library.

The user reported the three-station run worked on 2026-10-17. This is a tested
prototype baseline, not a measured accuracy, repeatability, or program-requirement
certification. Source poses contain differing displayed ID4 values; the metrology
pre-turn lift and empty-arm returns were derived. API acceptance does not prove
a grasp or release. There is no joint feedback or automatic grasp verification.

Network commands use HTTP JSON-RPC ``SetPWMServo`` on port 9030. Rejections and
connection failures stop future commands without retries or recovery movements.
Ctrl+C stops dispatch, but a previously sent command may finish. Never enable
competing phone/vendor behaviors during a transfer.

Examples::

    python3 scripts/test_pickup_without_id4.py
    python3 scripts/test_pickup_without_id4.py --execute
    python3 scripts/test_pickup_without_id4.py --cube etch --execute

See ``docs/working_pickup.md`` for setup, pose tables, CLI options, and tests.
"""
import argparse
import json
import math
import os
from pathlib import Path
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

ALLOWED = {1, 3, 5, 6}
MIN_ID3 = 30  # User-observed tip/backward-lean boundary; never command below this.
DEFAULT_DURATION_MS = 500
SETTLE_SECONDS = 0.15
POSE_SET = 'station-photos-v6'
POSE_FILE = Path(__file__).resolve().parents[1] / 'hardware/station_poses.json'
# Load only the active station map; historical_pose_set is provenance, never motion.
POSE_DATA = json.loads(POSE_FILE.read_text())
if POSE_DATA.get('pose_set') != POSE_SET:
    raise ValueError('Station pose file does not match this script')
CUBES = POSE_DATA['stations']
BASE_POSE = CUBES['etch']['start']
LIFT_TRIM = POSE_DATA['lift_trim']['command_delta']


def duration_for(label):
    """Return the fixed 500 ms duration for every movement label.

    ``label`` is retained for the existing plan/printing interface; it does not
    select a different speed. Settling time is applied separately by ``main``."""
    return DEFAULT_DURATION_MS


def joint_pose(raw):
    """Convert a JSON joint-target mapping to integer servo IDs.

    Return a new dictionary so trimming a planned pose does not mutate the
    reference configuration. Target validation is performed by ``payload``."""
    return {int(joint): value for joint, value in raw.items()}


def build_steps(selection='all'):
    """Build and validate the ordered movement plan without network access.

    Args:
        selection: ``all``, ``deposition``, ``metrology``, or ``etch``.

    Returns:
        List of (human-readable label, joint-target dictionary) tuples: eleven
        per station, thirty-three for all stations. Unspecified joints retain
        their previous target; ID4 is never inserted.

    Raises:
        ValueError: Unknown station or any invalid target anywhere in the plan.

    Source/contact poses are copied. Clearance trim applies only to approach,
    lift and retract. Each cycle releases before retracting, turns the empty arm
    back, and returns to its start. Metrology's pre-turn lift is explicitly
    derived from its later raised turn pose, retaining the pickup base angle."""
    if selection != 'all' and selection not in CUBES:
        raise ValueError('Use deposition, metrology, or etch; old location labels are obsolete')
    steps = []
    for name in (CUBES if selection == 'all' else [selection]):
        cube = CUBES[name]
        base = joint_pose(cube['start'])
        pickup = joint_pose(cube['pickup'])
        raised = joint_pose(cube['raised'])
        raised[5] += LIFT_TRIM
        approach = joint_pose(cube['approach'])
        approach[5] += LIFT_TRIM
        approach[1] = cube['open']
        destination = joint_pose(cube['destination'])
        # Do not open/close during retract; retain station-specific release.
        retracted = {3: raised[3], 5: raised[5]}
        cycle = [
            ('Base/start, empty gripper (derived transition)', base.copy()),
            ('Open approach with +0.5 ID5 clearance trim', approach),
            ('Lower to recorded pickup pose', pickup),
            ('Grip cube', {1: cube['grip']}),
            ('Lift with +0.5 ID5 clearance trim' + (' (derived pre-turn pose)' if name == 'metrology' else ''), raised),
            ('Turn arm base to tray', {6: destination[6]}),
            ('Lower at station-specific tray pose', {3: destination[3], 5: destination[5]}),
            ('Release at destination', {1: cube['release']}),
            ('Retract empty arm with +0.5 ID5 clearance trim (derived transition)', retracted),
            ('Turn empty arm toward start (derived transition)', {6: base[6]}),
            ('Return empty arm to base/start (derived transition)', base.copy()),
        ]
        steps.extend((f'[{name.upper()} / {cube["color"]}] {label}', joints) for label, joints in cycle)
    # Reject the entire plan before any motion, including later stations.
    for number, (_, joints) in enumerate(steps, 1):
        payload(joints, number)
    return steps


def color(text, code):
    """Return ANSI-colored terminal text, respecting ``NO_COLOR``.

    Redirected output remains plain text; ``code`` is an ANSI SGR parameter."""
    if sys.stdout.isatty() and 'NO_COLOR' not in os.environ:
        return f'\033[{code}m{text}\033[0m'
    return text


def payload(joints, request_id, duration_ms=DEFAULT_DURATION_MS):
    """Validate targets and construct one vendor JSON-RPC request.

    Args:
        joints: Nonempty mapping of allowed integer servo IDs to app command
            values in [-90, 90]; ID3 additionally requires a value >=30.
        request_id: Request identifier echoed by the JSON-RPC service.
        duration_ms: Must be 500; this baseline does not permit other durations.

    Returns:
        A JSON-serializable ``SetPWMServo`` request whose params alternate
        servo ID and target after the duration. This function sends nothing.

    Raises:
        ValueError: Disallowed ID, nonfinite/out-of-range target, or duration.

    App values are not calibrated Cartesian coordinates or measured angles."""
    if not joints or not set(joints) <= ALLOWED:
        raise ValueError('Only IDs 1, 3, 5, 6 allowed')
    if duration_ms != DEFAULT_DURATION_MS:
        raise ValueError('Unsupported movement duration')
    params = [duration_ms]
    for joint, target in joints.items():
        if not isinstance(target, (int, float)) or not math.isfinite(target):
            raise ValueError('Joint targets must be finite numbers')
        if joint == 3 and target < MIN_ID3:
            raise ValueError(f'ID3 must never be below {MIN_ID3}; requested {target}')
        if not -90 <= target <= 90:
            raise ValueError('Invalid taught target')
        params.extend([joint, target])
    return {'jsonrpc': '2.0', 'method': 'SetPWMServo', 'params': params, 'id': request_id}


def main():
    """Parse CLI options, preview the plan, and optionally dispatch it once.

    Return 0 on preview/completion/user step cancellation and 1 on caught
    execution or vision errors/interruption. Argparse handles usage errors.
    The entire plan is validated before the first request. Automatic mode has
    one countdown, not per-step confirmations. Requests are sequential; each
    accepted request is followed by its duration plus a settling interval.

    Optional vision reads snapshots even in preview and rechecks the locked
    target after the countdown before movement. No automatic retry, release,
    or return is sent after an execution error."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--step', action='store_true', help='Optionally ask before each movement')
    parser.add_argument('--host', default='raspberrypi.local')
    parser.add_argument('--cube', choices=['all', *CUBES], default='all', help='All three cubes by default; release at destination, return empty arm to base')
    parser.add_argument('--vision', action='store_true', help='Select ONE stable visible cube from calibrated zones; no AI API')
    parser.add_argument('--configure-vision', action='store_true', help='Read camera and draw pickup zones; no motion')
    parser.add_argument('--distances-cm', type=float, nargs=3, metavar=('DEPOSITION', 'METROLOGY', 'ETCH'), help='Calibration distances supplied upfront; avoids switching back to Terminal')
    parser.add_argument('--at-observation-pose', action='store_true', help='Confirm arm is already at recorded base observation pose, with unchanged layout')
    parser.add_argument('--vision-config', default=str(Path(__file__).resolve().parents[1] / 'hardware/camera_pickup_zones.json'))
    args = parser.parse_args()
    if args.vision or args.configure_vision:
        if not args.at_observation_pose:
            parser.error('Camera is arm-mounted: set the recorded base observation pose, then provide --at-observation-pose. No motion sent.')
        from cube_vision import configure, select
        try:
            if args.configure_vision:
                configure(args.host, args.vision_config, args.distances_cm, observation_pose=BASE_POSE, pose_set=POSE_SET, stations=list(CUBES))
                return 0
            target = select(args.host, args.vision_config, observation_pose=BASE_POSE, pose_set=POSE_SET, stations=list(CUBES))
            args.cube = target['cube']
        except (OSError, ValueError, RuntimeError) as exc:
            print(f'VISION STOPPED: {exc}')
            return 1
    steps = build_steps(args.cube)
    print(color(f'ARM TRANSFER TEST v6 | LATEST STATION PHOTOS | CUBES: {args.cube.upper()} | ID4 EXCLUDED | NO WHEELS', '1;36'))
    for number, (label, joints) in enumerate(steps, 1):
        duration_ms = duration_for(label)
        payload(joints, number, duration_ms)
        print(color(f'{number:02d}. {label}', '1;36') + color(f' | {joints} | {duration_ms} ms', '35'), flush=True)
    # Preview is the default. Importing this module never dispatches motion.
    if not args.execute:
        print(color('PREVIEW ONLY: no movement commands. Vision mode reads camera snapshots.', '1;33'))
        return 0
    print('ID4 must remain physically stable and cool; omission is not electrical isolation.')
    print('Keep phone controls idle. Use the latest green=deposition, blue=metrology, red=etch layout; start with empty gripper.')
    print('Source photos display different ID4 values (20/4/0); actual fixed-joint geometry and derived returns are unverified.')
    print('Each move: 500 ms, then 150 ms settling. Metrology pre-turn lift is derived; see station_poses.json.')
    print(color('Each cube: base -> approach -> pickup -> lift -> destination -> release -> empty-arm return to base.', '1;33'))
    print(color('Clearance trim: +0.5 ID5 command units on ALL approach/raised poses; not calibrated mm or percent. New transitions unverified.', '1;33'))
    print('Ctrl+C stops future commands; an already-sent move may finish.')
    print(color('AUTOMATIC SELECTED CUBES — starts in 5 seconds. Ctrl+C cancels.', '1;33') if not args.step else color('STEP MODE: approval before each command.', '1;33'), flush=True)
    try:
        if not args.step:
            time.sleep(5)
        if args.vision:
            # Recheck after countdown, before any motion. Never silently switch target.
            checked = select(args.host, args.vision_config, observation_pose=BASE_POSE, pose_set=POSE_SET, stations=list(CUBES))
            if checked['cube'] != target['cube'] or math.dist(checked['center'], target['center']) > 8:
                raise RuntimeError('Target changed during countdown; no movement')
        for number, (label, joints) in enumerate(steps, 1):
            print(color(f'\nSTEP {number}/{len(steps)} — {label}', '1;36'))
            if args.step:
                answer = input(color('Check clearance. Type go to move; anything else cancels: ', '1;33'))
                if answer.strip().lower() != 'go':
                    print(color('CANCELLED: no further commands.', '1;33'))
                    return 0
            duration_ms = duration_for(label)
            # No retries: a timeout does not prove the robot ignored a request.
            req = Request(f'http://{args.host}:9030/', data=json.dumps(payload(joints, number, duration_ms)).encode(), headers={'Content-Type': 'application/json'})
            with urlopen(req, timeout=5) as response:
                result = json.load(response)
            # Vendor acknowledgement is transport/service acceptance, not grasp feedback.
            if result.get('error') or not isinstance(result.get('result'), list) or not result['result'] or result['result'][0] is not True:
                raise RuntimeError(f'Command rejected: {result}')
            print(color('ACCEPTED: observe physical movement.', '1;32'), flush=True)
            time.sleep(duration_ms / 1000 + SETTLE_SECONDS)
        print(color('SEQUENCE FINISHED: verify cubes released at destination and empty arm at start.', '1;32'))
        return 0
    except (KeyboardInterrupt, EOFError):
        print(color('\nSTOPPED: no automatic return or release.', '1;31'))
        return 1
    except (URLError, OSError, ValueError, RuntimeError) as exc:
        print(color(f'STOPPED: {exc}. A sent command may have executed; no automatic retries.', '1;31'))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
