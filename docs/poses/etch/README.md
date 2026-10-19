# Etch — sorted photo and position record

**Red cube at the Etch station.** All 19 supplied images are included: seven control screenshots and twelve robot photos. Originals are unchanged; ordered viewing copies are stored beside this file.

Screenshot/photo pairings are inferred from filenames, visible poses, and joint changes. Displayed settings are transcribed observations, not measured joint feedback.

## Ordered positions

| Stage | Control screenshot | Robot photos | ID1 | ID3 | ID4 displayed only | ID5 | ID6 | Voltage |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1. Base/start reference | IMG_1022.HEIC | IMG_1023.jpg | 4 | 48 | 0 | 4 | 0 | 8.2 V |
| 2. Open approach to red cube | IMG_1024.HEIC | IMG_1025.jpg, IMG_1026.jpg | -42 | 76 | 0 | -50 | 32 | 8.3 V |
| 3. Grip red cube | IMG_1027.HEIC | IMG_1028.jpg, IMG_1029.jpg | 6 | 80 | 0 | -60 | 32 | 8.3 V |
| 4. Lift red cube | IMG_1030.HEIC | IMG_1031.jpg, IMG_1032.jpg | 6 | 80 | 0 | -30 | 32 | 8.3 V |
| 5. Turn held cube toward tray | IMG_1033.HEIC | IMG_1034.jpg | 6 | 80 | 0 | -30 | 90 | 8.3 V |
| 6. Lower held cube over tray | IMG_1035.HEIC | IMG_1036.jpg, IMG_1037.jpg | 6 | 90 | 0 | -58 | 90 | 8.3 V |
| 7. Release red cube in tray | IMG_1038.HEIC | IMG_1039.jpg, IMG_1040.jpg | -44 | 90 | 0 | -58 | 90 | 8.3 V |

## Filename inventory

- [IMG_1022.HEIC](/Users/joshua/Downloads/IMG_1022.HEIC) — stage 1: Base/start reference.
- [IMG_1023.jpg](/Users/joshua/Downloads/IMG_1023.jpg) — stage 1: Base/start reference.
- [IMG_1024.HEIC](/Users/joshua/Downloads/IMG_1024.HEIC) — stage 2: Open approach to red cube.
- [IMG_1025.jpg](/Users/joshua/Downloads/IMG_1025.jpg) — stage 2: Open approach to red cube.
- [IMG_1026.jpg](/Users/joshua/Downloads/IMG_1026.jpg) — stage 2: Open approach to red cube.
- [IMG_1027.HEIC](/Users/joshua/Downloads/IMG_1027.HEIC) — stage 3: Grip red cube.
- [IMG_1028.jpg](/Users/joshua/Downloads/IMG_1028.jpg) — stage 3: Grip red cube.
- [IMG_1029.jpg](/Users/joshua/Downloads/IMG_1029.jpg) — stage 3: Grip red cube.
- [IMG_1030.HEIC](/Users/joshua/Downloads/IMG_1030.HEIC) — stage 4: Lift red cube.
- [IMG_1031.jpg](/Users/joshua/Downloads/IMG_1031.jpg) — stage 4: Lift red cube.
- [IMG_1032.jpg](/Users/joshua/Downloads/IMG_1032.jpg) — stage 4: Lift red cube.
- [IMG_1033.HEIC](/Users/joshua/Downloads/IMG_1033.HEIC) — stage 5: Turn held cube toward tray.
- [IMG_1034.jpg](/Users/joshua/Downloads/IMG_1034.jpg) — stage 5: Turn held cube toward tray.
- [IMG_1035.HEIC](/Users/joshua/Downloads/IMG_1035.HEIC) — stage 6: Lower held cube over tray.
- [IMG_1036.jpg](/Users/joshua/Downloads/IMG_1036.jpg) — stage 6: Lower held cube over tray.
- [IMG_1037.jpg](/Users/joshua/Downloads/IMG_1037.jpg) — stage 6: Lower held cube over tray.
- [IMG_1038.HEIC](/Users/joshua/Downloads/IMG_1038.HEIC) — stage 7: Release red cube in tray.
- [IMG_1039.jpg](/Users/joshua/Downloads/IMG_1039.jpg) — stage 7: Release red cube in tray.
- [IMG_1040.jpg](/Users/joshua/Downloads/IMG_1040.jpg) — stage 7: Release red cube in tray.

## Paired visual evidence

### 01 — Base/start reference

Upright arm with empty gripper; red cube rests at Etch.

![IMG_1022.HEIC](01_start_controls_01.jpg)

![IMG_1023.jpg](01_start_robot_01.jpg)

### 02 — Open approach to red cube

Open fingers approach the red cube on the cardboard. Both external views are retained.

![IMG_1024.HEIC](02_approach_controls_01.jpg)

![IMG_1025.jpg](02_approach_robot_01.jpg)

![IMG_1026.jpg](02_approach_robot_02.jpg)

### 03 — Grip red cube

Fingers close around the red cube at the surface. ID3 and ID5 also change from the approach setting; this is not only a gripper change.

![IMG_1027.HEIC](03_grip_controls_01.jpg)

![IMG_1028.jpg](03_grip_robot_01.jpg)

![IMG_1029.jpg](03_grip_robot_02.jpg)

### 04 — Lift red cube

Red cube is visibly suspended above its empty Etch outline.

![IMG_1030.HEIC](04_lift_controls_01.jpg)

![IMG_1031.jpg](04_lift_robot_01.jpg)

![IMG_1032.jpg](04_lift_robot_02.jpg)

### 05 — Turn held cube toward tray

Red cube remains held while the arm turns toward the tray.

![IMG_1033.HEIC](05_turn_controls_01.jpg)

![IMG_1034.jpg](05_turn_robot_01.jpg)

### 06 — Lower held cube over tray

Red cube is held low over the tray containing green and blue cubes. Exact support/contact is not established from these views.

![IMG_1035.HEIC](06_lower_tray_controls_01.jpg)

![IMG_1036.jpg](06_lower_tray_robot_01.jpg)

![IMG_1037.jpg](06_lower_tray_robot_02.jpg)

### 07 — Release red cube in tray

Open fingers and red cube resting above the green/blue cubes are visible; 1040 provides a closer view of the stack. No later return pose is supplied.

![IMG_1038.HEIC](07_release_controls_01.jpg)

![IMG_1039.jpg](07_release_robot_01.jpg)

![IMG_1040.jpg](07_release_robot_02.jpg)

## Record boundaries

- ID4 displays 0 in all seven screenshots. It remains excluded from commands; these records do not authorize sending it to zero.
- Recorded ID3 values are 48, 76, 80, or 90, all at or above the minimum 30. Photos do not validate the full motion paths.
- Exact displayed values are preserved without applying lift trim, inventing durations, or adding a return pose.
- The final photos show red resting on the other cubes in the tray; this records the demonstration and does not define a general stacking routine.
- No executable script or robot configuration was changed, and no robot commands were sent.

Related records: [Deposition](../deposition/README.md) · [Metrology](../metrology/README.md).
