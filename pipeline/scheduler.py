import logging
import time

from pipeline.orchestrator import run_pipeline
from config.settings import SYMBOLS

logger = logging.getLogger("scheduler")

SCHEDULE_INTERVAL_MINUTES = 60


def run_forever(interval_minutes: int = SCHEDULE_INTERVAL_MINUTES) -> None:
    logger.info("Scheduler started — running every %d minutes", interval_minutes)

    while True:
        try:
            logger.info("Scheduled ETL run triggered")
            run_pipeline(symbols=SYMBOLS[:2], intervals=["1h", "4h"], days_back=7)
        except Exception:
            logger.exception("Scheduled run failed, retrying in %d minutes", interval_minutes)

        time.sleep(interval_minutes * 60)


if __name__ == "__main__":
    run_forever()
