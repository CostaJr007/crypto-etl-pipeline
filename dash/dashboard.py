import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from sqlalchemy import text

from load.database import get_engine

st.set_page_config(page_title="Crypto ETL Dashboard", layout="wide")
st.title("Crypto Data Pipeline Dashboard")

engine = get_engine()

with engine.connect() as conn:
    symbols = conn.execute(text("SELECT DISTINCT symbol FROM features ORDER BY symbol")).fetchall()
    symbols = [r[0] for r in symbols]

selected = st.sidebar.selectbox("Symbol", symbols if symbols else ["BTCUSDT"])
interval = st.sidebar.selectbox("Interval", ["1h", "4h", "1d"], index=1)
days = st.sidebar.slider("Days back", 1, 90, 30)

query = text("""
    SELECT open_time, open, high, low, close, volume,
           sma_20, sma_50, rsi_14, macd, macd_signal, macd_histogram,
           bb_upper, bb_lower, volatility_20
    FROM features
    WHERE symbol = :symbol AND interval = :interval
      AND open_time >= datetime('now', :days)
    ORDER BY open_time
""")

with engine.connect() as conn:
    df = pd.read_sql_query(
        query,
        conn,
        params={"symbol": selected, "interval": interval, "days": f"-{days} days"},
    )
    df["open_time"] = pd.to_datetime(df["open_time"])

if df.empty:
    st.warning("No data found. Run the pipeline first: `python -m pipeline.orchestrator`")
    st.stop()

cols = st.columns(4)
latest = df.iloc[-1]
cols[0].metric("Price", f"${latest['close']:,.2f}")
cols[1].metric("RSI (14)", f"{latest['rsi_14']:.1f}" if pd.notna(latest["rsi_14"]) else "N/A")
cols[2].metric("Volatility (20)", f"{latest['volatility_20']:.4f}" if pd.notna(latest["volatility_20"]) else "N/A")
cols[3].metric("Volume", f"{latest['volume']:,.0f}")

fig1 = make_subplots(
    rows=3, cols=1, shared_xaxes=True,
    vertical_spacing=0.05,
    row_heights=[0.5, 0.25, 0.25],
    subplot_titles=("Price + Bollinger Bands + MAs", "RSI (14)", "MACD"),
)

fig1.add_trace(go.Candlestick(
    x=df["open_time"], open=df["open"], high=df["high"],
    low=df["low"], close=df["close"], name="OHLC",
), row=1, col=1)

if df["bb_upper"].notna().any():
    fig1.add_trace(go.Scatter(x=df["open_time"], y=df["bb_upper"], line=dict(dash="dot", color="gray"), name="BB Upper"), row=1, col=1)
    fig1.add_trace(go.Scatter(x=df["open_time"], y=df["bb_lower"], line=dict(dash="dot", color="gray"), name="BB Lower"), row=1, col=1)

fig1.add_trace(go.Scatter(x=df["open_time"], y=df["sma_20"], line=dict(color="blue"), name="SMA 20"), row=1, col=1)
fig1.add_trace(go.Scatter(x=df["open_time"], y=df["sma_50"], line=dict(color="orange"), name="SMA 50"), row=1, col=1)

fig1.add_trace(go.Scatter(x=df["open_time"], y=df["rsi_14"], line=dict(color="purple"), name="RSI"), row=2, col=1)
fig1.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
fig1.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

fig1.add_trace(go.Bar(x=df["open_time"], y=df["macd_histogram"], name="Histogram"), row=3, col=1)
fig1.add_trace(go.Scatter(x=df["open_time"], y=df["macd"], line=dict(color="blue"), name="MACD"), row=3, col=1)
fig1.add_trace(go.Scatter(x=df["open_time"], y=df["macd_signal"], line=dict(color="red"), name="Signal"), row=3, col=1)

fig1.update_layout(height=800, showlegend=True, xaxis_rangeslider_visible=False)
st.plotly_chart(fig1, use_container_width=True)

st.subheader("Recent Alerts")
with engine.connect() as conn:
    alerts = pd.read_sql_query(
        text("SELECT * FROM alerts ORDER BY created_at DESC LIMIT 50"),
        conn,
    )
if not alerts.empty:
    st.dataframe(alerts, use_container_width=True)
else:
    st.info("No alerts generated yet.")

st.subheader("Pipeline Run History")
with engine.connect() as conn:
    runs = pd.read_sql_query(
        text("SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT 20"),
        conn,
    )
if not runs.empty:
    st.dataframe(runs, use_container_width=True)
