import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

BINANCE_BASE_URL = "https://api.binance.com"

SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]
INTERVALS = ["1m", "5m", "15m", "1h", "4h", "1d"]
DEFAULT_INTERVAL = "1h"
LOOKBACK_DAYS = 90
BATCH_SIZE = 1000

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{PROJECT_ROOT}/data/crypto_warehouse.db",
)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

TECHNICAL_INDICATORS = {
    "sma_20": {"window": 20},
    "sma_50": {"window": 50},
    "ema_12": {"window": 12},
    "ema_26": {"window": 26},
    "rsi": {"window": 14},
    "macd": {"fast": 12, "slow": 26, "signal": 9},
    "bb": {"window": 20, "std": 2},
    "atr": {"window": 14},
}

ALERT_THRESHOLDS = {
    "rsi_oversold": 30,
    "rsi_overbought": 70,
    "volume_spike_multiplier": 3.0,
}
