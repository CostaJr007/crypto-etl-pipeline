import unittest
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

from transform.indicators import compute_indicators, detect_alerts


class TestIndicators(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        dates = pd.date_range(start="2024-01-01", periods=100, freq="1h")
        np.random.seed(42)
        price = 50000 + np.cumsum(np.random.randn(100) * 100)
        cls.df = pd.DataFrame({
            "symbol": "BTCUSDT",
            "interval": "1h",
            "open_time": dates,
            "open": price - 50,
            "high": price + 100,
            "low": price - 100,
            "close": price,
            "volume": np.random.rand(100) * 1000 + 500,
        })

    def test_compute_indicators_adds_columns(self):
        result = compute_indicators(self.df)
        expected = [
            "sma_20", "sma_50", "ema_12", "ema_26",
            "rsi_14", "macd", "macd_signal", "macd_histogram",
            "bb_upper", "bb_lower", "atr_14",
            "volume_sma", "returns", "log_returns", "volatility_20",
        ]
        for col in expected:
            self.assertIn(col, result.columns)

    def test_rsi_range(self):
        result = compute_indicators(self.df)
        valid_rsi = result["rsi_14"].dropna()
        self.assertTrue((valid_rsi >= 0).all())
        self.assertTrue((valid_rsi <= 100).all())

    def test_sma_values(self):
        result = compute_indicators(self.df)
        self.assertAlmostEqual(
            result["sma_20"].iloc[-1],
            result["close"].iloc[-20:].mean(),
            delta=0.5,
        )

    def test_detect_alerts(self):
        df = compute_indicators(self.df)
        alerts = detect_alerts(df)
        self.assertIsInstance(alerts, list)
        if alerts:
            self.assertIn("symbol", alerts[0])
            self.assertIn("signal", alerts[0])

    def test_empty_df_handled(self):
        empty = pd.DataFrame(columns=["symbol", "interval", "open_time", "open", "high", "low", "close", "volume"])
        result = compute_indicators(empty)
        self.assertTrue(result.empty)


class TestExtract(unittest.TestCase):

    def test_fetch_klines_returns_data(self):
        from extract.binance_client import fetch_klines

        end = datetime.utcnow()
        start = end - timedelta(days=1)
        rows = fetch_klines("BTCUSDT", "1h", start, end)
        self.assertIsInstance(rows, list)
        if rows:
            self.assertIn("open", rows[0])
            self.assertIn("close", rows[0])


class TestDatabaseInit(unittest.TestCase):

    def test_init_keeps_features_and_migrates_old_schema(self):
        from sqlalchemy import create_engine, text
        from load.database import init_database, upsert_features

        engine = create_engine("sqlite://")
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE features (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, "
                "interval TEXT NOT NULL, open_time TIMESTAMP NOT NULL, close REAL, "
                "UNIQUE(symbol, interval, open_time))"))
        init_database(engine)
        row = pd.DataFrame([{"symbol": "BTCUSDT", "interval": "1h", "open_time": "2024-01-01 00:00:00",
                             "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5}])
        upsert_features(engine, row)

        init_database(engine)  # second run must not wipe computed features
        with engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM features")).scalar()
            high = conn.execute(text("SELECT high FROM features")).scalar()
        self.assertEqual(count, 1)
        self.assertEqual(high, 2.0)


if __name__ == "__main__":
    unittest.main()
