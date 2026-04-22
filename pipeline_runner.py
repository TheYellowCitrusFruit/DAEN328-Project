import logging

from config import DEBUG
from extract import (
    extract_csv,
    get_api_last_updated,
    get_cached_csv_path,
    get_pandas_from_raw_csv,
    is_csv_current,
)
from transform import transform, create_hourly_aggregation_df
from load import load_dataframes_to_db, is_db_current

def configure_logging():
    class LevelFormatter(logging.Formatter):
        def format(self, record):
            if record.levelno == logging.INFO:
                self._style._fmt = "%(asctime)s - %(message)s"
            else:
                self._style._fmt = "%(asctime)s - %(levelname)s | %(message)s"
            return super().format(record)

    handler = logging.StreamHandler()
    handler.setFormatter(LevelFormatter())

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG if DEBUG else logging.INFO)
    logger.addHandler(handler)


def run_pipeline(force_api_call=False, force_db=False):
    ## Check if the pipeline needs to run (is it up to date)
    logging.info("Checking if the pipeline needs to run...")

    api_last_updated = get_api_last_updated()
    db_current = is_db_current(api_last_updated)

    # If the DB is up to date, don't need to run at all.
    if db_current and not force_api_call and not force_db:
        logging.info("Database is up to date with the API. No pipeline run needed.")
        return

    ## Running the pipeline
    logging.info("Pipeline needs to run. Starting execution...")
    if force_api_call:
        logging.info("force_api_call enabled: CSV will be refreshed from the API.")
    if force_db:
        logging.info("force_db enabled: database will be reloaded.")

    # Extract the data or use cached CSV if it is current to the API.
    csv_current = is_csv_current(api_last_updated)
    if not csv_current or force_api_call:
        logging.info("CSV is stale or force_api_call requested. Downloading raw CSV from API...")
        raw_csv_path = extract_csv(api_last_updated)
    else:
        logging.info("Using existing cached CSV file.")
        cached_csv = get_cached_csv_path()
        if cached_csv is None:
            logging.info("Cached CSV not found; downloading from API.")
            raw_csv_path = extract_csv()
        else:
            raw_csv_path = cached_csv

    # Load the raw CSV into a pandas DataFrame for transformation
    df = get_pandas_from_raw_csv(raw_csv_path)

    ## Transform data
    main_df, segment_df, unique_boro_df = transform(df)
    logging.debug("\n" + str(main_df.head()))
    logging.debug("\n" + str(segment_df.head()))
    logging.debug("\n" + str(unique_boro_df.head()))

    # Create Aggregated Hourly Volume DataFrame
    hourly_agg_df = create_hourly_aggregation_df(main_df)
    logging.debug("\n" + str(hourly_agg_df.head()))

    ## Load the data into the corresponding database tables.
    load_dataframes_to_db(main_df, segment_df, unique_boro_df, hourly_agg_df, api_last_updated)

    logging.info("Pipeline execution completed.")

if __name__ == "__main__":
    # Set logging configuration
    configure_logging()

    # Run the pipeline
    run_pipeline()