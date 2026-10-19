# Installed MasterPi software: initial inspection

Source: local copy in `robot-reference/MasterPi`, transferred from `/home/pi/MasterPi` on October 17, 2026. This is a vendor application snapshot, not a full robot disk backup. Findings below come from reading source, not executing it. Hardware availability and endpoint reachability remain to be tested.

## Startup and CPU usage

The user supplied `systemctl status 721` shows `masterpi.service` enabled and running `/usr/bin/python3 /home/pi/MasterPi/MasterPi.py`. The service unit itself was not included in this transfer.

`MasterPi.py` initializes the controller and ultrasonic sensor, starts a voltage-reading thread, starts JSON-RPC and MJPEG servers, and opens the camera. Its main loop sleeps about 30 ms between passes. Even when no behavior is selected, it passes camera frames to the stream server.

`Camera.py` requests 30 FPS and maintains a camera-reading thread. Every successful frame is resized to 640x480 and corrected using calibration maps. This continuous processing plausibly contributes to the observed 41.2% CPU usage; profiling would be needed to quantify each contributor. The observed CPU temperatures around 49–52 C were measured while the vendor service was active.

Startup is not motion-free: `rpc_server.set_board()` calls `color_detect.initMove()` and sounds the buzzer. Do not restart the main program just to inspect it.

## Interfaces found

| Component | Source | Observed behavior |
| --- | --- | --- |
| Controller | `masterpi_sdk/common_sdk/common/ros_robot_controller_sdk.py` | `Board()` opens `/dev/ttyAMA0` at 1,000,000 baud; provides servo, motor, battery, and other protocol methods |
| Chassis | `masterpi_sdk/common_sdk/common/mecanum.py` | `MecanumChassis.set_velocity(velocity, direction, angular_rate)` translates to four motor duty commands; module creates a Board instance during import |
| Arm | `masterpi_sdk/kinematics_sdk/kinematics/arm_move_ik.py` | Inverse-kinematics support for arm positioning |
| PWM servos | Controller SDK and `board_demo/control_by_servo.py` | `pwm_servo_set_position(duration, [[id, pulse], ...])`; demo immediately issues movements |
| Ultrasonic/RGB | `masterpi_sdk/common_sdk/common/sonar.py` | Uses I2C bus 1, address `0x77`; distance and RGB methods present; physical readings not verified |
| Action groups | `masterpi_sdk/common_sdk/common/action_group_control.py` | Loads `.d6a` files using SQLite from `/home/pi/MasterPi/action_groups/` |
| Camera | `Camera.py`, `CameraCalibration/` | OpenCV capture, calibration files, frame correction |
| Video stream | `mjpg_server.py` | HTTP listener on port 8080; snapshot path `/?action=snapshot`; other GET paths enter MJPEG streaming |
| Remote API | `rpc_server.py` | Werkzeug JSON-RPC listener on port 9030; read methods and movement methods share the dispatcher |
| Behavior selection | `functions/running.py` | Selects, starts, stops, and unloads behaviors; 15-second heartbeat expiry unloads selected behavior |

The chassis docstring labels velocity as mm/s, but its implementation feeds computed values directly to motor duty commands. Do not assume calibrated physical speed from that parameter alone.

SDK packaging confirms that `masterpi_sdk/common_sdk/common` installs as Python package `common`, and `masterpi_sdk/kinematics_sdk/kinematics` as `kinematics`. The folder name `masterpi_sdk` does not invalidate the existing `common.mecanum` import convention.

## Behavior map

`functions/running.py` registers:

| ID | Behavior |
| --- | --- |
| 0 | No selected behavior |
| 1 | Remote control |
| 2 | Color detection |
| 3 | Color sorting |
| 4 | Color tracking |
| 5 | Visual line patrol |
| 6 | Obstacle avoidance |
| 7–8 | Unassigned |
| 9 | LAB color calibration |

Other files include face recognition, color recognition, and color warning, but their presence alone does not mean they are selected or running. `RunningFunc` starts at 0; current runtime selection was not queried.

## Read interfaces worth exploring next

- Camera snapshot, from a Mac browser: `http://raspberrypi.local:8080/?action=snapshot`. This source-defined endpoint has not yet been tested; an unavailable camera can prevent a useful response.
- JSON-RPC method `GetBatteryVoltage`: source returns the controller battery reading without the main program's conversion from millivolts to volts. On external power this is a supply reading, not battery state of charge.
- JSON-RPC method `GetSonarDistance`: source requests distance from the initialized ultrasonic object. Units should be checked in the driver's conversion before presenting readings.
- Installed dependencies and complete service configuration still need a separate read-only inventory. They are not included merely by copying MasterPi.

Use the existing service for compatible read requests rather than launching a second controller process. Multiple serial readers may interfere. Imported modules can open hardware or start threads, and example scripts can issue motion at top level; source inspection should precede execution.

## Relation to the school project

Reuse the low-level arm/chassis interfaces and camera infrastructure after calibration. Our project supplies the missing wafer scheduling logic, station/lot state, measurements, and comparisons between scheduling approaches. Color sorting and line following are existing robot behaviors, not evidence of an AI wafer scheduling optimizer.

Next useful steps: verify the camera snapshot, capture service configuration and dependency inventory, review arm geometry/servo mappings, then design repeatable station fixtures and measured transfer operations. Full file-by-file review, physical calibration, and live API verification have not yet been completed.
