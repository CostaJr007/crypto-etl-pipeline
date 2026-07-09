import logging

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from config.settings import DATABASE_URL

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS raw_klines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    open_time TIMESTAMP NOT NULL,
    close_time TIMESTAMP NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    quote_volume REAL,
    trades INTEGER,
    taker_buy_volume REAL,
    taker_buy_quote_volume REAL,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, interval, open_time)
);

CREATE INDEX IF NOT EXISTS idx_raw_klines_symbol
    ON raw_klines(symbol, interval);

CREATE INDEX IF NOT EXISTS idx_raw_klines_time
    ON raw_klines(open_time);

DROP TABLE IF EXISTS features;

CREATE TABLE features (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    open_time TIMESTAMP NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    sma_20 REAL,
    sma_50 REAL,
    ema_12 REAL,
    ema_26 REAL,
    rsi_14 REAL,
    macd REAL,
    macd_signal REAL,
    macd_histogram REAL,
    bb_upper REAL,
    bb_lower REAL,
    atr_14 REAL,
    volume_sma REAL,
    returns REAL,
    log_returns REAL,
    volatility_20 REAL,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, interval, open_time)
);

CREATE INDEX IF NOT EXISTS idx_features_symbol
    ON features(symbol, interval);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    signal TEXT NOT NULL,
    value REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP,
    status TEXT DEFAULT 'running',
    symbols_processed INTEGER DEFAULT 0,
    rows_extracted INTEGER DEFAULT 0,
    rows_transformed INTEGER DEFAULT 0,
    alerts_generated INTEGER DEFAULT 0,
    error_message TEXT
);
"""


def get_engine() -> Engine:
    return create_engine(DATABASE_URL, echo=False)


def init_database(engine: Engine) -> None:
    logger.info("Initializing database schema")
    with engine.begin() as conn:
        for statement in SCHEMA_SQL.split(";"):
            stmt = statement.strip()
            if stmt:
                conn.execute(text(stmt))
    logger.info("Database schema ready")


def upsert_raw(engine: Engine, df: pd.DataFrame) -> int:
    df = df.copy()
    for col in ("open_time", "close_time"):
        if col in df.columns:
            df[col] = df[col].astype(str)
    rows = 0
    with engine.begin() as conn:
        for _, row in df.iterrows():
            result = conn.execute(
                text("""
                    INSERT OR IGNORE INTO raw_klines
                        (symbol, interval, open_time, close_time, open, high, low, close,
                         volume, quote_volume, trades, taker_buy_volume, taker_buy_quote_volume)
                    VALUES (:symbol, :interval, :open_time, :close_time, :open, :high, :low, :close,
                            :volume, :quote_volume, :trades, :taker_buy_volume, :taker_buy_quote_volume)
                """),
                row.to_dict(),
            )
            rows += result.rowcount
    return rows


def upsert_features(engine: Engine, df: pd.DataFrame) -> int:
    df = df.copy()
    if "open_time" in df.columns:
        df["open_time"] = df["open_time"].astype(str)
    rows = 0
    cols = [
        "symbol", "interval", "open_time",
        "open", "high", "low", "close", "volume",
        "sma_20", "sma_50", "ema_12", "ema_26", "rsi_14",
        "macd", "macd_signal", "macd_histogram",
        "bb_upper", "bb_lower", "atr_14", "volume_sma",
        "returns", "log_returns", "volatility_20",
    ]
    available = [c for c in cols if c in df.columns]

    with engine.begin() as conn:
        for _, row in df[available].iterrows():
            result = conn.execute(
                text(f"""
                    INSERT OR REPLACE INTO features
                        ({", ".join(available)})
                    VALUES ({", ".join(f":{c}" for c in available)})
                """),
                row.to_dict(),
            )
            rows += result.rowcount
    return rows


def save_alerts(engine: Engine, alerts: list[dict]) -> int:
    if not alerts:
        return 0
    rows = 0
    with engine.begin() as conn:
        for alert in alerts:
            conn.execute(
                text("INSERT INTO alerts (symbol, signal, value) VALUES (:symbol, :signal, :value)"),
                alert,
            )
            rows += 1
    return rows


def log_pipeline_run(
    engine: Engine,
    run_id: int,
    status: str,
    **kwargs,
) -> None:
    with engine.begin() as conn:
        if status == "finished":
            conn.execute(
                text("""
                    UPDATE pipeline_runs
                    SET status = :status, finished_at = CURRENT_TIMESTAMP,
                        symbols_processed = :symbols_processed,
                        rows_extracted = :rows_extracted,
                        rows_transformed = :rows_transformed,
                        alerts_generated = :alerts_generated
                    WHERE id = :id
                """),
                {"id": run_id, "status": status, **kwargs},
            )
        elif status == "failed":
            conn.execute(
                text("""
                    UPDATE pipeline_runs
                    SET status = :status, finished_at = CURRENT_TIMESTAMP, error_message = :error
                    WHERE id = :id
                """),
                {"id": run_id, "status": status, "error": kwargs.get("error", "")},
            )


def start_pipeline_run(engine: Engine) -> int:
    with engine.begin() as conn:
        result = conn.execute(
            text("INSERT INTO pipeline_runs DEFAULT VALUES")
        )
        return result.lastrowid
