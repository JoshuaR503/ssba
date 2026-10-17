"""Associate demonstration carrier labels with real held-out dataset records."""

import hashlib
import json
from pathlib import Path

from .config import PROJECT_ROOT


def prepare_lot_analysis(lot_id: str, manifest_path: Path = PROJECT_ROOT / "data/lot_manifest.json") -> dict:
    import pandas as pd

    manifest = json.loads(manifest_path.read_text())
    if manifest.get("mapping_is_demonstration_only") is not True:
        raise ValueError("SECOM-to-carrier associations must be labeled demonstration-only")
    if lot_id not in manifest.get("lots", {}):
        raise ValueError("Carrier label is not in the demonstration lot manifest")
    source = manifest["lots"][lot_id]
    path = (manifest_path.parent / manifest["dataset_csv"]).resolve()
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["dataset_sha256"]:
        raise ValueError("Dataset checksum changed; review the carrier associations")
    record_id = source.get("record_id", "")
    if not isinstance(record_id, str) or not record_id.startswith("SECOM_"):
        raise ValueError("Invalid SECOM record identifier")
    try:
        index = int(record_id.removeprefix("SECOM_"))
    except ValueError as exc:
        raise ValueError("Invalid SECOM record identifier") from exc
    frame = pd.read_csv(path)
    if not 0 <= index < len(frame):
        raise ValueError("Record index is outside the dataset")
    columns = [str(value) for value in range(590)]
    record = frame.iloc[index]
    return {
        "mapping_is_demonstration_only": True,
        "record_source": manifest["record_source"],
        "normal_destination": source["normal_destination"],
        "payload": {
            "record_id": record_id,
            "features": [None if pd.isna(value) else float(value) for value in record[columns]],
            "context": {"lot_id": lot_id},
        },
        "next_step": "Operator reviews the AI recommendation; no destination is changed or movement executed automatically",
    }
