import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from config.settings import SYMBOLS, INTERVALS, LOOKBACK_DAYS
from extract.binance_client import fetch_klines
from transform.indicators import compute_indicators, detect_alerts
from load.database import (
    get_engine,
    init_database,
    upsert_raw,
    upsert_features,
    save_alerts,
    start_pipeline_run,
    log_pipeline_run,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("pipeline")


def run_pipeline(
    symbols: list[str] | None = None,
    intervals: list[str] | None = None,
    days_back: int | None = None,
) -> dict:
    symbols = symbols or SYMBOLS
    intervals = intervals or INTERVALS
    days_back = days_back or LOOKBACK_DAYS

    engine = get_engine()
    Path("data").mkdir(exist_ok=True)
    init_database(engine)

    run_id = start_pipeline_run(engine)
    stats = {"run_id": run_id, "extracted": 0, "transformed": 0, "alerts": 0}

    try:
        for symbol in symbols:
            for interval in intervals:
                logger.info("Processing %s %s", symbol, interval)

                end_date = datetime.now(tz=timezone.utc).replace(tzinfo=None)
                start_date = end_date - timedelta(days=days_back)
                raw = fetch_klines(symbol, interval, start_date, end_date)
                if not raw:
                    continue

                df_raw = pd.DataFrame(raw)
                upsert_raw(engine, df_raw)
                stats["extracted"] += len(df_raw)

                df_features = compute_indicators(df_raw)
                upsert_features(engine, df_features)
                stats["transformed"] += len(df_features)

                alerts = detect_alerts(df_features)
                save_alerts(engine, alerts)
                stats["alerts"] += len(alerts)

                for a in alerts:
                    logger.info("ALERT | %s | %s | %.2f", a["symbol"], a["signal"], a["value"])

        log_pipeline_run(engine, run_id, "finished",
                         symbols_processed=stats["extracted"],
                         rows_extracted=stats["extracted"],
                         rows_transformed=stats["transformed"],
                         alerts_generated=stats["alerts"])
        logger.info("Pipeline run %d completed: %s", run_id, stats)
        return stats

    except Exception as e:
        logger.exception("Pipeline run %d failed", run_id)
        log_pipeline_run(engine, run_id, "failed", error=str(e))
        raise


if __name__ == "__main__":
    run_pipeline()
