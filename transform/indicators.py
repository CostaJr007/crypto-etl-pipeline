import logging
from typing import Optional

import pandas as pd
import numpy as np

from config.settings import TECHNICAL_INDICATORS

logger = logging.getLogger(__name__)


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Engineer technical indicators on OHLCV data."""
    df = df.copy()
    df.sort_values(["symbol", "open_time"], inplace=True)

    for symbol in df["symbol"].unique():
        mask = df["symbol"] == symbol

        sma_20 = TECHNICAL_INDICATORS["sma_20"]["window"]
        sma_50 = TECHNICAL_INDICATORS["sma_50"]["window"]
        ema_12 = TECHNICAL_INDICATORS["ema_12"]["window"]
        ema_26 = TECHNICAL_INDICATORS["ema_26"]["window"]
        rsi_w = TECHNICAL_INDICATORS["rsi"]["window"]
        macd_f = TECHNICAL_INDICATORS["macd"]["fast"]
        macd_s = TECHNICAL_INDICATORS["macd"]["slow"]
        macd_sig = TECHNICAL_INDICATORS["macd"]["signal"]
        bb_w = TECHNICAL_INDICATORS["bb"]["window"]
        bb_std = TECHNICAL_INDICATORS["bb"]["std"]
        atr_w = TECHNICAL_INDICATORS["atr"]["window"]

        close = df.loc[mask, "close"]

        df.loc[mask, "sma_20"] = close.rolling(sma_20).mean()
        df.loc[mask, "sma_50"] = close.rolling(sma_50).mean()
        df.loc[mask, "ema_12"] = close.ewm(span=ema_12, adjust=False).mean()
        df.loc[mask, "ema_26"] = close.ewm(span=ema_26, adjust=False).mean()
        df.loc[mask, "rsi_14"] = _compute_rsi(close, rsi_w)
        df.loc[mask, "macd"] = _macd(close, macd_f, macd_s)
        df.loc[mask, "macd_signal"] = _macd_signal(close, macd_f, macd_s, macd_sig)
        df.loc[mask, "macd_histogram"] = df.loc[mask, "macd"] - df.loc[mask, "macd_signal"]
        df.loc[mask, "bb_upper"], df.loc[mask, "bb_lower"] = _bollinger_bands(close, bb_w, bb_std)

        high = df.loc[mask, "high"]
        low = df.loc[mask, "low"]
        df.loc[mask, "atr_14"] = _atr(high, low, close, atr_w)

        df.loc[mask, "volume_sma"] = df.loc[mask, "volume"].rolling(20).mean()
        df.loc[mask, "returns"] = close.pct_change()
        df.loc[mask, "log_returns"] = np.log(close / close.shift(1))
        df.loc[mask, "volatility_20"] = df.loc[mask, "returns"].rolling(20).std()

    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    return df


def _compute_rsi(series: pd.Series, window: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def _macd(series: pd.Series, fast: int, slow: int) -> pd.Series:
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    return ema_fast - ema_slow


def _macd_signal(series: pd.Series, fast: int, slow: int, signal: int) -> pd.Series:
    macd_line = _macd(series, fast, slow)
    return macd_line.ewm(span=signal, adjust=False).mean()


def _bollinger_bands(series: pd.Series, window: int, std: int) -> tuple[pd.Series, pd.Series]:
    sma = series.rolling(window).mean()
    std_dev = series.rolling(window).std()
    return sma + std * std_dev, sma - std * std_dev


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int) -> pd.Series:
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return true_range.ewm(alpha=1 / window, adjust=False).mean()


def detect_alerts(df: pd.DataFrame) -> list[dict]:
    """Detect trading signals from transformed data."""
    alerts = []
    latest = df.sort_values("open_time").groupby("symbol").tail(1)

    for _, row in latest.iterrows():
        if pd.notna(row.get("rsi_14")):
            if row["rsi_14"] <= 30:
                alerts.append({"symbol": row["symbol"], "signal": "RSI_OVERSOLD", "value": row["rsi_14"]})
            elif row["rsi_14"] >= 70:
                alerts.append({"symbol": row["symbol"], "signal": "RSI_OVERBOUGHT", "value": row["rsi_14"]})

        if pd.notna(row.get("macd_histogram")) and pd.notna(row.get("macd")):
            if row["macd_histogram"] > 0 and row["macd"] > row["macd_signal"]:
                alerts.append({"symbol": row["symbol"], "signal": "MACD_BULLISH", "value": row["macd_histogram"]})
            elif row["macd_histogram"] < 0 and row["macd"] < row["macd_signal"]:
                alerts.append({"symbol": row["symbol"], "signal": "MACD_BEARISH", "value": row["macd_histogram"]})

    return alerts
