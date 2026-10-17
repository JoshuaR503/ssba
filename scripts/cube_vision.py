"""Local OpenCV station selector. No motion commands or external AI calls."""
import json
import math
import time
from pathlib import Path
from urllib.request import urlopen


def libraries():
    """Lazily import OpenCV and NumPy; raise RuntimeError with install guidance."""
    try:
        import cv2
        import numpy as np
        return cv2, np
    except ImportError as exc:
        raise RuntimeError('Install vision dependencies: .venv/bin/python -m pip install -r requirements-vision.txt') from exc


def snapshot(host):
    """Read and decode one camera snapshot on port 8080, capped at 8 MB. Sends no motion."""
    cv2, np = libraries()
    with urlopen(f'http://{host}:8080/?action=snapshot', timeout=4) as response:
        raw = response.read(8_000_001)
    if len(raw) > 8_000_000:
        raise RuntimeError('Snapshot too large')
    frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise RuntimeError('Camera did not return a usable image')
    return frame


def read_distance(name):
    """Prompt until a positive finite station distance in centimeters is entered."""
    while True:
        raw = input(f'{name}: measured distance from observation gripper to cube center, cm: ').strip()
        try:
            distance = float(raw)
            if not math.isfinite(distance) or distance <= 0:
                raise ValueError()
            return distance
        except ValueError:
            print('Enter a positive number, for example 12. Blank input does not cancel.')


def configure(host, path, distances=None, *, observation_pose, pose_set, stations):
    """Calibrate three station ROIs at an already established observation pose.

    Args:
        host: Robot camera hostname or IP address.
        path: Destination JSON calibration file.
        distances: Optional positive centimeter distances in station order;
            otherwise prompt after each ROI selection.
        observation_pose: Actual operator-established arm pose to record.
        pose_set: Version identifying the active taught-pose configuration.
        stations: Three canonical station names in calibration order.

    Requires a graphical OpenCV session. Captures one image, asks for tight ROIs,
    estimates center LAB colors, and saves only after all selections complete.
    Existing configuration survives cancellation. Always closes image windows.
    No pose is commanded or independently verified by this function.
    """
    cv2, _ = libraries()
    frame = snapshot(host)
    zones = []
    print(f'At observation pose {observation_pose}, select green=deposition, blue=metrology, red=etch. Enter confirms; Esc cancels.')
    try:
        if distances is not None and (len(distances) != 3 or any(not math.isfinite(d) or d <= 0 for d in distances)):
            raise ValueError('Provide three positive finite distances: deposition, metrology, etch')
        for index, name in enumerate(stations):
            print(f'IMAGE WINDOW {index+1}/3: {name} — drag around this cube, then Enter in that window.', flush=True)
            roi = cv2.selectROI(f'{name}: select cube', frame, False, False)
            cv2.destroyAllWindows()
            x, y, w, h = map(int, roi)
            if w < 10 or h < 10:
                raise RuntimeError('Calibration cancelled or rectangle too small')
            distance = distances[index] if distances is not None else read_distance(name)
            print(f'{name}: distance {distance:g} cm recorded.', flush=True)
            lab = cv2.cvtColor(frame[y:y+h, x:x+w], cv2.COLOR_BGR2LAB)
            # Calibrate from the center, avoiding most background pixels.
            patch = lab[h//4:3*h//4, w//4:3*w//4]
            _, np = libraries()
            center = np.median(patch.reshape(-1, 3), axis=0)
            zones.append({'cube': name, 'roi': [x,y,w,h], 'lab_center': center.tolist(), 'distance_cm': distance})
        data = {'pose_set': pose_set, 'observation_pose': {str(k):v for k,v in observation_pose.items()}, 'image_size':[frame.shape[1], frame.shape[0]], 'zones':zones,
                'note':'Measured station-center distance, not live depth. Taught pickup only; robot/cubes/camera pose must remain fixed.'}
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data,indent=2)+'\n')
        print(f'Saved {path}. No motion commands sent.')
    finally:
        cv2.destroyAllWindows()


def detect(frame, data):
    """Return eligible in-zone color detections; reject changed image size or invalid zones.

    Uses LAB thresholds, morphological cleanup, contour area and center tolerance.
    Distances are calibration metadata, not live depth or ultrasonic readings."""
    cv2, np = libraries()
    if [frame.shape[1], frame.shape[0]] != data['image_size']:
        raise RuntimeError('Image size changed; recalibrate')
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    results=[]
    for zone in data['zones']:
        x,y,w,h=zone['roi']
        if min(x,y)<0 or min(w,h)<10 or x+w>frame.shape[1] or y+h>frame.shape[0]:
            raise ValueError('Invalid camera zone')
        c=np.asarray(zone['lab_center'],dtype=float)
        lower=np.clip(c-[55,22,22],0,255).astype(np.uint8)
        upper=np.clip(c+[55,22,22],0,255).astype(np.uint8)
        mask=cv2.inRange(lab[y:y+h,x:x+w],lower,upper)
        mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
        contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        if not contours: continue
        contour=max(contours,key=cv2.contourArea)
        if cv2.contourArea(contour)<0.15*w*h: continue
        m=cv2.moments(contour)
        if not m['m00']: continue
        cx=x+m['m10']/m['m00'];cy=y+m['m01']/m['m00']
        # Reject meaningful displacement: there is no arbitrary-XYZ grasp calibration.
        if abs(cx-(x+w/2))>0.2*w or abs(cy-(y+h/2))>0.2*h: continue
        distance=zone['distance_cm']
        if not math.isfinite(distance) or distance<=0: raise ValueError('Invalid station distance')
        results.append({'cube':zone['cube'],'center':[cx,cy],'distance_cm':distance,'roi':[x,y,w,h]})
    return results


def choose_stable(samples):
    """Choose the nearest calibrated station visible in at least three stable samples.

    Require each candidate in every sample and at most eight pixels displacement
    from the final center. Break distance ties by station name; return None if absent."""
    if len(samples)<3: return None
    candidates=[]
    for current in samples[-1]:
        matches=[next((r for r in sample if r['cube']==current['cube']),None) for sample in samples]
        if any(r is None for r in matches): continue
        if any(math.dist(r['center'],current['center'])>8 for r in matches): continue
        candidates.append(current)
    return min(candidates,key=lambda r:(r['distance_cm'],r['cube'])) if candidates else None


def select(host, path, *, pose_set, observation_pose, stations):
    """Validate calibration, sample three images, lock one station and save an overlay.

    Reject old pose sets or observation poses before reading the camera. Return
    the selected detection dictionary or raise on invalid/unstable input. Writes
    vision_selection.jpg beside the configuration; sends no movement commands."""
    cv2, _ = libraries()
    data=json.loads(Path(path).read_text())
    expected_pose = {str(k):v for k,v in observation_pose.items()}
    if data.get('pose_set') != pose_set or data.get('observation_pose') != expected_pose:
        raise RuntimeError('Camera zones belong to the older layout/observation pose. Recalibrate with --configure-vision --at-observation-pose; no motion sent.')
    if len(data['zones']) != 3 or {z['cube'] for z in data['zones']} != set(stations):
        raise RuntimeError('Configuration must contain deposition, metrology, and etch zones')
    samples=[]
    for _ in range(3):
        frame=snapshot(host)
        samples.append(detect(frame,data))
        time.sleep(0.15)
    target=choose_stable(samples)
    if target is None: raise RuntimeError('No stable eligible cube at a taught location; no movement')
    output=Path(path).parent/'vision_selection.jpg'
    for item in samples[-1]:
        x,y,w,h=item['roi'];selected=item['cube']==target['cube']
        cv2.rectangle(frame,(x,y),(x+w,y+h),(0,255,0) if selected else (0,180,255),2)
        cv2.putText(frame,f"{item['cube']} {item['distance_cm']:.1f}cm" ,(x,max(18,y-8)),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,255,0),1)
    cv2.imwrite(str(output),frame)
    print(f"LOCKED: {target['cube']} | measured station distance {target['distance_cm']} cm | overlay {output}")
    return target
