import pandas as pd

import logging

from config import VALID_BOROUGHS, SEGMENT_COLUMNS, VOLUME_COLUMNS, HOURLY_COLUMNS


def _cast_dtypes(df:pd.DataFrame) -> pd.DataFrame:
    """Ensure columns are expected types."""
    numeric_cols = ["requestid", "yr", "m", "d", "hh", "mm", "vol", "segmentid"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    text_cols = ["boro", "wktgeom", "street", "fromst", "tost", "direction"]
    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).replace("nan", pd.NA)

    return df

def _get_date_columns(df:pd.DataFrame) -> pd.DataFrame:
    """Create date and time columns from existing columns."""
    # Hour and datetime columns
    time_df = df[["hh"]].copy()
    time_df["datetime"] = pd.to_datetime({
        "year": df["yr"],
        "month": df["m"],
        "day": df["d"],
        "hour": df["hh"],
        "minute": df["mm"]
    })

    # Day of week and weekend indicator
    time_df["day_of_week"] = time_df["datetime"].dt.dayofweek
    time_df["is_weekend"] = time_df["day_of_week"].isin([5, 6]) # Saturday=5, Sunday=6

    return time_df

def _process_boro(df:pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]: 
    # Process boro column
    boro_df = df[["boro"]].copy()
    boro_df["boro"] = boro_df["boro"].str.strip().str.title()

    invalid_mask = ~boro_df["boro"].isin(VALID_BOROUGHS)
    if invalid_mask.any():
        logging.warning("⚠ Unexpected boro values found. Check for typos or inconsistencies.")
        logging.warning(boro_df[invalid_mask]["boro"].value_counts())

    # Unique Boros Dataframe
    unique_boro = boro_df["boro"].dropna().unique()
    unique_boro_df = pd.DataFrame({"boro": unique_boro})
    unique_boro_df["boro_id"] = range(1, len(unique_boro_df) + 1)

    mapping = {boro: idx for (idx, boro) in enumerate(unique_boro_df["boro"], start=1)}
    boro_df["boro_id"] = boro_df["boro"].map(mapping)

    return boro_df[["boro_id"]], unique_boro_df

def _fix_volume(df:pd.DataFrame) -> pd.DataFrame:
    """Drop rows where vol is null or negative."""
    before = len(df)
    df = df.dropna(subset=["vol"]) # Drop Missing Values
    df = df[df["vol"] >= 0] # Drop Negative Counts
    after = len(df)
    dropped = before - after
    if dropped:
        logging.warning(f"⚠ Dropped {dropped:,} rows with null/negative vol")

    return df

def _normalize_strings(df:pd.DataFrame, cols:list[str]) -> pd.DataFrame:
    for col in cols:
        df[col] = df[col].str.strip().str.lower()

    return df


def _extract_segment_df(df:pd.DataFrame) -> pd.DataFrame:
    # Build the segment dataframe using only the intended segment columns.
    segment_df = df.loc[:, SEGMENT_COLUMNS].copy().drop_duplicates()

    ## More proper cleaning of the data
    # The normalizing value is the segment_id
    # Unfortunately, the corresponding data is not always entered the same.
    # But they represent the same street segment with some of the following differences
    # - Swap to/from
    # - Add direction to the street name
    # - Very slightly different geometries.
    # However, through exploration, none of these are different segments.
    # Thus we can just drop duplicates based on the segment_id and be good.
    segment_df.drop_duplicates(subset=["segmentid"], inplace=True)

    return segment_df

def _deduplicate_df(df):
    return df.drop_duplicates()

def transform(df:pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    # Step 1 | Check the datatypes of the columns
    df = _cast_dtypes(df)

    # Step 2 | Build Time and Date Columns
    time_df = _get_date_columns(df)
    df[["datetime", "day_of_week", "is_weekend"]] = time_df[["datetime", "day_of_week", "is_weekend"]]

    # Step 3 | Process boro column and create unique boro dataframe
    boro_key_df, unique_boro_df = _process_boro(df)
    df[["boro_id"]] = boro_key_df[["boro_id"]]

    # Step 4 | Validate the volume column
    df = _fix_volume(df)

    # Step 5 | Normalize String Columns
    df = _normalize_strings(df, ["street", "fromst", "tost"])

    # Step 6 | Deduplicate rows
    # 6a | Extract segment dataframe before deduplication
    segment_df = _extract_segment_df(df)
    # 6b | Combine into the volume dataframe
    main_df = df[VOLUME_COLUMNS].copy()
    main_df = _deduplicate_df(main_df)

    return main_df, segment_df, unique_boro_df

def create_hourly_aggregation_df(volume_df:pd.DataFrame) -> pd.DataFrame:
    """
    Create an aggregated table with total volume per segment per hour.
    With individual columns for day of week and weekend indicator to allow for more flexible analysis.
    """
    agg_df = volume_df[HOURLY_COLUMNS].copy()
    agg_df = agg_df.groupby([
        "segmentid",
        "direction",
        "day_of_week",
        "is_weekend",
        "hh"
    ], as_index=False)["vol"].sum()

    return agg_df