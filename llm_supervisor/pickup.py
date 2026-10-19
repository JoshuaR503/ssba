#!/usr/bin/env python3
"""Experimental checkpointed transfer, isolated from the working baseline.

Preview is offline. --execute enables both camera/API calls and robot motion.
Movements use the latest calibrated poses at 500 ms plus 150 ms settling.
No model-generated angles, recovery, regrips or ID4/wheel commands are accepted.
"""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import time
from urllib.request import Request, urlopen

import supervisor as ai
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from pickup_steps import compact_steps

ROOT = Path(__file__).resolve().parent
COLORS = {'deposition': 'green', 'metrology': 'blue/cyan', 'etch': 'red'}
TARGET_SCHEMA = {
    'type': 'object',
    'properties': {
        'status': {'type': 'string', 'enum': ['visible', 'absent', 'uncertain']},
        'pickup_area_visible': {'type': 'boolean', 'description': 'Relevant local pickup patch/edge is visible; the entire tabletop is not required.'},
        'appearance_consistent': {'type': 'boolean', 'description': 'Visible object appearance supports the expected cube/color, allowing lighting casts; taught pose alone is not evidence.'},
        'evidence_type': {'type': 'string', 'enum': ['full_cube', 'recognizable_partial_cube', 'insufficient']},
        'evidence': {'type': 'string'},
    },
    'required': ['status', 'pickup_area_visible', 'appearance_consistent', 'evidence_type', 'evidence'],
    'additionalProperties': False,
}
CARRY_SCHEMA = {
    'type': 'object',
    'properties': {
        'status': {'type': 'string', 'enum': ['likely_carrying', 'not_carrying', 'uncertain']},
        'target_color_visible_near_camera': {'type': 'boolean'},
        'appearance_matches_before': {'type': 'boolean'},
        'clearly_left_on_source': {'type': 'boolean'},
        'evidence': {'type': 'string'},
    },
    'required': ['status', 'target_color_visible_near_camera', 'appearance_matches_before', 'clearly_left_on_source', 'evidence'],
    'additionalProperties': False,
}


def validate_carry(result):
    """Gate on weak near-camera color continuity, never claim confirmed gripping.

    Matching close target fragments may pass without visible fingers/support.
    Missing, conflicting, or clearly source-supported evidence must not pass.
    """
    if not isinstance(result, dict) or set(result) != set(CARRY_SCHEMA['required']):
        raise ValueError('Malformed carrying assessment')
    if result['status'] not in CARRY_SCHEMA['properties']['status']['enum']:
        raise ValueError('Unknown carrying status')
    for key in ('target_color_visible_near_camera', 'appearance_matches_before', 'clearly_left_on_source'):
        if type(result[key]) is not bool:
            raise ValueError('Carrying evidence flags must be booleans')
    if not isinstance(result['evidence'], str) or not result['evidence'].strip():
        raise ValueError('Missing carrying evidence')
    result = result.copy()
    if result['clearly_left_on_source']:
        result['status'] = 'not_carrying'
    elif result['status'] == 'likely_carrying' and not (result['target_color_visible_near_camera'] and result['appearance_matches_before']):
        result['status'] = 'uncertain'
    return {**result, 'suggested_action': 'continue' if result['status'] == 'likely_carrying' else 'return_to_start',
            'verification_type': 'weak_visual_color_continuity_not_confirmed_grip'}


RELEASE_SCHEMA = {
    'type': 'object',
    'properties': {
        'status': {'type': 'string', 'enum': ['likely_released', 'target_still_visible', 'uncertain']},
        'evidence': {'type': 'string'},
    },
    'required': ['status', 'evidence'],
    'additionalProperties': False,
}


class CheckpointPause(RuntimeError):
    """A visual checkpoint did not establish the required visible evidence."""


def configuration():
    """Load the folder-local active pose file; never import the non-LLM runner."""
    data = json.loads((ROOT / 'station_poses.json').read_text())
    if data['pose_set'] != 'station-photos-v6' or list(data['stations']) != list(ai.STATIONS):
        raise ValueError('Unexpected pose configuration')
    return data


def validate_targets(joints):
    """Check every command locally, independently of any model response."""
    if not joints or not set(joints) <= {1, 3, 5, 6}:
        raise ValueError('Only servo IDs 1,3,5,6 are permitted')
    if all(joints.get(joint) == value for joint, value in {3:48, 5:4, 6:0}.items()):
        raise ValueError('Banned upright start pose; use raised base {3:74,5:-33.5,6:-4}')
    for joint, value in joints.items():
        if type(value) not in (int, float) or not math.isfinite(value) or not -90 <= value <= 90:
            raise ValueError('Invalid joint target')
        if joint == 3 and value < 30:
            raise ValueError('ID3 must remain >=30')
    return joints


def station_steps(name, data, current=None):
    """Build the calibrated pickup cycle and remove unchanged commands."""
    cube = data['stations'][name]
    convert = lambda raw: {int(k): v for k, v in raw.items()}
    start, approach, pickup, raised, tray = [convert(cube[k]) for k in ('start', 'approach', 'pickup', 'raised', 'destination')]
    trim = data['lift_trim']['command_delta']
    if cube.get('approach_trim', True):
        approach[5] += trim
    approach[1] = cube['open']
    raised[5] += trim
    steps = [
        ('Base/start', start.copy()),
        ('Open approach', approach),
        ('Lower to taught pickup', pickup),
        ('Grip', {1: cube['grip']}),
        ('Lift — CAMERA CHECK before turning', raised),
        ('Turn to tray', {6: tray[6]}),
        ('Lower over tray', {3: tray[3], 5: tray[5]}),
        ('Release — CAMERA CHECK before empty-arm return', {1: cube['release']}),
        ('Retract empty arm', {3: raised[3], 5: raised[5]}),
        ('Turn empty arm back', {6: start[6]}),
        ('Return to start', start.copy()),
    ]
    for _, joints in steps:
        validate_targets(joints)
    return compact_steps(steps, current)


def validate_checkpoint(result, kind):
    """Strictly validate model evidence; uncertainty never authorizes continuation."""
    schema = TARGET_SCHEMA if kind == 'approach' else RELEASE_SCHEMA
    if not isinstance(result, dict) or set(result) != set(schema['required']):
        raise ValueError('Malformed checkpoint result')
    if not isinstance(result['evidence'], str) or not result['evidence'].strip():
        raise ValueError('Missing checkpoint evidence')
    if result['status'] not in schema['properties']['status']['enum']:
        raise ValueError('Unknown checkpoint status')
    for key, specification in schema['properties'].items():
        if specification['type'] == 'boolean' and type(result[key]) is not bool:
            raise ValueError('Checkpoint evidence flags must be booleans')
    result = result.copy()
    if kind == 'approach':
        if result['evidence_type'] not in TARGET_SCHEMA['properties']['evidence_type']['enum']:
            raise ValueError('Unknown approach evidence type')
        if not result['pickup_area_visible']:
            result['status'] = 'uncertain'
        if result['status'] == 'visible' and (not result['appearance_consistent'] or result['evidence_type'] == 'insufficient'):
            result['status'] = 'uncertain'
    return result


def assess(kind, station, frame, before=None, model=ai.DEFAULT_MODEL):
    """Request one observation at a completed pose; never request new joint angles."""
    target = COLORS[station]
    context = f'Target is the {target} cube at {station}. '
    if kind == 'approach':
        prompt = (context + 'The robot has stopped at this station’s calibrated OPEN PICKUP-HEIGHT pose, immediately before closing the gripper. '
                  'This is a close arm-mounted view: the target may be very close and partially cut off at the BOTTOM EDGE. '
                  'First inspect the bottom edge and nearby lower image, then the rest of the frame. The box may occupy '
                  'most of the image. Full tabletop visibility, the station label and a complete cube silhouette are NOT required. '
                  'A recognizable partial cube face/top/edge at the expected pickup patch can count as visible if its '
                  'geometry/material and appearance support the expected target. Set evidence_type recognizable_partial_cube '
                  'and describe exactly which fragment is visible. Set pickup_area_visible true when that relevant local '
                  'box/pickup patch is visible, even if most of the tabletop is outside the frame. '
                  'Colored robot LEDs can cast red/pink/blue light: consider lighting, but do not simply relabel a '
                  'clearly different-colored cube as the expected one. Set appearance_consistent only when visual evidence supports it. '
                  'The taught pose is context, NOT proof that the target exists. A generic colored strip, glow, gripper '
                  'pad, cable or screen image is insufficient. If the fragment cannot be identified, use uncertain and '
                  'evidence_type insufficient. Faces/room alone require pickup_area_visible false. absent requires a clear '
                  'view of the expected local pickup patch showing no target; cropping/occlusion alone means uncertain. '
                  'This checkpoint assesses likely target visibility only, not grip, distance or 3D clearance.')
        schema, images = TARGET_SCHEMA, [frame]
    elif kind == 'grip':
        prompt = (context + 'Use a WEAK VISUAL CARRYING HEURISTIC, not confirmed grip verification. '
                  'Image 1 is the open approach before gripping; image 2 is after the taught grip and lift. '
                  'The camera moves with the arm. Inspect the bottom edge and nearby lower frame first. '
                  'A matching target-colored object/face/edge fragment remaining close to the camera in image 2, '
                  'consistent with the fragment in image 1, can support likely_carrying even when fingers and '
                  'supporting surface are not visible. A full cube silhouette and visible finger contact are NOT required. '
                  'Do not reject solely because the fingers or cube clearance cannot be seen. This is deliberately '
                  'weaker evidence and does not prove attachment or a successful grip. Color is affected by LEDs; '
                  'do not count colored glow, cables, pads or screens, or a clearly different object elsewhere. '
                  'Set clearly_left_on_source true only if actual visible spatial evidence establishes the target '
                  'still rests on its original support; being at the bottom edge does NOT establish that. '
                  'Disappearance, a background change or an obscured fragment alone means uncertain, not success. '
                  'not_carrying requires clear negative evidence such as the target visibly left on the source. '
                  'Describe the observed fragment and similarity, and report likely_carrying only when both '
                  'target_color_visible_near_camera and appearance_matches_before are supported by the images.')
        schema, images = CARRY_SCHEMA, [before, frame]
    elif kind == 'release':
        prompt = (context + 'This is AFTER the taught release command at the TRAY, not at the source station. '
                  'Provide an ADVISORY visual observation only. Fingers are never visible from this camera; '
                  'do NOT request finger contact/separation as evidence. A visible target resting in the tray '
                  'can suggest likely_released. A target-colored fragment still close to the camera means '
                  'target_still_visible, not necessarily still held. If the cube is cropped out or no support '
                  'relationship is visible, use uncertain. Disappearance alone does not prove release. '
                  'Do not look for this cube back at its original pickup area or propose returning there.')
        schema, images = RELEASE_SCHEMA, [frame]
    else:
        raise ValueError('Unknown checkpoint')
    result, elapsed = ai.ask_gemini(prompt, schema, images, model)
    return (validate_carry(result) if kind == 'grip' else validate_checkpoint(result, kind)), elapsed


def send_move(host, joints, number):
    """Send exactly one 500 ms baseline move; no retries or recovery commands."""
    validate_targets(joints)
    params = [500]
    for joint, target in joints.items():
        params.extend([joint, target])
    request = Request(f'http://{host}:9030/', data=json.dumps({'jsonrpc': '2.0', 'method': 'SetPWMServo', 'params': params, 'id': number}).encode(), headers={'Content-Type': 'application/json'})
    with urlopen(request, timeout=5) as response:
        result = json.load(response)
    if not isinstance(result, dict) or result.get('error') or not isinstance(result.get('result'), list) or not result['result'] or result['result'][0] is not True:
        raise RuntimeError('Robot command was not acknowledged; no retry')
    time.sleep(0.65)


def reverse_to_start(station, history, current, host, record, *, release_sent=False, step_mode=False):
    """Restore pre-command targets in reverse, back to the taught station start.

    This reverses commanded waypoints, not measured physical trajectories.
    Before release, reverse lift first, then reopen at source pickup height.
    After a release was sent, keep fingers open: never regrip a delivered cube.
    A failed reverse command stops immediately; there is no retry.
    """
    print(f'[{station.upper()}] IMAGE CHECK FAILED — reversing to taught start.', flush=True)
    for offset, (step, previous) in enumerate(reversed(history), 1):
        targets = previous.copy()
        if release_sent:
            targets.pop(1, None)
        targets = {joint: value for joint, value in targets.items() if current[joint] != value}
        if not targets:
            continue
        validate_targets(targets)
        print(f'REVERSE step {step}: {targets} | 500 ms', flush=True)
        if step_mode and input('Type go to send this reverse move; anything else stops: ').strip().lower() != 'go':
            raise KeyboardInterrupt('Operator stopped reverse')
        send_move(host, targets, 1000 + offset)
        current.update(targets)
        record({'type': 'reverse_accepted', 'station': station, 'undo_step': step, 'targets': targets, 'duration_ms': 500})
    record({'type': 'returned_after_failed_check', 'station': station, 'final_commanded_pose': current.copy(), 'release_already_sent': release_sent})


def execute_station(station, data, host, model, record, *, approach_only=False, step_mode=False, initial_pose=None):
    """Gate lowering, tray transfer and return with fresh checkpoint observations.

    A failed approach/carry check reverses acknowledged waypoints to the
    taught start, then stops. After release, advisory observations never trigger
    a return to pickup height: use the original retract/turn/start sequence.
    Transport errors, malformed responses and Ctrl+C stop without blind reversal.
    """
    steps = station_steps(station, data, initial_pose)
    before = None
    current = dict(initial_pose) if initial_pose else {int(k): v for k,v in data['stations'][station]['start'].items()}
    history = []
    release_status = 'uncertain'
    for number, (label, joints) in enumerate(steps, 1):
        print(f'[{station.upper()}] {number:02}/{len(steps)} {label} | {joints} | 500 ms', flush=True)
        if step_mode and input('Type go to send this move; anything else stops: ').strip().lower() != 'go':
            raise KeyboardInterrupt('Operator stopped before movement')
        previous = {joint: current[joint] for joint in joints}
        send_move(host, joints, number)
        current.update(joints)
        history.append((number, previous))
        record({'type': 'move_accepted', 'station': station, 'step': number, 'targets': joints, 'duration_ms': 500})
        kind = ('approach' if number < len(steps) and steps[number][0] == 'Grip' else 'grip' if label.startswith('Lift') else 'release' if label.startswith('Release') else None)
        if kind is None:
            continue
        print(f'CAMERA CHECK: {kind}' + (' — OPEN AT PICKUP HEIGHT, before closing' if kind == 'approach' else '') + '; arm remains at this pose while awaiting API.', flush=True)
        frame = ai.capture_camera(host)
        result, elapsed = assess(kind, station, frame, before, model)
        record({'type': 'checkpoint', 'station': station, 'checkpoint': kind, 'result': result, 'api_elapsed_seconds': elapsed})
        print(json.dumps({'checkpoint': kind, 'station': station, 'result': result, 'api_seconds': elapsed}), flush=True)
        if kind == 'approach':
            before = frame
        if kind == 'release':
            release_status = result['status']
            print('Release observation is advisory; continuing normal retract -> turn back -> start. No return to source pickup height.', flush=True)
            continue
        passed = result['status'] == {'approach': 'visible', 'grip': 'likely_carrying'}[kind]
        if not passed:
            reverse_to_start(station, history, current, host, record, step_mode=step_mode)
            raise CheckpointPause(f'{station} {kind}: {result["status"]}. Returned to taught start; run stopped, no retry.')
        if approach_only:
            return 'approach_checked_only'
    return f'cycle_completed_release_observation_{release_status}'


def main():
    """Offline preview by default; explicit execution enables checkpoints and motion."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--execute', action='store_true', help='Run automatically')
    mode.add_argument('--go', action='store_true', help='Execute step by step; type go before each move')
    parser.add_argument('--cube', choices=['all', *ai.STATIONS], default='all')
    parser.add_argument('--approach-only', action='store_true', help='One station: reach OPEN pickup height, inspect, stop before gripping')
    parser.add_argument('--host', default='raspberrypi.local')
    parser.add_argument('--model', default=ai.DEFAULT_MODEL)
    parser.add_argument('--instruction', help='Optional natural-language job/order instruction; uses LLM station selection')
    parser.add_argument('--unavailable', choices=ai.STATIONS, nargs='*', default=[])
    args = parser.parse_args()
    if args.approach_only and args.cube == 'all':
        parser.error('--approach-only requires --cube deposition, metrology, or etch')
    if not re_host(args.host):
        parser.error('Use a hostname or IPv4 address for --host')
    data = configuration()
    selected = list(ai.STATIONS) if args.cube == 'all' else [args.cube]
    plans = {}
    planned_pose = {}
    for name in selected:
        plans[name] = station_steps(name, data, planned_pose)
        for _, joints in plans[name]:
            planned_pose.update(joints)
    for name, steps in plans.items():
        print(f'\n{name.upper()} — 500 ms moves, +0.5 ID5 clearance trim')
        for number, (label, joints) in enumerate(steps[:next(i for i,(name,_) in enumerate(steps) if name == 'Grip')] if args.approach_only else steps, 1):
            check = ' — CAMERA CHECK before closing' if number < len(steps) and steps[number][0] == 'Grip' else ''
            print(f'  {number:02}. {label}{check}: {joints}')
    if not (args.execute or args.go):
        print('PREVIEW ONLY — no camera, API or robot calls.')
        return 0
    if not ai.local_api_key():
        parser.error('No local API key configured')
    print('ID4 excluded; ID3 >=30. Use taught layout, empty gripper and idle phone controls. Failed approach/carry checks reverse to taught start; release checks are advisory. Connection failures stop in place.', flush=True)
    print('Starting immediately. Ctrl+C stops future commands; sent moves may finish.', flush=True)
    log_dir = ROOT / 'runs'
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.jsonl')
    def record(event):
        """Write stage timing/assessment metadata only, never images or credentials."""
        with log_path.open('a') as stream:
            stream.write(json.dumps({'time_utc': datetime.now(timezone.utc).isoformat(), **event}) + '\n')
    state = {'pending': selected.copy(), 'available': {s: s not in args.unavailable for s in ai.STATIONS}, 'tray_ready': True, 'arm_idle': True}
    print(f'Run log: {log_path}', flush=True)
    current_pose = {}
    try:
        while state['pending']:
            if args.instruction:
                decision, elapsed = ai.plan(state, args.instruction, args.model)
                record({'type': 'station_decision', 'result': decision, 'api_elapsed_seconds': elapsed})
                if decision['action'] != 'pick_station':
                    raise CheckpointPause(decision['reason'])
                station = decision['station']
            else:
                eligible = ai.eligible_stations(state)
                if not eligible:
                    raise CheckpointPause('Remaining stations unavailable')
                station = eligible[0]
            started = time.monotonic()
            outcome = execute_station(station, data, args.host, args.model, record, approach_only=args.approach_only, step_mode=args.go, initial_pose=current_pose)
            record({'type': 'station_finished', 'station': station, 'outcome': outcome, 'elapsed_seconds': round(time.monotonic()-started, 3)})
            current_pose = {int(k):v for k,v in data['stations'][station]['start'].items()}
            state['pending'].remove(station)
        print('Finished. Visual assessments are not force/position sensor confirmation.')
        return 0
    except (OSError, ValueError, RuntimeError, KeyboardInterrupt) as exc:
        message = str(exc) or 'Operator interrupted'
        record({'type': 'stopped', 'reason': message, 'pending': state['pending']})
        print(f'STOPPED: {message}. No further commands or automatic retry.', file=sys.stderr)
        return 1


def re_host(host):
    """Restrict robot destinations to a hostname/IPv4, not an arbitrary URL."""
    import re
    return re.fullmatch(r'[a-zA-Z0-9.-]+', host)


if __name__ == '__main__':
    raise SystemExit(main())
