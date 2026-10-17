"""Fetch the public Kaggle SECOM CSV and retain source/checksum information."""

import hashlib
import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

import requests

DOWNLOAD_URL = "https://www.kaggle.com/api/v1/datasets/download/paresh2047/uci-semcom"


def download_secom(output: Path) -> dict:
    if (output / "uci-secom.csv").exists():
        raise ValueError("SECOM CSV already exists; choose another output directory to preserve it")
    response = requests.get(DOWNLOAD_URL, timeout=45)
    response.raise_for_status()
    try:
        with ZipFile(BytesIO(response.content)) as archive:
            matches = [name for name in archive.namelist() if Path(name).name == "uci-secom.csv"]
            if len(matches) != 1:
                raise ValueError("Kaggle archive does not contain exactly one expected SECOM CSV")
            data = archive.read(matches[0])
    except BadZipFile as exc:
        raise ValueError("Kaggle returned no ZIP archive; authentication may be required") from exc
    output.mkdir(parents=True, exist_ok=True)
    (output / "kaggle-download.zip").write_bytes(response.content)
    (output / "uci-secom.csv").write_bytes(data)
    source = {
        "provider": "kaggle", "dataset": "paresh2047/uci-semcom", "url": DOWNLOAD_URL,
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "csv_sha256": hashlib.sha256(data).hexdigest(),
        "archive_sha256": hashlib.sha256(response.content).hexdigest(),
        "original_source": "https://archive.ics.uci.edu/dataset/179/secom",
        "original_citation": "McCann, M. & Johnston, A. (2008). SECOM. DOI: 10.24432/C54305.",
    }
    (output / "download_source.json").write_text(json.dumps(source, indent=2) + "\n")
    return source
