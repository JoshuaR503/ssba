"""Pi 5 driver tests use fake backends only. Never import the real vendor SDK."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wafer_project.models import LotTask
from wafer_project.pi5_driver import Pi5TransferRunner
from wafer_project.pi5_hardware import DEFAULT_PROFILE, inspect_hardware, load_profile, transfer_preview


class FakeBackend:
    def __init__(self, profile):
        self.commands = []

    def drive(self, step):
        self.commands.append(("drive", step))

    def servo(self, step):
        self.commands.append(("servo", step))

    def stop(self):
        self.commands.append(("stop", None))


class Pi5HardwareTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.profile = load_profile(DEFAULT_PROFILE)
        self.task = LotTask("W001", "ETCH")
        self.ready = lambda _: {key: True for key in (
            "model_matches", "memory_consistent_with_4gb", "python_supported", "vendor_modules_found"
        )}

    def calibrated_profile(self):
        profile = copy.deepcopy(self.profile)
        profile["motion_enabled"] = True
        calibration = {
            "calibrated": True, "calibration_id": "FAKE_TEST_ONLY",
            "pickup": [{"kind": "servo", "duration_s": 0.001, "positions": [[1, 1500]]}],
            "routes": {"ETCH": {
                "outbound": [{"kind": "drive", "duration_s": 0.001, "speed_mm_s": 10, "direction_deg": 90}],
                "place": [{"kind": "servo", "duration_s": 0.001, "positions": [[1, 1500]]}],
                "return": [{"kind": "drive", "duration_s": 0.001, "speed_mm_s": 10, "direction_deg": 270}],
            }},
        }
        path = self.root / "calibration.json"
        path.write_text(json.dumps(calibration))
        profile["calibration_file"] = str(path)
        return profile, calibration

    def test_default_preview_has_no_motor_side_effects_and_is_not_calibrated(self):
        with patch("wafer_project.pi5_driver.HiwonderPi5Backend", side_effect=AssertionError("must not load SDK")):
            result = Pi5TransferRunner(self.profile, self.root).execute(self.task)
        self.assertFalse(result["hardware_action_executed"])
        self.assertTrue(result["issues"])
        self.assertFalse(result["ready_for_hardware_check"])

    def test_execution_refuses_uncalibrated_plan_before_loading_sdk(self):
        factory = lambda _: self.fail("must not create backend")
        with self.assertRaisesRegex(ValueError, "not calibrated"):
            Pi5TransferRunner(self.profile, self.root, factory, self.ready).execute(self.task, execute=True)

    def test_wrong_hardware_refuses_even_a_calibrated_plan(self):
        profile, _ = self.calibrated_profile()
        with self.assertRaisesRegex(ValueError, "runtime"):
            Pi5TransferRunner(profile, self.root, lambda _: self.fail("must not create backend"), lambda _: {}).execute(self.task, execute=True)

    def test_limits_reject_bad_values_instead_of_sending_commands(self):
        profile, calibration = self.calibrated_profile()
        calibration["routes"]["ETCH"]["outbound"][0]["speed_mm_s"] = 999
        Path(profile["calibration_file"]).write_text(json.dumps(calibration))
        self.assertIn("speed_mm_s", " ".join(transfer_preview(self.task, profile)["issues"]))
        calibration["pickup"][0]["positions"] = [[1, 1500], [1, 1600]]
        Path(profile["calibration_file"]).write_text(json.dumps(calibration))
        self.assertIn("unique", " ".join(transfer_preview(self.task, profile)["issues"]))

    def test_command_completion_is_unverified_not_a_claim_of_delivery(self):
        profile, _ = self.calibrated_profile()
        backend = FakeBackend(profile)
        result = Pi5TransferRunner(profile, self.root, lambda _: backend, self.ready).execute(self.task, execute=True)
        self.assertEqual(result["outcome"], "executed_unverified")
        self.assertIsNone(result["physical_success_observed"])
        self.assertEqual(backend.commands[-1][0], "stop")
        self.assertEqual(len(result["steps"]), 4)
        self.assertTrue(Path(result["log_file"]).exists())

    def test_failure_stops_wheels_and_retains_failed_trial(self):
        profile, _ = self.calibrated_profile()
        backend = FakeBackend(profile)
        backend.drive = lambda _: (_ for _ in ()).throw(RuntimeError("fake motor error"))
        with self.assertRaisesRegex(RuntimeError, "fake motor error"):
            Pi5TransferRunner(profile, self.root, lambda _: backend, self.ready).execute(self.task, execute=True)
        self.assertEqual(backend.commands[-1][0], "stop")
        result = json.loads(next(self.root.glob("physical-*.json")).read_text())
        self.assertEqual(result["outcome"], "failed")

    def test_identity_check_reads_files_without_importing_sdk(self):
        model, memory = self.root / "model", self.root / "meminfo"
        model.write_text("Raspberry Pi 5 Model B Rev 1.0\x00")
        memory.write_text("MemTotal:        3900000 kB\n")
        with patch("wafer_project.pi5_hardware.find_vendor_modules", return_value={"common.mecanum": None}):
            result = inspect_hardware(self.profile, model, memory)
        self.assertTrue(result["model_matches"])
        self.assertTrue(result["memory_consistent_with_4gb"])
        self.assertFalse(result["vendor_modules_found"])
        self.assertFalse(result["hardware_action_executed"])

    def test_cancellation_stops_wheels_and_records_incomplete_transfer(self):
        profile, _ = self.calibrated_profile()
        backend = FakeBackend(profile)
        runner = Pi5TransferRunner(profile, self.root, lambda _: backend, self.ready)
        backend.drive = lambda _: runner.cancel()
        with self.assertRaises(InterruptedError):
            runner.execute(self.task, execute=True)
        self.assertEqual(backend.commands[-1][0], "stop")
        result = json.loads(next(self.root.glob("physical-*.json")).read_text())
        self.assertEqual(result["outcome"], "cancelled")
        self.assertIsNone(result["physical_success_observed"])
