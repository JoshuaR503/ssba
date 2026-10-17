"""Package an allowlisted robot-only project; never include environments or datasets."""

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    members = {}
    files = list((root / "wafer_project").glob("*.py")) + [
        root / name for name in (
            "config.json", "requirements-robot.txt", "hardware/pi5_4gb.json",
            "hardware/calibration.json", "data/example_tasks.json",
            "data/templates/physical_observations.csv", "scripts/setup_robot.sh",
            "ROBOT_ONBOARDING.md", "PHYSICAL_DESIGN.md",
        )
    ]
    for path in files:
        members[path.relative_to(root).as_posix()] = path.read_bytes()
    profile = json.loads(members["hardware/pi5_4gb.json"])
    profile["motion_enabled"] = False
    members["hardware/pi5_4gb.json"] = (json.dumps(profile, indent=2) + "\n").encode()
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "target": "masterpi_pi5_4gb", "motion_enabled": False,
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(members.items())},
    }
    members["bundle_manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    output = root / "dist/masterpi-wafer-pi5.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(members.items()):
            archive.writestr("masterpi-wafer/" + name, data)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".zip.sha256").write_text(f"{digest}  {output.name}\n")
    print(json.dumps({"bundle": str(output), "bytes": output.stat().st_size, "files": len(members),
                      "motion_enabled": False}, indent=2))


if __name__ == "__main__":
    main()
