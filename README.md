# Mark Minervini Stock Screener

A modernised Python stock screener built with **Streamlit** that implements Mark Minervini's **8 Trend Template conditions** plus additional technical indicators for comprehensive stock analysis.

## Features

### Minervini's 8 Trend Template Conditions
1. Price > 150-day SMA **and** > 200-day SMA
2. 150-day SMA > 200-day SMA
3. 200-day SMA trending up for at least 1 month
4. 50-day SMA > 150-day SMA > 200-day SMA
5. Price > 50-day SMA
6. Price at least 30% above 52-week low
7. Price within 25% of 52-week high
8. Relative Strength Rating above threshold (default 70)

### Additional Indicators
| Indicator | Purpose |
|-----------|---------|
| **RSI (14)** | Momentum — overbought (>70) / oversold (<30) |
| **MACD** | Trend momentum and signal crossovers |
| **ADX (14)** | Trend strength (>25 = strong trend) |
| **Bollinger Bands (%B)** | Volatility and mean-reversion signals |
| **Stochastic Oscillator** | Overbought/oversold conditions |
| **ATR (14)** | Volatility measurement |
| **OBV** | Volume-confirmed trend direction |
| **Volume ROC** | Volume momentum — breakout detection |
| **EMA 21** | Fast trend reference for swing traders |
| **VWAP (proxy)** | Institutional price reference |

### Modern UI
- **Tabbed interface** — Screener, Stock Deep-Dive, About & Methodology
- **Interactive Plotly charts** — candlestick with overlays, volume bars
- **Metric cards** — at-a-glance summary of key stats
- **Color-coded results** — green/red pass/fail for each condition
- **CSV export** — download filtered results

### Performance
- **Batch downloading** via `yfinance` multi-ticker API (vs one-at-a-time)
- **Concurrent processing** with `ThreadPoolExecutor` for indicator computation
- **Streamlit caching** (`@st.cache_data`) to avoid redundant API calls
- **No artificial delays** — removed legacy `time.sleep()` rate-limiting

## Installation

### Option 1: pip (recommended)
```bash
git clone https://github.com/icedevil2001/mark_minervini_stock_screener.git
cd mark_minervini_stock_screener
pip install -r requirements.txt
```

### Option 2: Conda
```bash
git clone https://github.com/icedevil2001/mark_minervini_stock_screener.git
cd mark_minervini_stock_screener
conda env create -f environment.yaml
conda activate stock-screener
```

## Usage

```bash
streamlit run stock_screener.py
```

The app opens in your browser. Use the sidebar to configure:
- **Market Index** — S&P 500, NASDAQ, or DOW
- **Lookback Period** — 6 months, 1 year, or 2 years
- **Min Price / Volume** — filter out penny stocks and illiquid names
- **Min RS Rating** — relative strength threshold
- **Show all stocks** — optionally view stocks that failed conditions

## Project Structure

```
mark_minervini_stock_screener/
├── stock_screener.py   # Streamlit app, data fetching, charts
├── indicators.py       # All technical indicator calculations
├── requirements.txt    # pip dependencies
├── environment.yaml    # Conda environment
├── LICENSE             # MIT
└── README.md
```

## Requirements

- Python 3.11+
- See `requirements.txt` for package versions

## References

- [Mark Minervini — How to Chart Stocks Correctly](http://www.minervini.com/blog/index.php/blog/first_things_first_how_to_chart_stocks_correctly_and_increase_your_chances)
- [How To Scan Mark Minervini's Trend Template Using Python](https://www.marcellagerwerf.com/how-to-scan-mark-minervinis-trend-template-using-python/)
- [Making a Stock Screener with Python!](https://towardsdatascience.com/making-a-stock-screener-with-python-4f591b198261)

## License

MIT
