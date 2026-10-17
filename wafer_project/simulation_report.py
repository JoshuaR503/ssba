"""Run matched simulation suites and export reproducible inputs, results and plots."""

import hashlib
import importlib.metadata
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .simulation import CONTROLLERS, Simulation, load_simulation_config
from .workload import generate_workload

LABELS = {
    "onboard_fifo": "Onboard FIFO",
    "external_fifo": "External FIFO",
    "external_adaptive": "External available-first",
}
COLORS = ("#64748b", "#2563eb", "#10b981")


def create_plots(runs: pd.DataFrame, temperatures: pd.DataFrame, config: dict, output: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    models = list(config["pi_profiles"])
    scenarios = list(config["scenarios"])
    fig, axes = plt.subplots(len(models), len(scenarios), figsize=(15, 3.8 * len(models)), squeeze=False,
                             sharey=True)
    try:
        for row, model in enumerate(models):
            for column, scenario in enumerate(scenarios):
                axis = axes[row, column]
                subset = runs[(runs.pi_model == model) & (runs.scenario == scenario)]
                stats = subset.groupby("controller")["throughput_per_minute"].agg(["mean", "std"]).reindex(CONTROLLERS)
                axis.bar(np.arange(3), stats["mean"], yerr=stats["std"].fillna(0), capsize=3, color=COLORS)
                axis.set_xticks(np.arange(3), ["Onboard\nFIFO", "External\nFIFO", "External\navailable-first"], fontsize=8)
                axis.set_title(f"{model.upper()} · {scenario.replace('_', ' ')}", fontsize=11)
                axis.grid(axis="y", alpha=0.2)
                axis.set_axisbelow(True)
                if column == 0:
                    axis.set_ylabel("Simulated deliveries / minute")
        fig.suptitle("Synthetic wafer-handling simulation · matched workloads", fontsize=16)
        fig.text(0.5, 0.015, "Bars: mean across seeds; error bars: 1 standard deviation. Pi timing assumptions are not hardware benchmarks.", ha="center", fontsize=10)
        fig.tight_layout(rect=(0, 0.045, 1, 0.95))
        fig.savefig(output / "comparison.png", dpi=160)
    finally:
        plt.close(fig)

    seed = int(temperatures.seed.min())
    thermal_scenarios = [name for name in ("normal", "warm_cpu") if name in scenarios] or scenarios[:1]
    fig, axes = plt.subplots(len(thermal_scenarios), len(models), figsize=(12, 7), squeeze=False, sharey=True)
    try:
        for row, scenario in enumerate(thermal_scenarios):
            for column, model in enumerate(models):
                axis = axes[row, column]
                for controller, color in zip(CONTROLLERS, COLORS):
                    data = temperatures[(temperatures.pi_model == model) & (temperatures.scenario == scenario)
                                        & (temperatures.seed == seed) & (temperatures.controller == controller)]
                    axis.plot(data.time_seconds, data.temperature_c, color=color, label=LABELS[controller])
                axis.axhline(config["temperature_warning_c"], linestyle="--", color="#d97706", label="Advisory threshold")
                axis.set(title=f"{model.upper()} · {scenario.replace('_', ' ')}", xlabel="Simulation time (seconds)", ylabel="Synthetic CPU temperature (°C)")
                axis.grid(alpha=0.2)
        axes[0, 0].legend(fontsize=8)
        fig.suptitle(f"Illustrative thermal model · seed {seed} · not sensor measurements", fontsize=15)
        fig.tight_layout(rect=(0, 0, 1, 0.95))
        fig.savefig(output / "temperature.png", dpi=160)
    finally:
        plt.close(fig)


def run_suite(config_path: Path, output: Path, seeds: int = 30, lots: int = 24,
              starting_seed: int = 20261012) -> dict:
    if seeds <= 0 or lots <= 0:
        raise ValueError("seeds and lots must be greater than zero")
    config = load_simulation_config(config_path)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output directory is not empty; choose a new directory to preserve previous results")
    output.mkdir(parents=True, exist_ok=True)
    seed_numbers = list(range(starting_seed, starting_seed + seeds))
    workloads = {seed: generate_workload(seed, lots, config) for seed in seed_numbers}
    inputs = pd.DataFrame([lot.to_dict() for workload in workloads.values() for lot in workload])
    inputs.to_csv(output / "workload.csv", index=False)
    summaries, trials, temperatures = [], [], []
    for seed, workload in workloads.items():
        for model in config["pi_profiles"]:
            for scenario in config["scenarios"]:
                for controller in CONTROLLERS:
                    summary, lot_rows, temperature_rows = Simulation(
                        workload, config, model, controller, scenario
                    ).run()
                    summaries.append(summary)
                    trials.extend(lot_rows)
                    temperatures.extend(temperature_rows)
    runs = pd.DataFrame(summaries)
    runs.to_csv(output / "run_summary.csv", index=False)
    pd.DataFrame(trials).to_csv(output / "lot_results.csv", index=False)
    thermal = pd.DataFrame(temperatures)
    thermal.to_csv(output / "temperature_simulated.csv", index=False)
    groups = ["pi_model", "scenario", "controller"]
    aggregate = runs.groupby(groups, sort=False).agg(
        runs=("run_id", "count"), mean_delivered=("delivered", "mean"),
        mean_pending=("pending", "mean"), mean_failed=("failed", "mean"),
        mean_throughput=("throughput_per_minute", "mean"),
        throughput_std=("throughput_per_minute", "std"),
        mean_delivery_fraction=("delivery_fraction", "mean"),
        mean_total_seconds_finished_only=("mean_total_seconds_finished_only", "mean"),
        mean_command_seconds_finished_only=("mean_command_seconds_finished_only", "mean"),
        maximum_synthetic_temperature_c=("max_temperature_c", "max"),
        mean_warning_samples=("temperature_warning_samples", "mean"),
    ).reset_index()
    aggregate.to_csv(output / "aggregate_summary.csv", index=False)
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source": "synthetic", "physical_hardware_used": False,
        "total_runs": len(runs), "lots_per_workload": lots, "seeds": seed_numbers,
        "workload_sha256": hashlib.sha256((output / "workload.csv").read_bytes()).hexdigest(),
        "packages": {name: importlib.metadata.version(name) for name in ("simpy", "pandas", "matplotlib", "numpy")},
        "assumptions": config,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    create_plots(runs, thermal, config, output)
    lines = [
        "# Synthetic wafer-handling simulation results", "",
        f"Executed {len(runs)} runs: {len(config['pi_profiles'])} Pi profiles × 3 controllers × "
        f"{len(config['scenarios'])} scenarios × {seeds} matched workload seeds.",
        f"Each workload contains {lots} lots; each run observes {config['horizon_seconds']} simulated seconds.", "",
        "All workloads, physical transfer times, failure outcomes, network delays, and CPU temperatures are synthetic.",
        "The target robot is a Raspberry Pi 5 with 4 GB RAM. Simulation timings remain illustrative assumptions, not hardware measurements.", "",
        "| Pi profile | Scenario | Controller | Mean delivered | Deliveries/min | Std. deviation |", "| --- | --- | --- | ---: | ---: | ---: |",
    ]
    for row in aggregate.itertuples(index=False):
        deviation = 0 if pd.isna(row.throughput_std) else row.throughput_std
        lines.append(f"| {row.pi_model} | {row.scenario} | {LABELS[row.controller]} | {row.mean_delivered:.2f} | {row.mean_throughput:.3f} | {deviation:.3f} |")
    lines += [
        "", f"![Throughput comparison](<{(output / 'comparison.png').resolve()}>)", "",
        f"![Synthetic temperature traces](<{(output / 'temperature.png').resolve()}>)", "",
        "## Interpretation and limitations", "",
        "- Onboard FIFO vs external FIFO isolates modeled communication/decision overhead under the same policy.",
        "- External FIFO vs external available-first compares policies under the same network assumptions.",
        "- In the network outage, already accepted transfers finish; new external commands wait for the link to return.",
        "- In a station outage, a transfer already in transit waits if its destination is unavailable at delivery.",
        "- Available-first can reorder eligible lots; it never substitutes one fabrication process for another.",
        "- Transfer duration includes pickup, travel, drop-off and return. One robot moves one lot at a time.",
        "- Each destination has one receiving slot, occupied through transfer and subsequent simulated processing.",
        "- Handling failures use the same per-lot random draw in every matched run; there are no retries.",
        "- Thermal behavior uses an illustrative first-order model; the Pi 5's actual thermal response has not been measured.",
        "- Temperature warnings are advisory only. No simulated thermal throttling or physical temperature measurement occurs.",
        "- Throughput is successful simulated deliveries divided by the entire observation window, not simulated processing completions.",
        "- Pending and in-progress lots are retained in lot_results.csv. Latency means include finished lots only and can be biased by unfinished work.",
        "- Charts show variation across seeds (one standard deviation), not confidence intervals or physical measurement uncertainty.",
        "- The simulator uses the same choose_next function as the starter scheduler; network behavior is modeled with SimPy, not real HTTP.",
        "", "## Reproducibility", "",
        "See manifest.json for seed numbers, package versions, dataset checksum and the complete assumptions snapshot.",
        "workload.csv is the generated input dataset; run_summary.csv and lot_results.csv contain outcomes.",
        "temperature_simulated.csv is kept separate from the real-sensor log data/logs/temperature.csv.", "",
    ]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return {"runs": len(runs), "lot_observations": len(trials), "output": str(output.resolve())}
