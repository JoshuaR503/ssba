"""Plot recorded temperature data, excluding missing sensor readings."""

from pathlib import Path


def plot_temperature(csv_path: Path, output_path: Path, warning_c: float) -> None:
    # Keep these laptop-only dependencies out of the Pi server's import path.
    import pandas as pd
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data = pd.read_csv(csv_path)
    required = {"timestamp_utc", "temperature_c", "device", "status"}
    if not required.issubset(data.columns):
        raise ValueError("CSV is missing required temperature columns")
    data["timestamp_utc"] = pd.to_datetime(data["timestamp_utc"], utc=True, errors="coerce")
    data["temperature_c"] = pd.to_numeric(data["temperature_c"], errors="coerce")
    data = data[data["status"].isin(["ok", "warning"])].dropna(
        subset=["timestamp_utc", "temperature_c"]
    )
    data = data[data["temperature_c"].between(0, 150)]
    if data.empty:
        raise ValueError("No valid CPU temperature readings exist; nothing to plot")
    fig, axis = plt.subplots(figsize=(9, 4))
    try:
        for device, observations in data.groupby("device"):
            observations = observations.sort_values("timestamp_utc")
            axis.plot(observations["timestamp_utc"], observations["temperature_c"],
                      marker=".", label=device)
        axis.axhline(warning_c, color="orange", linestyle="--", label="Advisory threshold")
        axis.set(title="Recorded Raspberry Pi CPU temperature", xlabel="Time (UTC)",
                 ylabel="Temperature (°C)")
        axis.legend()
        fig.autofmt_xdate()
        fig.tight_layout()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=150)
    finally:
        plt.close(fig)
