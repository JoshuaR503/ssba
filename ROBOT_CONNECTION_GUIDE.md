# Connecting the MasterPi robot to the Mac

Recorded: October 17, 2026 (Mac local date).

## Confirmed outcome

We successfully logged into the robot from the Mac using SSH over the home local area network (LAN). No paid VNC software, OS flashing, or robot movement was required.

| Item | Confirmed value |
| --- | --- |
| Hardware | Raspberry Pi 5 Model B Rev 1.0 |
| Robot hostname | `raspberrypi` |
| Login username | `pi` |
| Working SSH name | `raspberrypi.local` |
| Home LAN IPv4 address at connection time | `192.168.1.80` |
| Vendor software directory | `/home/pi/MasterPi` |
| Operating system shown at login | Debian GNU/Linux, aarch64 |

The user previously identified this robot as the 4 GB RAM model; memory capacity has not yet been verified through the terminal. The LAN IP may change after a reboot or router lease renewal.

## Default passwords

| Connection | Username | Default password |
| --- | --- | --- |
| Robot Wi-Fi hotspot `HW-xxxx` | Not required | `hiwonder` |
| SSH terminal login | `pi` | `raspberrypi` |
| Home Wi-Fi during LAN setup | Not required | Your own home Wi-Fi password |

These robot defaults apply unless changed.

## Networks and passwords: what each one means

- **Robot hotspot (`HW-xxxx`):** the robot creates its own Wi-Fi network. Connecting a phone to it allows initial setup. The documented default hotspot password is `hiwonder`; it initially failed during our attempts, but the phone later connected. We did not determine exactly why the earlier attempts failed.
- **Home Wi-Fi / LAN:** the robot joins the same home router as the Mac. WonderPi's LAN setup needs the **home Wi-Fi password** at this stage.
- **SSH login:** after reaching the robot, SSH asks for the Linux account password for user `pi`. This is separate from either Wi-Fi password. Default credentials: **username `pi`, password `raspberrypi`**. Use these unless you have changed them.

Do not put private home Wi-Fi passwords in this guide or in source control.

## LAN setup we worked through

1. Connected the phone to the robot's `HW-xxxx` hotspot successfully after earlier unsuccessful attempts.
2. Opened WonderPi and started its **LAN Mode** connection flow through the add-connection option.
3. Connected the phone to home Wi-Fi when the app requested a connection to the router.
4. Entered the home Wi-Fi password in the LAN setup flow.
5. Switched the phone back to `HW-xxxx` when WonderPi requested the robot hotspot, then returned to the app.
6. Returned the phone to home Wi-Fi and saw the robot in the app.
7. Kept the Mac on home Wi-Fi and tested SSH using the robot's hostname.

The app displayed repeated connection instructions and an “unable to join” message during the attempts. The conversation did not establish exactly which retry completed provisioning. The later successful SSH session and the robot's `192.168.1.80` address confirmed that LAN connectivity ultimately worked.

Seeing a robot entry in the app alone was not sufficient proof that it was reachable on the LAN.

## The SSH command that worked

On the **Mac**, opened Terminal and ran:

```bash
ssh -o ConnectTimeout=10 pi@raspberrypi.local
```

SSH resolved the hostname to an IPv6 address on the home network and displayed:

```text
The authenticity of host 'raspberrypi.local (...)' can't be established.
Are you sure you want to continue connecting (yes/no/[fingerprint])?
```

This was the first connection to that host from the Mac. We entered `yes`, which saved the host key in the Mac's SSH known-hosts file. For a future first connection, confirm that the hostname belongs to the intended Pi; if multiple Pis are present, the name alone may be ambiguous.

At this prompt:

```text
pi@raspberrypi.local's password:
```

Typed **`raspberrypi`** (the default SSH password) and pressed **Enter**. SSH does not display characters or dots while entering a password.

The login succeeded and displayed a Linux welcome banner and a prompt containing `pi@raspberrypi`. Commands entered at that point run **on the robot**, rather than on the Mac.

## How we confirmed the robot's identity and IP

Inside the SSH session, ran:

```bash
cat /proc/device-tree/model
hostname -I
ls ~
```

The model was:

```text
Raspberry Pi 5 Model B Rev 1.0
```

The first address returned by `hostname -I` was:

```text
192.168.1.80
```

The home directory contained `MasterPi`, `hiwonder-toolbox`, `board_demo`, and other vendor/system folders.

The model file has no trailing newline, so the model text and IP address appeared joined together in the pasted output. That was formatting, not a hardware or network problem.

## Problems encountered and what we learned

| Problem | What happened / resolution |
| --- | --- |
| VNC cost concern | Used the Mac's built-in SSH client to get a terminal. No VNC subscription was needed for this connection. |
| SSH to `192.168.149.1` appeared to hang | This is the documented robot hotspot address. The Mac was on the home network, where the robot ultimately had a different address. Used `raspberrypi.local` instead. |
| `hiwonder` was rejected for the hotspot | Forget/rejoin was attempted; later the phone connected successfully. The exact cause of the earlier rejection remains unknown. |
| Confusion over which password to enter | Home Wi-Fi password belongs in LAN provisioning; `hiwonder` joins `HW-xxxx`; `raspberrypi` is the default SSH password for user `pi`. |
| WonderPi repeatedly requested a Wi-Fi change | Followed the router/home Wi-Fi and robot hotspot switching flow. Exact app behavior depended on the setup stage. |
| App reported “unable to join” | We did not establish which network failed at that moment. Later successful SSH confirmed the final LAN connection. |
| Could not tap the robot or find its IP in WonderPi | App inspection did not yield a usable IP. Hostname-based SSH bypassed that obstacle. |
| Only `72:ef:5a:41:ca:c7` was visible | This is a MAC address, not an SSH IP address. Its relationship to the robot's active LAN interface was not independently verified. |
| Mac discovery did not initially find the Pi | Early hostname/service discovery and SSH probes of previously visible devices were inconclusive. A negative discovery result did not prove LAN setup had failed. |
| Suggested switching the Mac to the hotspot after LAN setup | That step was unnecessary once LAN connectivity worked. The successful connection kept the Mac on home Wi-Fi. |
| First SSH connection asked about authenticity | Accepted the host key with `yes`; this was not a password failure. |
| Password prompt looked inactive | SSH hides password input. Entering the password and pressing Enter completed login. |

## Reconnecting next time

1. Power on the robot and allow it to boot.
2. Keep the Mac on the same home network as the robot.
3. In Mac Terminal, run:

   ```bash
   ssh -o ConnectTimeout=10 pi@raspberrypi.local
   ```

4. At the password prompt, type **`raspberrypi`** and press **Enter**. Nothing appears while typing; this is normal. If you changed the password, use your replacement.

Alternatively, while its address remains unchanged:

```bash
ssh -o ConnectTimeout=10 pi@192.168.1.80
```

To end the SSH session and return to the Mac shell:

```bash
exit
```

To cancel a connection attempt that is stuck, press **Control+C**.

If the hostname stops working, check the router's connected-device list for the robot's current IP. The Mac's `arp -a` command shows discovered IPv4 neighbors, but is not a complete inventory of all Wi-Fi devices.

## Where we stopped

Connection and basic robot identity checks succeeded. No project files were copied to the robot, packages installed on it, OS reflashed, motor commands issued, or robot services changed during this connection session.

The following read-only checks were proposed next but their results have **not** yet been supplied:

```bash
python3 --version
free -h
ls ~/MasterPi
cat /sys/class/thermal/thermal_zone0/temp
```

The temperature value is in thousandths of a degree Celsius: `45000` means 45°C. These checks will inform project onboarding; they do not move the robot.
