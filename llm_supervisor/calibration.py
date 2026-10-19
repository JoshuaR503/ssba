#!/usr/bin/env python3
"""Step through open-gripper reference poses to mark the physical cube locations.

Preview by default; --go prompts before each move; --execute runs automatically.
No grip, tray transfer, camera/API calls, or edits to taught targets. At the
pickup-height stop, align/mark the cube between the open fingers before moving
on. This is placement assistance, not automatic geometric/servo calibration.
"""
import argparse
import sys

from pickup import COLORS, configuration, re_host, send_move, validate_targets


def positioning_steps(station, data, current=None):
    """Build open-gripper positioning/retract steps, keeping contact pose untrimmed.

    Start uses the chosen raised base with this station's OPEN gripper value.
    After the pickup-height pause, raise before turning back to start. Every
    step explicitly retains the open value, so no gripping target is emitted.
    """
    cube = data['stations'][station]
    convert = lambda name: {int(k): v for k, v in cube[name].items()}
    start, approach, contact, raised = [convert(k) for k in ('start', 'approach', 'pickup', 'raised')]
    # Retain the approved etch contact wrist setting; lift remains ID3=80.
    if station == 'etch':
        contact[3] = 76
    approach[5] += data['lift_trim']['command_delta']
    raised[5] += data['lift_trim']['command_delta']
    # One operator-selected raised base for every calibration station.
    # Never return to the old upright ID3=48/ID5=4/ID6=0 pose that faced the user.
    start = {1: cube['open'], 3: 74, 5: -33.5, 6: -4}
    steps = [
        ('Start with gripper OPEN', start),
        ('OPEN approach above pickup', approach),
        ('PICKUP HEIGHT — align/mark cube here; no gripping', contact),
        ('Raise OPEN fingers away from marked position', raised),
        ('Turn empty arm back toward start', {6: start[6]}),
        ('Return to start, gripper OPEN', start.copy()),
    ]
    if station == 'deposition':
        # The 0.5-unit approach/contact separation adds no useful calibration stop.
        steps = [step for step in steps if step[0] != 'OPEN approach above pickup']
    for _, joints in steps:
        joints[1] = cube['open']
        validate_targets(joints)
    # Skip commands that leave the accumulated commanded pose unchanged.
    # The first station still establishes a known base from an unknown pose.
    state = dict(current or {})
    compact = []
    for label, joints in steps:
        changed = {joint: value for joint, value in joints.items() if joint not in state or state[joint] != value}
        if not changed:
            continue
        # Between stations only the open gripper value changes at the shared base.
        if label == 'Start with gripper OPEN' and state and set(changed) == {1}:
            # The following approach already includes the required open value.
            continue
        compact.append((label, joints))
        state.update(joints)
    return compact


def main():
    """Preview or position each station with explicit go before every move; never grip."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='Run all selected moves automatically')
    parser.add_argument('--go', action='store_true', help='Step by step; require go before every move')
    parser.add_argument('--cube', choices=['all', *COLORS], default='all')
    parser.add_argument('--host', default='raspberrypi.local')
    args = parser.parse_args()
    if not re_host(args.host):
        parser.error('Use a hostname or IPv4 address')
    data = configuration()
    stations = list(COLORS) if args.cube == 'all' else [args.cube]
    plans = {}
    current = {}
    for station in stations:
        plans[station] = positioning_steps(station, data, current)
        for _, joints in plans[station]:
            current.update(joints)
    print('POSITIONING GUIDE | OPEN GRIPPER ONLY | 500 ms | ID4 EXCLUDED | ID3 >=30')
    for station, steps in plans.items():
        print(f'\n{station.upper()} — {COLORS[station]}')
        for index, (label, joints) in enumerate(steps, 1):
            print(f'  {index}. {label}: {joints}')
    if not (args.execute or args.go):
        print('\nPREVIEW ONLY. Add --execute for automatic execution, or --go for step-by-step positioning.')
        return 0
    print('\nStart with an empty gripper and idle phone controls.')
    print('AUTOMATIC: starting immediately, no prompts or pickup holds.' if not args.go else 'INTERACTIVE: type go before each move; wait at pickup height as needed.')
    print('Keep hands clear before approving a move. q or Ctrl+C stops in place; no automatic return.')
    print(f'Live feed: http://{args.host}:8080/')
    number = 0
    try:
        for station, steps in plans.items():
            for index, (label, joints) in enumerate(steps, 1):
                print(f'\n[{station.upper()} / {COLORS[station]}] {index}/{len(steps)} — {label}\nTargets: {joints} | 500 ms', flush=True)
                if args.go:
                    answer = input('Type go to send this move; anything else stops here: ').strip().lower()
                    if answer != 'go':
                        print('Stopped in current pose; no further commands.')
                        return 0
                number += 1
                send_move(args.host, joints, number)
                print('Command accepted. Observe the physical pose.', flush=True)
                if label.startswith('PICKUP HEIGHT'):
                    print(f"{'HOLDING' if args.go else 'PASSING'} OPEN AT {COLORS[station].upper()} PICKUP HEIGHT — right before gripping. {'Align/mark the location.' if args.go else 'No pause in automatic mode.'}", flush=True)
        print('\nPositioning sequence complete. No grip or transfer commands sent; no configuration changed.')
        return 0
    except (KeyboardInterrupt, EOFError, OSError, ValueError, RuntimeError) as exc:
        print(f'\nSTOPPED: {str(exc) or "operator interruption"}. No automatic return. A sent move may finish.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
