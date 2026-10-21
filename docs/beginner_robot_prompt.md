# Prompt for understanding a robot and its project

Paste the following prompt into an AI assistant and provide the project files. If the assistant cannot inspect files or the robot directly, supply the requested files and command output. Never include API keys or passwords.

---

Help me understand this robot and its project. Assume I have no robotics experience. Explain things in plain language and investigate the available files before making assumptions.

Start by identifying:

1. The robot model, controller, operating system and existing vendor software.
2. What the project actually does, which scripts currently work, and which files describe older experiments.
3. How the computer communicates with the robot and camera.
4. Which commands move hardware, including scripts or imports that might move it automatically.
5. Whether joint values are requested targets or actual measured positions. Check whether usable position feedback exists; do not assume a successful command means successful movement.
6. Any damaged joints, unstable poses, calibration requirements or camera blind spots.
7. What is backed up, what exists only locally, and what would be needed to restore the robot.

Begin with read-only inspection. Do not move the robot, restart its control service, install packages or change settings without explaining the proposed action and receiving approval. Do not display credentials.

Then explain the project in this order: intended task → hardware → working movement sequence → calibration → AI features → observed results → limitations.

Distinguish features that were demonstrated from features merely proposed. Use saved logs, photographs and tests as evidence. Explain what each test proves and what it does not prove. Do not assume an unavailable camera view means an object is absent, or that a requested joint angle is a measured physical angle.

Finish with a short file map, the safest commands for getting started, and a list of missing information. Identify documentation that can be consolidated or archived without deleting important code or experimental evidence.

## Context for this repository

The current physical demonstration runs from the Mac against the existing Raspberry Pi service. Start with [the documentation index](README.md) and [the working pickup guide](working_pickup.md). Older onboarding instructions describe a separate project-copy workflow.

The setup uses green for deposition, blue/cyan for metrology and red for etch. ID4 is unresponsive and excluded from movement commands. The AI checks images around taught movements; it does not calculate new servo targets. Actual servo-position feedback was not established during the experiment.
