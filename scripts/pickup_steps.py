"""Shared motion-only compaction for baseline and AI pickup runners."""


def compact_steps(steps, current=None):
    """Skip unchanged commands; merge between-station opening into approach.

    Preserve real raises/turns and the first start from unknown position. Targets
    are copied; no angle, timing, gripper grip or tray target is invented.
    """
    state = dict(current or {})
    result = []
    for label, raw in steps:
        joints = raw.copy()
        changed = {k:v for k,v in joints.items() if k not in state or state[k] != v}
        if not changed:
            continue
        if 'Base/start' in label and state and set(changed) == {1}:
            continue  # Next open approach explicitly contains the opening target.
        result.append((label, joints))
        state.update(joints)
    return result
