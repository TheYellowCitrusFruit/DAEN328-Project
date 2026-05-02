# Docker Pipeline

This folder contains the ETL pipeline and a Docker Compose service for running it.

## Components

- `Dockerfile`
  - Builds a Python 3.14 image.
  - Installs dependencies from `requirements.txt`.
  - Copies the pipeline into the container.
  - Runs `python pipeline_runner.py`.

- `docker-compose.yml`
  - Defines the `etl` service.
  - Mounts the host `../data` directory into the container at `/app/data`.
  - Starts the pipeline service in the `docker_pipeline` folder.

- `requirements.txt`
  - Lists Python dependencies used by the pipeline.

- `.dockerignore`
  - Excludes build artifacts and the `data/` directory from the build context.

- `config.py`
  - Stores API endpoints, local paths, and metadata file locations.

- `extract.py`
  - Provides `get_api_last_updated()` to read dataset freshness from Socrata metadata.
  - Provides `is_csv_current(api_last_updated)` to check the raw CSV cache.
  - Provides `download_csv(api_last_updated)` to refresh the CSV when needed.
  - Saves the last API timestamp in `data/raw/last_fetch.json`.

- `transform.py`
  - Casts numeric and text column types.
  - Builds `datetime`, `day_of_week`, and `is_weekend` from `yr`, `m`, `d`, `hh`, `mm`.
  - Normalizes borough values and creates a unique borough lookup.
  - Drops null/negative `vol` rows.
  - Normalizes street / from / to string columns.
  - Deduplicates segment rows by `segmentid` and main volume rows.

- `load.py`
  - Creates the SQLite schema.
  - Provides `is_db_current(api_last_updated)` to check whether the DB is stale.
  - Writes pipeline results into SQLite and saves the last DB load timestamp.

- `pipeline_runner.py`
  - Orchestrates the process inside a single run.
  - Checks the API timestamp first.
  - Skips work if the DB is already current and no force flag is set.
  - Otherwise refreshes the CSV as needed, then runs transform + load.

  - `app.py`
    - Creates the Streamlit page with all figures

## Overall process

1. Start the pipeline service.
2. Read the dataset `rowsUpdatedAt` / `viewLastModified` timestamp from Socrata.
3. If the database is already current, the pipeline exits.
4. Otherwise, check the cached raw CSV.
5. If the CSV is stale or `force_api_call` is enabled, refresh from the API.
6. Transform data and load it into SQLite.
7. Uses the transformed data to predict future traffic

## How to start

From the repository root:

```powershell
cd docker_pipeline
docker compose up --build
```

This starts the named service `etl` defined in `docker-compose.yml`.

If you only want to start the pipeline service without rebuilding:

```powershell
cd docker_pipeline
docker compose up
```

To stop the service, press `Ctrl+C` or run:

```powershell
docker compose down
```

## Notes

- `data/` is mounted as a host volume so raw CSV cache and SQLite DB persist across container runs.
- Dates are treated as seconds since epoch from the API metadata, not milliseconds.
- Future services like a Streamlit dashboard can be added as extra Compose services.
