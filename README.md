# Crypto ETL Pipeline

**End-to-end Data Engineering pipeline for cryptocurrency market data — extraction, transformation, loading, and visualization.**

Built as a portfolio project demonstrating production-grade data engineering skills: API extraction, ETL orchestration, SQL schema design, technical indicator computation, and interactive dashboards.

## Architecture

```
Binance REST API
       │
       ▼
┌─────────────────┐
│    EXTRACT      │  ◄── binance_client.py
│   (requests)    │      Paginated API calls
└────────┬────────┘      Batch fetching
         │
         ▼
┌─────────────────┐
│   TRANSFORM     │  ◄── indicators.py
│   (pandas)      │     8 technical indicators
└────────┬────────┘     Feature engineering
         │
         ▼
┌─────────────────┐
│     LOAD        │  ◄── database.py
│  (SQLAlchemy)   │     SQLite/PostgreSQL
└────────┬────────┘     Upsert with dedup
         │
         ▼
┌─────────────────┐
│   DASHBOARD     │  ◄── dashboard.py
│  (Streamlit)    │     Interactive charts
└─────────────────┘     Real-time alerts
```

## ETL Pipeline

| Stage | Technology | Details |
|-------|-----------|---------|
| **Extract** | Binance REST API + `requests` | Pulls OHLCV candles for 5 pairs across 6 intervals, paginated, with retry logic |
| **Transform** | `pandas` + `numpy` | Computes SMA, EMA, RSI, MACD, Bollinger Bands, ATR, volatility, log returns |
| **Load** | `SQLAlchemy` + SQLite | Upserts into star-schema tables (`raw_klines`, `features`, `alerts`, `pipeline_runs`), deduplication via unique constraints |
| **Orchestrate** | Python scheduler | Serial pipeline with stats tracking, error handling, run history |
| **Visualize** | `plotly` + `Streamlit` | Candlestick charts, indicators overlay, RSI/MACD subplots, alerts table |

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/CostaJr007/crypto-etl-pipeline.git
cd crypto-etl-pipeline
pip install -r requirements.txt

# 2. Run the full ETL pipeline
python -m pipeline.orchestrator

# 3. Launch the dashboard
streamlit run dash/dashboard.py
```

## Docker

```bash
# Run pipeline once
docker compose run --rm pipeline

# Run dashboard
docker compose up dashboard
```

## Technical Indicators Engineered

| Indicator | Description | Use Case |
|-----------|-------------|----------|
| SMA 20/50 | Simple Moving Average | Trend direction |
| EMA 12/26 | Exponential Moving Average | Trend strength |
| RSI 14 | Relative Strength Index | Overbought/oversold |
| MACD | Moving Average Convergence Divergence | Momentum |
| Bollinger Bands | Volatility bands (20, 2σ) | Volatility regime |
| ATR 14 | Average True Range | Volatility magnitude |
| Volatility | 20-period std of returns | Risk measurement |
| Log Returns | Log price changes | Quantitative modeling |

## Project Structure

```
crypto-etl-pipeline/
├── config/
│   └── settings.py         # Configuration constants
├── extract/
│   └── binance_client.py   # Binance API data extraction
├── transform/
│   └── indicators.py       # Feature engineering & alerts
├── load/
│   └── database.py         # SQL schema + upsert logic
├── pipeline/
│   ├── orchestrator.py     # Main ETL orchestrator
│   └── scheduler.py        # Recurring job scheduler
├── dash/
│   └── dashboard.py        # Streamlit interactive dashboard
├── tests/
│   └── test_pipeline.py    # Unit tests
├── notebooks/
│   └── analysis.ipynb      # Jupyter exploration notebook
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## Skills Demonstrated

- **Data Extraction**: REST API pagination, retry logic, batch processing
- **Data Transformation**: pandas/numpy vectorized operations, financial feature engineering
- **Data Modeling**: Star schema, upsert patterns, deduplication, indexing
- **Orchestration**: ETL pipeline design, error handling, run tracking
- **Visualization**: Plotly candlestick charts, multi-panel dashboards
- **DevOps**: Docker, docker-compose, environment configuration
- **Testing**: Unit tests with real API validation

Author: Costa Junior — Ottawa, Canada
