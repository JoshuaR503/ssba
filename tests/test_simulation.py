"""Check event timing, fair comparisons, horizon accounting and simulated telemetry."""

import copy
import unittest
from pathlib import Path

from wafer_project.simulation import Simulation, load_simulation_config
from wafer_project.workload import SimulatedLot, generate_workload

ROOT = Path(__file__).resolve().parent.parent


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.config = load_simulation_config(ROOT / "simulation_config.json")
        self.config["horizon_seconds"] = 100
        self.config["failure_probability"] = 0
        self.config["pi_profiles"]["pi5"] = {"ram_gb": 4, "onboard_decision_seconds": 0, "command_handling_seconds": 0}
        self.config["laptop_decision_seconds"] = 0
        self.config["network"] = {"round_trip_seconds": 0, "jitter_seconds": 0}
        self.config["scenarios"]["normal"] = {"station_outages": [], "network_outages": []}
        self.lots = [SimulatedLot(7, "W001", "ETCH", 0, 10, 5, 0.5),
                     SimulatedLot(7, "W002", "DEPOSITION", 0, 10, 5, 0.5)]

    def run_case(self, controller="onboard_fifo", scenario="normal", lots=None):
        return Simulation(lots or self.lots, self.config, "pi5", controller, scenario).run()

    def test_identical_policy_with_zero_network_overhead_has_identical_lot_outcomes(self):
        local, local_rows, _ = self.run_case()
        external, external_rows, _ = self.run_case("external_fifo")
        self.assertEqual(local["delivered"], 2)
        self.assertEqual(local["throughput_per_minute"], external["throughput_per_minute"])
        self.assertEqual([row["completion_seconds"] for row in local_rows],
                         [row["completion_seconds"] for row in external_rows])

    def test_network_outage_blocks_external_only(self):
        self.config["scenarios"]["disconnected"] = {
            "station_outages": [], "network_outages": [{"start": 0, "end": 1000}]
        }
        self.assertEqual(self.run_case(scenario="disconnected")[0]["delivered"], 2)
        summary, rows, _ = self.run_case("external_fifo", "disconnected")
        self.assertEqual(summary["pending"], 2)
        self.assertEqual(summary["delivered"], 0)
        self.assertTrue(all(row["completion_seconds"] is None for row in rows))

    def test_adaptive_selects_other_eligible_lot_during_station_outage(self):
        self.config["horizon_seconds"] = 25
        self.config["scenarios"]["blocked"] = {
            "station_outages": [{"station": "ETCH", "start": 0, "end": 1000}], "network_outages": []
        }
        self.assertEqual(self.run_case("external_fifo", "blocked")[0]["delivered"], 0)
        summary, rows, _ = self.run_case("external_adaptive", "blocked")
        self.assertEqual(summary["delivered"], 1)
        self.assertEqual(rows[1]["destination"], "DEPOSITION")
        self.assertEqual(rows[0]["outcome"], "pending")

    def test_in_transit_outage_delays_delivery(self):
        self.config["scenarios"]["transit"] = {
            "station_outages": [{"station": "ETCH", "start": 5, "end": 40}], "network_outages": []
        }
        _, rows, _ = self.run_case(scenario="transit")
        self.assertEqual(rows[0]["completion_seconds"], 40)

    def test_horizon_retains_in_progress_and_not_arrived_lots(self):
        self.config["horizon_seconds"] = 5
        lots = [self.lots[0], SimulatedLot(7, "W003", "METROLOGY", 20, 10, 5, 0.5)]
        summary, rows, _ = self.run_case(lots=lots)
        self.assertEqual(summary["arrived"], 1)
        self.assertEqual(summary["in_progress"], 1)
        self.assertEqual(summary["not_arrived"], 1)
        self.assertEqual(summary["delivered"], 0)
        self.assertIsNone(rows[0]["completion_seconds"])

    def test_warning_and_synthetic_provenance_are_explicit(self):
        _, _, thermal = self.run_case(scenario="warm_cpu")
        self.assertEqual(thermal[0]["temperature_c"], 78)
        self.assertEqual(thermal[0]["status"], "simulated_warning")
        self.assertTrue(all(row["source"] == "synthetic" for row in thermal))

    def test_seeded_input_is_repeatable_and_simulator_does_not_mutate_it(self):
        lots = generate_workload(42, 10, self.config)
        self.assertEqual(lots, generate_workload(42, 10, self.config))
        before = copy.deepcopy(lots)
        self.run_case(lots=lots)
        self.assertEqual(lots, before)


if __name__ == "__main__":
    unittest.main()
