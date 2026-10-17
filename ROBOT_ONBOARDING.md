# Get the code onto the MasterPi Pi 5 / 4 GB

For this session the goal is: **copy the project → read hardware information → inspect a
transfer preview**. Movement stays disabled. AI training and datasets remain on the Mac.

## 1. Open the robot's own desktop or terminal

Use the existing Hiwonder system on its SD card. You do not need to reinstall the OS.
Either connect a monitor/keyboard, or use the vendor remote-desktop connection from the Mac.

For an unchanged Hiwonder Pi 5 image in default AP mode, the documented setup is:

- Power up the robot and wait for it to boot.
- Connect the Mac to its Wi-Fi network beginning with `HW`; documented Wi-Fi password: `hiwonder`.
- In VNC Viewer, connect to `192.168.149.1`.
- Documented Pi 5 desktop login: username `pi`, password `raspberrypi`.

These are manufacturer defaults, not verified credentials for your individual robot.
Use its actual credentials/address if they have been changed. A USB/monitor setup avoids
remote-desktop configuration. See the [Hiwonder connection guide](https://docs.hiwonder.com/projects/MasterPi/en/latest/docs/1.getting_ready.html#remote-desktop-installation-and-connection).

The robot hotspot is a local connection and normally has no internet. Copying files,
robot-check and robot-plan do not need internet. Dependency downloads do.
For internet access use the vendor [LAN-mode instructions](https://docs.hiwonder.com/projects/MasterPi/en/latest/docs/11_network_configuration.html).

## 2. Transfer the small robot bundle

The Mac project contains `dist/masterpi-wafer-pi5.zip`. It contains an inner folder named
`masterpi-wafer`, with source, hardware settings, example tasks, this guide and the setup
script. The bundle does not contain a Mac virtual environment, model weights, datasets,
review databases, credentials, or simulation outputs. Its copied motion setting is disabled.

**Simplest transfer: USB drive.** Copy the ZIP onto a USB drive from the Mac, plug the drive
into the Pi, and copy the ZIP to the Pi user's home folder using the Pi file manager.
Extract it there. The expected project folder is `~/masterpi-wafer`.
If that folder already exists, use a fresh folder so you preserve previous robot calibration.

**Alternative: SSH/SCP**, only if SSH is already enabled and you know the robot's account/IP.
On the Mac, replace ROBOT_USER and ROBOT_IP with their actual values:

```bash
scp "/Users/joshua/Desktop/ai-based wafer/dist/masterpi-wafer-pi5.zip" ROBOT_USER@ROBOT_IP:~/
```

Inside the Pi terminal, a command-line extraction option is:

```bash
python3 -m zipfile -e ~/masterpi-wafer-pi5.zip ~/
```

Use that command only when `~/masterpi-wafer` does not already exist; extraction can
overwrite files with the same name. Do not copy or replace the manufacturer's MasterPi directory.

## 3. Run this first, in the PI terminal

```bash
cd ~/masterpi-wafer
python3 -m wafer_project robot-check
```

No package installation is needed for this check. It discovers files without importing the
vendor drivers, and reads CPU temperature without sending motor/servo commands.

Look for `model_matches: true`, `memory_consistent_with_4gb: true`, a supported Python,
and a real CPU temperature. `vendor_modules_found` should be true when the manufacturer
modules are visible. `motion_enabled: false` is expected at this stage.

If module paths are null, share the output. That usually needs a vendor Python/path
adjustment, not a replacement OS or random pip-installed hardware library. If files are
not under `/home/pi/MasterPi`, update sdk_root in hardware/pi5_4gb.json to the actual
manufacturer SDK root. Keep the copied project separate from that root.

## 4. Prepare a separate robot environment

Still inside the Pi project folder:

```bash
bash scripts/setup_robot.sh
source .venv-robot/bin/activate
```

The script creates a project-local virtual environment with access to the vendor's existing
system packages, then repeats the read-only check. It does not alter Wi-Fi, system services,
the OS image, or motor settings. It starts no server and runs no movement.
It uses the current python3 installation; if the vendor SDK uses a dedicated environment,
we need to select that interpreter instead.

If creating a virtual environment fails because python3-venv/ensurepip is missing, stop
there and share the error. The read-only check can still run using the Pi's original Python.

Optional, when internet is available, install the robot HTTP API dependency:

```bash
bash scripts/setup_robot.sh --install-api
```

This installs only the robot requirements (Flask and its dependencies) into .venv-robot.
It does not install the Kaggle/ML packages or start a service. It may use an already installed
compatible Flask version from the vendor image.

## 5. Preview; do not move yet

```bash
python -m wafer_project robot-plan --lot-id W001 --destination ETCH
```

Expect missing calibration values. That is intentional: our first physical session still
needs measured grip/lift/drop poses and a short route. This preview imports no hardware SDK.
Do not enable motion or use robot-run --execute during onboarding.

Share the robot-check output and any setup error. The next work is supervised calibration
with one lightweight carrier and one destination; the physical design guide covers that stage.

## Packaging again on the Mac after source changes

```bash
cd "/Users/joshua/Desktop/ai-based wafer"
.venv/bin/python scripts/build_robot_bundle.py
```

This refreshes the robot bundle and companion checksum, preserving the original project
and forcing motion disabled in the exported configuration.
