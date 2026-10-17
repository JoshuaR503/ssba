#!/usr/bin/env bash
# Project-local environment setup only. Never starts a server or sends motion commands.
set -euo pipefail

robot_project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$robot_project_dir"

install_api=false
if [[ "${1:-}" == "--install-api" && $# -eq 1 ]]; then
  install_api=true
elif [[ $# -ne 0 ]]; then
  echo "Usage: bash scripts/setup_robot.sh [--install-api]" >&2
  exit 2
fi

python3 - <<'PY'
import sys
from pathlib import Path
if sys.version_info < (3, 10):
    raise SystemExit('Python 3.10+ is required. Leave the vendor Python intact and share robot-check output.')
try:
    model = Path('/proc/device-tree/model').read_text().strip('\x00\n ')
except OSError:
    raise SystemExit('Run this setup inside the project folder ON THE PI, not on the Mac.')
if not model.startswith('Raspberry Pi 5 '):
    raise SystemExit('This bundle targets Raspberry Pi 5. Share robot-check output before installing.')
PY

if [[ ! -d .venv-robot ]]; then
  python3 -m venv --system-site-packages .venv-robot
fi
if [[ ! -f .venv-robot/pyvenv.cfg ]] || ! .venv-robot/bin/python - <<'PY'
from pathlib import Path
config = Path('.venv-robot/pyvenv.cfg').read_text().lower()
if 'include-system-site-packages = true' not in config:
    raise SystemExit('Existing .venv-robot does not inherit vendor packages. Preserve it and share the setup output.')
PY
then
  echo "Cannot reuse .venv-robot; no environment was deleted or reset." >&2
  exit 1
fi

if [[ "$install_api" == true ]]; then
  .venv-robot/bin/python -m pip install -r requirements-robot.txt
fi

.venv-robot/bin/python -m wafer_project robot-check
echo "Project environment prepared. Read the check results; this is not proof of hardware readiness."
echo "No motion or server was started. Activate with: source .venv-robot/bin/activate"
if [[ "$install_api" == false ]]; then
  echo "Optional API dependency install, once internet is available: bash scripts/setup_robot.sh --install-api"
fi
