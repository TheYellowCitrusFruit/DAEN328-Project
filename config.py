import os
from pathlib import Path

# Toggle debug logging via the DEBUG environment variable (e.g. DEBUG=true docker-compose up)
DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

# Socrata SODA2 endpoint — no authentication required for public datasets
# Supports .csv and .json extensions; we prefer CSV for flat tabular data
SODA2_BASE = "https://data.cityofnewyork.us/resource/7ym2-wayt"
SODA2_CSV_URL = f"{SODA2_BASE}.csv"
SODA2_JSON_URL = f"{SODA2_BASE}.json"  # available if needed

# Pagination — SODA2 uses $limit / $offset (max $limit is 50,000)
PAGE_SIZE = 50_000
REQUEST_DELAY_SEC = 1.0     # polite delay between paginated requests

# File paths
RAW_DIR = Path("data/raw")
DB_PATH = Path("data/traffic_data.db")

# Metadata URL for checking last update timestamp
SODA2_METADATA_URL = "https://data.cityofnewyork.us/api/views/7ym2-wayt.json"
LAST_FETCH_PATH = RAW_DIR / "last_fetch.json"
DB_LAST_LOAD_PATH = Path("data/db_last_load.json")

# Valid boroughs for validation
VALID_BOROUGHS = {"Manhattan", "Bronx", "Brooklyn", "Queens", "Staten Island"}

# Canonical column names coming from the SODA2 CSV endpoint
RAW_COLUMNS = [
    "requestid",
    "boro",
    "yr",
    "m",
    "d",
    "hh",
    "mm",

    "vol",

    "segmentid",
    "wktgeom",
    "street",
    "fromst",
    "tost",

    "direction",
]

SEGMENT_COLUMNS = [
    "segmentid",
    "wktgeom",
    "street",
    "fromst",
    "tost",
    "boro_id"
]

VOLUME_COLUMNS = [
    "requestid", # Non-Unique for Record fetch request.

    "datetime",
    "day_of_week",
    "is_weekend",
    "hh",
    "mm",

    "vol",

    "segmentid",
    "direction"
]

HOURLY_COLUMNS = [
    "day_of_week",
    "is_weekend",
    "hh",

    "vol",

    "segmentid",
    "direction",
]


DEBUG = True