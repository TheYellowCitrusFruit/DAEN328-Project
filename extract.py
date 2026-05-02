## Extract data from the source
# Imports
import json
from datetime import datetime, timezone

import pandas as pd
import requests

import time
from pathlib import Path

import logging

from config import (
    PAGE_SIZE,
    REQUEST_DELAY_SEC,
    RAW_DIR,
    SODA2_CSV_URL,
    SODA2_METADATA_URL,
    LAST_FETCH_PATH,
)


def get_api_last_updated() -> datetime:
    resp = requests.get(SODA2_METADATA_URL, timeout=30)
    resp.raise_for_status()
    payload = resp.json()

    # Socrata metadata for this dataset exposes the latest row update timestamp
    # in `rowsUpdatedAt`. If that is missing, fall back to `viewLastModified`.
    ts = payload.get("rowsUpdatedAt") or payload.get("viewLastModified")
    if ts is None:
        raise ValueError("Could not determine API last-updated timestamp")
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _get_local_last_fetch() -> datetime | None:
    if not LAST_FETCH_PATH.exists():
        return None
    data = json.loads(LAST_FETCH_PATH.read_text(encoding="utf-8"))
    ts = data.get("api_last_updated_at")
    if ts is None:
        return None
    return datetime.fromisoformat(ts)


def _save_last_fetch(api_last_updated_at: datetime) -> None:
    LAST_FETCH_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAST_FETCH_PATH.write_text(
        json.dumps({"api_last_updated_at": api_last_updated_at.isoformat()}, indent=2),
        encoding="utf-8",
    )


def is_csv_current(api_last_updated: datetime) -> bool:
    existing_csv = _check_existing_csv()
    if existing_csv is None:
        return False

    local_last_updated = _get_local_last_fetch()
    return local_last_updated is not None and api_last_updated <= local_last_updated


def extract_csv(api_last_updated: datetime | None = None) -> Path:
    if api_last_updated is None:
        api_last_updated = get_api_last_updated()
    logging.info("Starting data extraction...")
    csv_path = _extract_paginated_csv()
    _save_last_fetch(api_last_updated)
    logging.info(f"✓ Data extraction completed. CSV saved to: {csv_path}")
    return csv_path


def _extract_paginated_csv(
    page_size: int = PAGE_SIZE,
    delay: float = REQUEST_DELAY_SEC,
    raw_dir: Path = RAW_DIR,
) -> Path:
    """
    Fetch all rows from the SODA2 CSV endpoint using $limit/$offset pagination.
    No authentication required.

    Each page is a CSV chunk; they are concatenated into a single raw CSV file.

    Parameters
    ----------
    page_size : int
        Number of rows per request (SODA2 max is 50,000).
    delay : float
        Seconds to wait between requests.
    raw_dir : Path
        Directory to save the raw CSV.

    Returns
    -------
    Path to the saved CSV file.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_path = raw_dir / "traffic_volume_raw.csv"
    offset = 0
    page = 1
    total_rows = 0
    first_page = True

    with open(out_path, "w", encoding="utf-8", newline="") as f_out:
        while True:
            params = {"$limit": page_size, "$offset": offset, "$order": "requestid"}
            logging.info(f"  Page {page}: offset={offset:,} …")

            resp = requests.get(SODA2_CSV_URL, params=params, timeout=120)
            resp.raise_for_status()

            text = resp.text
            lines = text.splitlines()

            if first_page:
                # Write header + data rows
                f_out.write(text)
                if not text.endswith("\n"):
                    f_out.write("\n")
                data_rows = len(lines) - 1  # subtract header
                first_page = False
            else:
                # Skip the header row on subsequent pages
                data_only = "\n".join(lines[1:])
                if data_only:
                    f_out.write(data_only)
                    if not data_only.endswith("\n"):
                        f_out.write("\n")
                data_rows = len(lines) - 1

            total_rows += data_rows
            logging.info(f"  {data_rows:,} rows (total: {total_rows:,})")

            if data_rows < page_size:
                break  # last page

            offset += page_size
            page += 1
            time.sleep(delay)

    size_mb = out_path.stat().st_size / (1024 * 1024)
    logging.info(f"✓ Extracted {total_rows:,} rows → {out_path} ({size_mb:.1f} MB)")
    return out_path

def _check_existing_csv(raw_dir: Path = RAW_DIR) -> Path | None:
    """
    Check if the raw CSV file already exists.

    Returns
    -------
    Path to the existing CSV file if it exists, else None.
    """
    existing_path = raw_dir / "traffic_volume_raw.csv"
    if existing_path.exists():
        logging.info(f"✓ Found existing CSV file: {existing_path}")
        return existing_path
    return None


def get_cached_csv_path() -> Path | None:
    return _check_existing_csv()


def get_pandas_from_raw_csv(csv_path: Path):
    """
    Load the raw CSV file into a pandas DataFrame.

    Parameters
    ----------
    csv_path : Path
        Path to the raw CSV file to load.
    """
    logging.info(f"Loading raw CSV from {csv_path} into pandas DataFrame...")
    try:
        df = pd.read_csv(csv_path)
        logging.info(f"✓ Loaded raw csv with {len(df)} rows into DataFrame.")
        return df

    except Exception as e:
        logging.error(f"⚠ Failed to load CSV into DataFrame: {e}")
        raise