"""
Mark Minervini's Trend Template Stock Screener
===============================================
Modernised Streamlit application with:
  - Corrected indicator calculations (RS, RSI, MACD, ADX, etc.)
  - Batch downloading via yfinance for speed
  - Concurrent processing with ThreadPoolExecutor
  - Streamlit caching to avoid redundant API calls
  - Modern UI with tabs, metrics, interactive Plotly charts
"""

import datetime
import io
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from indicators import (
    TrendTemplate,
    relative_strength,
    sma,
    ema,
)

# ──────────────────────────────────────────────────────────────
# Page config  (must be the first Streamlit call)
# ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Minervini Stock Screener",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────
INDEX_TICKERS = {
    "S&P 500": "^GSPC",
    "NASDAQ": "^IXIC",
    "DOW": "^DJI",
}

MAX_WORKERS = 8  # concurrent yfinance downloads


# ──────────────────────────────────────────────────────────────
# Data fetching  (cached to avoid repeated API calls)
# ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def get_ticker_list(index_name: str) -> list[str]:
    """
    Fetch the list of tickers for the selected index.
    Falls back to a static list on network error.
    """
    try:
        if index_name == "S&P 500":
            table = pd.read_html(
                "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
            )[0]
            return sorted(table["Symbol"].str.replace(".", "-", regex=False).tolist())
        elif index_name == "NASDAQ":
            from yahoo_fin import stock_info as si
            return sorted(si.tickers_nasdaq())
        elif index_name == "DOW":
            from yahoo_fin import stock_info as si
            return sorted(si.tickers_dow())
    except Exception:
        pass
    # Fallback: small default list so the app doesn't crash
    return ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
            "BRK-B", "JPM", "V", "UNH", "JNJ", "WMT", "PG", "MA"]


@st.cache_data(ttl=3600, show_spinner=False)
def download_index_data(ticker: str, period: str) -> pd.DataFrame:
    """Download index benchmark data (cached)."""
    return yf.download(ticker, period=period, progress=False, auto_adjust=True)


def download_batch(tickers: list[str], period: str) -> dict[str, pd.DataFrame]:
    """
    Download historical data for a batch of tickers using yfinance's
    multi-ticker download (much faster than one-at-a-time).
    """
    data: dict[str, pd.DataFrame] = {}
    if not tickers:
        return data

    try:
        # yfinance multi-download
        raw = yf.download(
            tickers,
            period=period,
            group_by="ticker",
            progress=False,
            auto_adjust=True,
            threads=True,
        )

        if isinstance(raw.columns, pd.MultiIndex):
            for ticker in tickers:
                try:
                    df = raw[ticker].dropna(how="all")
                    if len(df) >= 200:
                        data[ticker] = df
                except (KeyError, Exception):
                    continue
        elif len(tickers) == 1:
            if len(raw) >= 200:
                data[tickers[0]] = raw
    except Exception:
        # Fallback: download one by one
        for ticker in tickers:
            try:
                df = yf.download(ticker, period=period, progress=False, auto_adjust=True)
                if len(df) >= 200:
                    data[ticker] = df
            except Exception:
                continue

    return data


# ──────────────────────────────────────────────────────────────
# Screening engine
# ──────────────────────────────────────────────────────────────

def run_screen(
    index_name: str,
    min_volume: float,
    min_price: float,
    period: str,
    min_rs_rating: float,
    progress_callback=None,
) -> pd.DataFrame:
    """
    Screen stocks against Minervini's Trend Template + extra indicators.
    Uses batch downloading and concurrent indicator computation for speed.
    """
    tickers = get_ticker_list(index_name)

    # 1. Download index benchmark
    index_ticker = INDEX_TICKERS[index_name]
    index_df = download_index_data(index_ticker, period)
    if index_df is None or index_df.empty:
        st.error("Failed to download index data. Please try again.")
        return pd.DataFrame()

    index_rs = relative_strength(index_df["Close"].squeeze())

    # 2. Batch-download all stock data
    if progress_callback:
        progress_callback(0.05, "Downloading stock data...")

    # Download in batches of 100 to avoid overwhelming the API
    all_data: dict[str, pd.DataFrame] = {}
    batch_size = 100
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i: i + batch_size]
        batch_data = download_batch(batch, period)
        all_data.update(batch_data)
        if progress_callback:
            pct = min(0.6, 0.05 + 0.55 * (i + len(batch)) / len(tickers))
            progress_callback(pct, f"Downloaded {min(i + len(batch), len(tickers))}/{len(tickers)} tickers...")

    # 3. Compute indicators concurrently
    results: list[dict] = []

    def _process_ticker(ticker: str, df: pd.DataFrame) -> dict | None:
        try:
            # Flatten MultiIndex columns if present
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            # Volume & price filters
            avg_vol = df["Volume"].iloc[-20:].mean()
            cur_price = df["Close"].iloc[-1]

            if avg_vol < min_volume or cur_price < min_price:
                return None

            tt = TrendTemplate(ticker, df, index_rs, min_rs_rating)
            if not tt._valid:
                return None

            return tt.summary_dict()
        except Exception:
            return None

    processed = 0
    total = len(all_data)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(_process_ticker, t, d): t
            for t, d in all_data.items()
        }
        for future in as_completed(futures):
            processed += 1
            result = future.result()
            if result and result.get("Valid", True) is not False:
                results.append(result)
            if progress_callback and processed % 10 == 0:
                pct = 0.6 + 0.35 * processed / total
                progress_callback(min(0.95, pct), f"Analysed {processed}/{total} stocks...")

    if progress_callback:
        progress_callback(1.0, "Done!")

    if not results:
        return pd.DataFrame()

    df_results = pd.DataFrame(results)
    return df_results


# ──────────────────────────────────────────────────────────────
# Plotly chart helpers
# ──────────────────────────────────────────────────────────────

def price_chart(ticker: str, period: str) -> go.Figure:
    """Interactive candlestick chart with SMAs and Bollinger Bands."""
    df = yf.download(ticker, period=period, progress=False, auto_adjust=True)
    if df.empty:
        return go.Figure()

    # Flatten columns if MultiIndex
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    close = df["Close"]
    df["SMA_50"] = sma(close, 50)
    df["SMA_150"] = sma(close, 150)
    df["SMA_200"] = sma(close, 200)
    df["EMA_21"] = ema(close, 21)

    # Bollinger Bands
    bb_mid = sma(close, 20)
    bb_std = close.rolling(20).std()
    df["BB_Upper"] = bb_mid + 2 * bb_std
    df["BB_Lower"] = bb_mid - 2 * bb_std

    fig = go.Figure()

    # Bollinger band fill
    fig.add_trace(go.Scatter(
        x=df.index, y=df["BB_Upper"], line=dict(width=0), showlegend=False,
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=df.index, y=df["BB_Lower"], fill="tonexty",
        fillcolor="rgba(173,216,230,0.15)", line=dict(width=0),
        name="Bollinger Bands", hoverinfo="skip",
    ))

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"],
        low=df["Low"], close=df["Close"], name="Price",
    ))

    # Moving averages
    for col, color, dash in [
        ("EMA_21", "#ff9800", "dot"),
        ("SMA_50", "#2196f3", "solid"),
        ("SMA_150", "#9c27b0", "dash"),
        ("SMA_200", "#f44336", "dashdot"),
    ]:
        fig.add_trace(go.Scatter(
            x=df.index, y=df[col], name=col.replace("_", " "),
            line=dict(color=color, width=1.5, dash=dash),
        ))

    fig.update_layout(
        title=f"{ticker} — Price & Moving Averages",
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        height=500,
        margin=dict(l=40, r=40, t=50, b=40),
        legend=dict(orientation="h", y=-0.15),
    )
    return fig


def volume_chart(ticker: str, period: str) -> go.Figure:
    """Volume bar chart with 20-day average line."""
    df = yf.download(ticker, period=period, progress=False, auto_adjust=True)
    if df.empty:
        return go.Figure()

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    vol = df["Volume"]
    avg_vol = vol.rolling(20).mean()

    colors = ["#26a69a" if c >= o else "#ef5350"
              for c, o in zip(df["Close"], df["Open"])]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df.index, y=vol, name="Volume",
        marker_color=colors, opacity=0.7,
    ))
    fig.add_trace(go.Scatter(
        x=df.index, y=avg_vol, name="20d Avg Vol",
        line=dict(color="#ffeb3b", width=2),
    ))
    fig.update_layout(
        title=f"{ticker} — Volume",
        template="plotly_dark",
        height=250,
        margin=dict(l=40, r=40, t=50, b=40),
        showlegend=True,
        legend=dict(orientation="h", y=-0.25),
    )
    return fig


# ──────────────────────────────────────────────────────────────
# Styling helpers
# ──────────────────────────────────────────────────────────────

def color_conditions(val):
    """Color True/False condition cells."""
    if val is True:
        return "background-color: rgba(76, 175, 80, 0.3); color: #4caf50"
    elif val is False:
        return "background-color: rgba(244, 67, 54, 0.2); color: #ef5350"
    return ""


def color_rs(val):
    """Color RS rating."""
    try:
        v = float(val)
        if v >= 100:
            return "color: #4caf50; font-weight: bold"
        elif v >= 70:
            return "color: #ff9800"
        else:
            return "color: #ef5350"
    except (ValueError, TypeError):
        return ""


# ──────────────────────────────────────────────────────────────
# Main App
# ──────────────────────────────────────────────────────────────

def main():
    # ---- Custom CSS ----
    st.markdown("""
    <style>
        .block-container { padding-top: 1.5rem; }
        [data-testid="stMetric"] {
            background: linear-gradient(135deg, #1e1e2f 0%, #2d2d44 100%);
            border: 1px solid #3d3d5c;
            border-radius: 10px;
            padding: 12px 16px;
        }
        [data-testid="stMetricValue"] { font-size: 1.4rem; }
        .stTabs [data-baseweb="tab-list"] { gap: 8px; }
        .stTabs [data-baseweb="tab"] {
            border-radius: 8px 8px 0 0;
            padding: 8px 20px;
        }
    </style>
    """, unsafe_allow_html=True)

    # ---- Sidebar ----
    with st.sidebar:
        st.header("Screener Settings")
        st.divider()

        index_name = st.selectbox(
            "Market Index",
            list(INDEX_TICKERS.keys()),
            index=0,
        )

        period_map = {
            "6 Months": "6mo",
            "1 Year": "1y",
            "2 Years": "2y",
        }
        period_label = st.selectbox("Lookback Period", list(period_map.keys()), index=1)
        period = period_map[period_label]

        st.divider()
        st.subheader("Filters")

        min_price = st.number_input("Min Price ($)", min_value=0, max_value=5000, value=5, step=1)
        min_volume = st.number_input(
            "Min Avg Volume",
            min_value=0,
            max_value=100_000_000,
            value=500_000,
            step=100_000,
            format="%d",
        )
        min_rs = st.slider("Min RS Rating", 0, 200, 70)

        st.divider()
        st.subheader("Display Options")
        show_all = st.checkbox("Show all scanned stocks", value=False,
                               help="Show stocks that failed conditions too")

    # ---- Main content ----
    st.title("Mark Minervini's Trend Template Screener")
    st.caption("Screen stocks using the 8 Trend Template conditions plus "
               "RSI, MACD, ADX, Bollinger Bands, OBV, ATR, Stochastics, and more.")

    # Tabs
    tab_screener, tab_chart, tab_about = st.tabs([
        "Screener", "Stock Deep-Dive", "About & Methodology",
    ])

    # ---- About tab ----
    with tab_about:
        st.header("Minervini's 8 Trend Template Conditions")
        conditions_md = """
| # | Condition | Rationale |
|---|-----------|-----------|
| 1 | Price > 150 SMA **and** > 200 SMA | Stock is above long-term support |
| 2 | 150 SMA > 200 SMA | Intermediate trend is bullish |
| 3 | 200 SMA trending up (≥ 20 days) | Long-term trend is rising |
| 4 | 50 SMA > 150 SMA > 200 SMA | Moving averages in proper order |
| 5 | Price > 50 SMA | Short-term trend is bullish |
| 6 | Price ≥ 30% above 52-week low | Significant recovery / momentum |
| 7 | Price within 25% of 52-week high | Near highs, not overextended down |
| 8 | RS Rating ≥ threshold (default 70) | Outperforming the market |
"""
        st.markdown(conditions_md)

        st.header("Additional Indicators")
        extras_md = """
| Indicator | What it tells you |
|-----------|-------------------|
| **RSI (14)** | Momentum oscillator (overbought > 70, oversold < 30) |
| **MACD Histogram** | Trend momentum — positive = bullish, negative = bearish |
| **ADX (14)** | Trend strength (> 25 = strong trend, < 20 = weak/no trend) |
| **Stochastic %K** | Overbought/oversold oscillator (> 80 / < 20) |
| **Bollinger %B** | Position within Bollinger Bands (> 1 = above upper, < 0 = below lower) |
| **ATR (14)** | Volatility — higher = more volatile |
| **Volume ROC %** | Volume momentum — spikes can signal breakouts |
| **EMA 21** | Fast trend reference used by swing traders |
| **OBV** | Cumulative volume — confirms price trends |
"""
        st.markdown(extras_md)

        st.header("References")
        st.markdown("""
- [Mark Minervini's Blog — How to Chart Stocks Correctly](http://www.minervini.com/blog/index.php/blog/first_things_first_how_to_chart_stocks_correctly_and_increase_your_chances)
- [How To Scan Mark Minervini's Trend Template Using Python](https://www.marcellagerwerf.com/how-to-scan-mark-minervinis-trend-template-using-python/)
- [Making a Stock Screener with Python!](https://towardsdatascience.com/making-a-stock-screener-with-python-4f591b198261)
""")

    # ---- Screener tab ----
    with tab_screener:
        if st.button("Run Screener", type="primary", use_container_width=True):
            progress_bar = st.progress(0)
            status_text = st.empty()

            def update_progress(pct, msg):
                progress_bar.progress(pct)
                status_text.text(msg)

            with st.spinner("Screening..."):
                results_df = run_screen(
                    index_name=index_name,
                    min_volume=float(min_volume),
                    min_price=float(min_price),
                    period=period,
                    min_rs_rating=float(min_rs),
                    progress_callback=update_progress,
                )

            progress_bar.empty()
            status_text.empty()

            if results_df.empty:
                st.warning("No stocks matched all criteria. Try relaxing your filters.")
            else:
                # Separate passing vs failing stocks
                condition_cols = [c for c in results_df.columns if c.startswith("C") and ":" in c]
                results_df["All Pass"] = results_df[condition_cols].all(axis=1)

                passing = results_df[results_df["All Pass"]].copy()
                failing = results_df[~results_df["All Pass"]].copy()

                # ---- Summary metrics ----
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Stocks Scanned", len(results_df))
                col2.metric("Passed All 8", len(passing))
                col3.metric("Pass Rate", f"{len(passing)/len(results_df)*100:.1f}%")
                if not passing.empty:
                    col4.metric("Avg RS Rating (Passed)", f"{passing['RS Rating'].mean():.1f}")
                else:
                    col4.metric("Avg RS Rating", "N/A")

                # ---- Results table ----
                st.subheader(f"Stocks Passing All 8 Conditions ({len(passing)})")

                display_cols = [
                    "Ticker", "Price", "RS Rating", "RSI (14)", "MACD Hist",
                    "ADX (14)", "Stoch %K", "BB %B", "ATR (14)", "Vol ROC %",
                    "Avg Vol (20d)", "SMA 50", "SMA 150", "SMA 200", "EMA 21",
                    "52w Low", "52w High", "% From 52w Low", "% From 52w High",
                    "Conditions Passed",
                ] + condition_cols

                if not passing.empty:
                    # Sort by RS Rating descending
                    passing = passing.sort_values("RS Rating", ascending=False)
                    styled = passing[display_cols].style
                    for col in condition_cols:
                        styled = styled.map(color_conditions, subset=[col])
                    styled = styled.map(color_rs, subset=["RS Rating"])

                    st.dataframe(styled, use_container_width=True, height=500)

                    # Download button
                    csv_buf = io.StringIO()
                    passing[display_cols].to_csv(csv_buf, index=False)
                    st.download_button(
                        "Download Results (CSV)",
                        csv_buf.getvalue(),
                        file_name="minervini_screener_results.csv",
                        mime="text/csv",
                    )
                else:
                    st.info("No stocks passed all 8 conditions.")

                # Show failing stocks if requested
                if show_all and not failing.empty:
                    st.subheader(f"Stocks That Did Not Pass ({len(failing)})")
                    failing = failing.sort_values("Conditions Passed", ascending=False)
                    styled_fail = failing[display_cols].style
                    for col in condition_cols:
                        styled_fail = styled_fail.map(color_conditions, subset=[col])
                    st.dataframe(styled_fail, use_container_width=True, height=400)

                # Store in session state for deep-dive
                st.session_state["results_df"] = results_df
                st.session_state["period"] = period
        else:
            if "results_df" in st.session_state:
                st.info("Previous results are still available. Switch to the **Stock Deep-Dive** tab to explore individual stocks.")

    # ---- Deep-Dive tab ----
    with tab_chart:
        st.header("Individual Stock Analysis")

        # Populate dropdown from results or allow manual entry
        ticker_options = []
        if "results_df" in st.session_state:
            ticker_options = st.session_state["results_df"]["Ticker"].tolist()

        col_input, col_period = st.columns([2, 1])
        with col_input:
            selected_ticker = st.text_input(
                "Enter Ticker Symbol",
                value=ticker_options[0] if ticker_options else "AAPL",
            ).upper().strip()
        with col_period:
            chart_period = st.selectbox(
                "Chart Period",
                ["6mo", "1y", "2y", "5y"],
                index=1,
                key="chart_period",
            )

        if st.button("Load Chart", key="load_chart"):
            with st.spinner(f"Loading {selected_ticker}..."):
                fig_price = price_chart(selected_ticker, chart_period)
                fig_vol = volume_chart(selected_ticker, chart_period)

            st.plotly_chart(fig_price, use_container_width=True)
            st.plotly_chart(fig_vol, use_container_width=True)

            # Show indicator summary for this stock
            if "results_df" in st.session_state:
                row = st.session_state["results_df"]
                row = row[row["Ticker"] == selected_ticker]
                if not row.empty:
                    r = row.iloc[0]
                    st.subheader("Indicator Summary")
                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("RS Rating", f"{r['RS Rating']:.1f}")
                    m2.metric("RSI (14)", f"{r['RSI (14)']:.1f}")
                    m3.metric("MACD Hist", f"{r['MACD Hist']:.3f}")
                    m4.metric("ADX (14)", f"{r['ADX (14)']:.1f}")
                    m5.metric("Stoch %K", f"{r['Stoch %K']:.1f}")

                    m6, m7, m8, m9, m10 = st.columns(5)
                    m6.metric("BB %B", f"{r['BB %B']:.2f}")
                    m7.metric("ATR (14)", f"{r['ATR (14)']:.2f}")
                    m8.metric("Vol ROC %", f"{r['Vol ROC %']:.1f}")
                    m9.metric("% From 52w High", f"{r['% From 52w High']:.1f}%")
                    m10.metric("% From 52w Low", f"{r['% From 52w Low']:.1f}%")


if __name__ == "__main__":
    main()
