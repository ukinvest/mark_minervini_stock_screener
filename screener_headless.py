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

import pandas as pd
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed

from indicators import TrendTemplate, relative_strength, sma


def get_sp500_tickers():
    """Fetch S&P 500 tickers from Wikipedia"""
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        tables = pd.read_html(url, headers=headers)
        df = tables[0]
        return df["Symbol"].tolist()
    except Exception as e:
        print(f"Warning: Could not fetch S&P 500 tickers: {e}")
        return []


def get_nasdaq_tickers():
    """Fetch NASDAQ-100 tickers"""
    try:
        url = "https://en.wikipedia.org/wiki/Nasdaq-100"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        tables = pd.read_html(url, headers=headers)
        df = tables[4]
        return df["Ticker"].tolist()
    except Exception as e:
        print(f"Warning: Could not fetch NASDAQ tickers: {e}")
        return []


def get_dow_tickers():
    """Fetch DOW tickers"""
    try:
        url = "https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        tables = pd.read_html(url, headers=headers)
        df = tables[1]
        return df["Symbol"].tolist()
    except Exception as e:
        print(f"Warning: Could not fetch DOW tickers: {e}")
        return []


def screen_stock(ticker: str, min_rs: float = 70) -> dict:
    """Screen a single stock against Minervini's 8 Trend Template"""
    try:
        # Download historical data
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1y")

        if hist.empty or len(hist) < 200:
            return None

        # Calculate indicators
        close = hist["Close"]
        template = TrendTemplate(close)

        # Get latest values
        price = close.iloc[-1]
        sma50 = template.sma_50.iloc[-1]
        sma150 = template.sma_150.iloc[-1]
        sma200 = template.sma_200.iloc[-1]
        rs = relative_strength(ticker, close)

        # Check conditions
        conditions = {
            "Condition1": price > sma150 and price > sma200,
            "Condition2": sma150 > sma200,
            "Condition3": template.sma200_trending_up,
            "Condition4": sma50 > sma150 > sma200,
            "Condition5": price > sma50,
            "Condition6": price >= hist["Close"].min() * 1.3,
            "Condition7": price >= hist["Close"].max() * 0.75,
            "Condition8": rs >= min_rs,
        }

        passed = sum(conditions.values())

        return {
            "ticker": ticker,
            "price": round(price, 2),
            "sma50": round(sma50, 2),
            "sma150": round(sma150, 2),
            "sma200": round(sma200, 2),
            "rs": round(rs, 1),
            "conditions_passed": passed,
            "all_conditions_met": passed == 8,
            **{f"cond_{k+1}": v for k, v in enumerate(conditions.values())},
        }
    except Exception as e:
        print(f"Error screening {ticker}: {e}")
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
            executor.submit(screen_stock, ticker, args.min_rs): ticker
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
