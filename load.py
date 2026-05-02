import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from config import DB_PATH, DB_LAST_LOAD_PATH


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON;")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS borough (
            boro_id INTEGER PRIMARY KEY,
            boro TEXT NOT NULL UNIQUE
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS segment (
            segmentid INTEGER PRIMARY KEY,
            boro_id INTEGER NOT NULL,
            wktgeom TEXT NOT NULL,
            street TEXT,
            fromst TEXT,
            tost TEXT,
            FOREIGN KEY (boro_id) REFERENCES borough(boro_id)
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS traffic_count (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requestid INTEGER,
            datetime TEXT NOT NULL,
            day_of_week INTEGER NOT NULL,
            is_weekend INTEGER NOT NULL,
            hh INTEGER NOT NULL,
            mm INTEGER NOT NULL,
            vol INTEGER NOT NULL,
            segmentid INTEGER NOT NULL,
            direction TEXT NOT NULL,
            FOREIGN KEY (segmentid) REFERENCES segment(segmentid)
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hourly_volume (
            segmentid INTEGER NOT NULL,
            direction TEXT NOT NULL,
            day_of_week INTEGER NOT NULL,
            is_weekend INTEGER NOT NULL,
            hh INTEGER NOT NULL,
            vol INTEGER NOT NULL,
            PRIMARY KEY (segmentid, direction, day_of_week, is_weekend, hh),
            FOREIGN KEY (segmentid) REFERENCES segment(segmentid)
        );
        """
    )


def _get_local_db_last_load() -> datetime | None:
    if not DB_LAST_LOAD_PATH.exists():
        return None
    data = json.loads(DB_LAST_LOAD_PATH.read_text(encoding="utf-8"))
    ts = data.get("db_last_loaded_at")
    if ts is None:
        return None
    return datetime.fromisoformat(ts)


def _save_db_last_load(api_last_updated_at: datetime) -> None:
    DB_LAST_LOAD_PATH.parent.mkdir(parents=True, exist_ok=True)
    DB_LAST_LOAD_PATH.write_text(
        json.dumps({"db_last_loaded_at": api_last_updated_at.isoformat()}, indent=2),
        encoding="utf-8",
    )


def is_db_current(api_last_updated: datetime) -> bool:
    local_last_loaded = _get_local_db_last_load()
    return local_last_loaded is not None and api_last_updated <= local_last_loaded


def _reset_database(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS hourly_volume;")
    conn.execute("DROP TABLE IF EXISTS traffic_count;")
    conn.execute("DROP TABLE IF EXISTS segment;")
    conn.execute("DROP TABLE IF EXISTS borough;")
    conn.commit()
    _create_schema(conn)


def _ensure_int_bool_columns(df, bool_columns):
    df = df.copy()
    for col in bool_columns:
        if col in df.columns:
            df[col] = df[col].astype(int)
    return df


def load_dataframes_to_db(main_df, segment_df, unique_boro_df, hourly_agg_df, api_last_updated: datetime):
    """Create the SQLite database and load the four pipeline tables.

    Writes to a temporary file first; the real database is replaced only when
    all tables load successfully, so a mid-load failure never corrupts it.
    """
    db_path = Path(DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = db_path.with_suffix(".db.tmp")
    try:
        conn = sqlite3.connect(tmp_path)
        try:
            _create_schema(conn)

            if not unique_boro_df.empty:
                unique_boro_df.to_sql("borough", conn, if_exists="append", index=False)

            if not segment_df.empty:
                if "direction" in segment_df.columns:
                    logging.warning("Removing stray 'direction' column from segment_df before loading segment table")
                    segment_df = segment_df.drop(columns=["direction"])
                segment_df.to_sql("segment", conn, if_exists="append", index=False)

            if not main_df.empty:
                main_df_for_sql = _ensure_int_bool_columns(main_df, ["is_weekend"])
                main_df_for_sql.to_sql("traffic_count", conn, if_exists="append", index=False)

            if not hourly_agg_df.empty:
                hourly_agg_df_for_sql = _ensure_int_bool_columns(hourly_agg_df, ["is_weekend"])
                hourly_agg_df_for_sql.to_sql("hourly_volume", conn, if_exists="append", index=False)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_traffic_segment ON traffic_count(segmentid);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_traffic_datetime ON traffic_count(datetime);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hourly_segment ON hourly_volume(segmentid);")
            conn.commit()
        finally:
            conn.close()

        # All writes succeeded — atomically replace the real database
        tmp_path.replace(db_path)
        _save_db_last_load(api_last_updated)
        logging.info("Loaded dataframes into %s", db_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
