import logging
from datetime import datetime, timedelta
from typing import Generator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config.settings import BINANCE_BASE_URL, BATCH_SIZE

logger = logging.getLogger(__name__)


def _session_with_retries() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    return session


def fetch_klines(
    symbol: str,
    interval: str,
    start_date: datetime,
    end_date: datetime,
) -> list[dict]:
    """Extract candlestick data from Binance public REST API."""
    session = _session_with_retries()
    start_ms = int(start_date.timestamp() * 1000)
    end_ms = int(end_date.timestamp() * 1000)
    all_rows: list[dict] = []

    logger.info("Extracting %s %s from %s to %s", symbol, interval, start_date.date(), end_date.date())

    while start_ms < end_ms:
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": BATCH_SIZE,
        }
        resp = session.get(
            f"{BINANCE_BASE_URL}/api/v3/klines",
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        data: list = resp.json()

        if not data:
            break

        for candle in data:
            all_rows.append({
                "symbol": symbol,
                "interval": interval,
                "open_time": datetime.utcfromtimestamp(candle[0] / 1000),
                "close_time": datetime.utcfromtimestamp(candle[6] / 1000),
                "open": float(candle[1]),
                "high": float(candle[2]),
                "low": float(candle[3]),
                "close": float(candle[4]),
                "volume": float(candle[5]),
                "quote_volume": float(candle[7]),
                "trades": int(candle[8]),
                "taker_buy_volume": float(candle[9]),
                "taker_buy_quote_volume": float(candle[10]),
            })

        start_ms = int(data[-1][6]) + 1

    logger.info("Extracted %d candles for %s %s", len(all_rows), symbol, interval)
    return all_rows


def batch_extract(
    symbols: list[str],
    intervals: list[str],
    days_back: int,
) -> Generator[tuple[str, str, list[dict]], None, None]:
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days_back)

    for symbol in symbols:
        for interval in intervals:
            rows = fetch_klines(symbol, interval, start_date, end_date)
            yield symbol, interval, rows
