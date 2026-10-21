# Documentation index

## Start here

- [Working pickup guide](working_pickup.md): current commands, targets and operating constraints.
- [AI and calibration guide](../llm_supervisor/README.md): image checks, API setup and calibration flags.
- [Beginner AI prompt](beginner_robot_prompt.md): a reusable prompt for investigating a robot and its project.
- [Project report](comprehensive_project_report.md): calibration, hardware limitations, AI integration and saved results.

## Pose records

- [Deposition — green](poses/deposition/README.md)
- [Metrology — blue/cyan](poses/metrology/README.md)
- [Etch — red](poses/etch/README.md)
- [Calibration history](../llm_supervisor/calibration_notes.md)

Each station folder contains photographs, control screenshots and a manifest. Historical photographs preserve earlier settings. Use the working guide and active pose configuration for the current targets.

## Technical and historical references

- [Connection guide](../ROBOT_CONNECTION_GUIDE.md): network setup and reconnection history.
- [Vendor software map](../ROBOT_SOFTWARE_MAP.md): source inspection of the installed robot application; some statements describe its initial inspection stage.
- [Earlier onboarding](../ROBOT_ONBOARDING.md): copying the scaffold onto the Pi, rather than the current Mac-run pickup workflow.
- [Camera findings](../llm_supervisor/findings/camera_visibility/README.md)
- [Dimensional feasibility](robot-model/dimensional-feasibility.md)
- [Session closeout](session_2026-10-17.md)

## Backup scope

This repository is **not a full robot operating-system backup**. It preserves project source, documentation, tracked pose evidence and configuration.

The local `robot-reference/MasterPi` folder is a copy of the vendor application from `/home/pi/MasterPi`. It is ignored by Git and is not uploaded with a normal push. It does not preserve the entire SD card, installed system packages or complete system-service configuration.

The generated `dist/masterpi-wafer-pi5.zip` is a project distribution bundle, not an OS image. Regenerate it before distribution; an existing bundle may predate the latest code.

A full robot restoration would require a separate verified SD-card image or equivalent system backup. Local ignored API credentials, captures and runtime logs also require separate handling if they need to be preserved. Selected JSON events are reproduced in the project report; its links to ignored runtime files may be unavailable in a fresh clone.

## Documentation cleanup candidates

The older onboarding and troubleshooting histories can be moved into an archive after updating their links and the bundle builder. Generated PyDoc can be regenerated. The root README can be shortened by linking to subsystem guides. These are proposed changes; this documentation update does not remove those files.

Keep active scripts, pose configurations, tests, calibration history, photographs and camera evidence. Review deliverables in `output/` before deciding whether to delete or publish them.
