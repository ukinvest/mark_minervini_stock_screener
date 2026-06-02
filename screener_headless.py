#!/usr/bin/env python3
"""
Headless Stock Screener for GitHub Actions
===========================================
Runs the Mark Minervini stock screener without Streamlit UI
and saves results to CSV.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from io import StringIO

import pandas as pd
import yfinance as yf
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

from indicators import TrendTemplate, relative_strength, sma


def get_sp500_tickers():
    """Fetch S&P 500 tickers from Wikipedia"""
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        df = pd.read_html(StringIO(response.text))[0]
        symbols = df["Symbol"].str.replace('.', '-', regex=False).tolist()
        return symbols
    except Exception as e:
        print(f"Warning: Could not fetch S&P 500 tickers: {e}")
        return []


def get_nasdaq_tickers():
    """Fetch NASDAQ-100 tickers"""
    try:
        url = "https://en.wikipedia.org/wiki/Nasdaq-100"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        tables = pd.read_html(StringIO(response.text))
        for t in tables:
            cols = [str(c).lower() for c in t.columns]
            if any('ticker' in c or 'symbol' in c for c in cols):
                col = [c for c in t.columns if 'ticker' in str(c).lower() or 'symbol' in str(c).lower()][0]
                syms = t[col].dropna().tolist()
                syms = [str(s).strip() for s in syms if str(s).strip().isalpha()]
                if len(syms) > 50:
                    return syms
        return []
    except Exception as e:
        print(f"Warning: Could not fetch NASDAQ tickers: {e}")
        return []


def get_dow_tickers():
    """Fetch DOW tickers"""
    try:
        url = "https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        df = pd.read_html(StringIO(response.text))[1]
        return df["Symbol"].tolist()
    except Exception as e:
        print(f"Warning: Could not fetch DOW tickers: {e}")
        return []


def screen_stock(ticker: str, index_rs: float, min_rs: float = 70) -> dict:
    """Screen a single stock against Minervini's 8 Trend Template"""
    try:
        # Download historical data for the stock
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1y")

        if hist.empty or len(hist) < 200:
            return None

        # Calculate moving averages
        close = hist["Close"]
        sma50_series = sma(close, 50)
        sma150_series = sma(close, 150)
        sma200_series = sma(close, 200)

        # Get latest values
        price = close.iloc[-1]
        sma50 = sma50_series.iloc[-1]
        sma150 = sma150_series.iloc[-1]
        sma200 = sma200_series.iloc[-1]

        # Calculate RS for this stock
        rs = relative_strength(close)
        rs_rating_val = rs_rating(rs, index_rs) if index_rs > 0 else 0

        # Check 8 conditions
        conditions = {
            "Condition1": price > sma150 and price > sma200,
            "Condition2": sma150 > sma200,
            "Condition3": sma200 > close.iloc[-20] if len(close) >= 20 else False,
            "Condition4": sma50 > sma150 > sma200,
            "Condition5": price > sma50,
            "Condition6": price >= close.min() * 1.3,
            "Condition7": price >= close.max() * 0.75,
            "Condition8": rs_rating_val >= min_rs,
        }

        passed = sum(conditions.values())

        return {
            "ticker": ticker,
            "price": round(price, 2),
            "sma50": round(sma50, 2),
            "sma150": round(sma150, 2),
            "sma200": round(sma200, 2),
            "rs_rating": round(rs_rating_val, 1),
            "conditions_passed": passed,
            "all_conditions_met": passed == 8,
            **{f"cond_{k+1}": v for k, v in enumerate(conditions.values())},
        }
    except Exception as e:
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Run stock screener and save results to CSV"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="screener_results.csv",
        help="Output CSV file path",
    )
    parser.add_argument(
        "--index",
        "-i",
        choices=["sp500", "nasdaq", "dow"],
        default="sp500",
        help="Index to screen",
    )
    parser.add_argument(
        "--min-rs", "-r", type=float, default=70, help="Minimum RS rating"
    )
    parser.add_argument(
        "--max-workers", "-w", type=int, default=8, help="Number of concurrent workers"
    )

    args = parser.parse_args()

    # Calculate index RS (SPY) once
    print("Calculating market RS...")
    try:
        spy = yf.Ticker("SPY")
        spy_hist = spy.history(period="1y")
        if spy_hist.empty or len(spy_hist) < 200:
            print("Could not fetch SPY data. Using default RS of 1.0")
            index_rs = 1.0
        else:
            index_rs = relative_strength(spy_hist["Close"])
            print(f"Market RS: {index_rs:.2f}")
    except Exception as e:
        print(f"Warning: Could not calculate market RS: {e}")
        index_rs = 1.0

    # Get tickers
    print(f"Fetching {args.index.upper()} tickers...")
    if args.index == "sp500":
        tickers = get_sp500_tickers()
    elif args.index == "nasdaq":
        tickers = get_nasdaq_tickers()
    else:
        tickers = get_dow_tickers()

    if not tickers:
        print("No tickers found. Exiting.")
        sys.exit(1)

    print(f"Found {len(tickers)} tickers. Starting screen...")

    # Screen stocks concurrently
    results = []
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = {
            executor.submit(screen_stock, ticker, index_rs, args.min_rs): ticker
            for ticker in tickers
        }

        completed = 0
        for future in as_completed(futures):
            completed += 1
            if completed % 50 == 0:
                print(f"Progress: {completed}/{len(tickers)}")

            result = future.result()
            if result:
                results.append(result)

    # Filter results
    passed_all = [r for r in results if r["all_conditions_met"]]
    passed_most = [r for r in results if r["conditions_passed"] >= 6]

    print(f"\nResults:")
    print(f"  All 8 conditions met: {len(passed_all)}")
    print(f"  6+ conditions met: {len(passed_most)}")
    print(f"  Total screened: {len(results)}")

    # Save to CSV
    if results:
        df = pd.DataFrame(results).sort_values("conditions_passed", ascending=False)
        
        # Create output directory if it doesn't exist
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        df.to_csv(output_path, index=False)
        print(f"\nResults saved to: {output_path}")
    else:
        print("No results to save.")

    print(f"Screener run completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
