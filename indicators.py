"""
Technical indicators for stock screening.

Includes Mark Minervini's 8 Trend Template conditions plus additional
indicators: RSI, MACD, ADX, Bollinger Bands, OBV, ATR, VWAP, EMA,
Stochastic Oscillator, and Volume Rate of Change.
"""

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Moving Averages
# ---------------------------------------------------------------------------

def sma(series: pd.Series, window: int) -> pd.Series:
    """Simple Moving Average."""
    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=span, adjust=False).mean()


# ---------------------------------------------------------------------------
# Relative Strength (Minervini-style, stock vs index)
# ---------------------------------------------------------------------------

def relative_strength(closes: pd.Series) -> float:
    """
    Calculate relative strength as the ratio of average percentage gains
    to average percentage losses over the period.

    Fixed calculation: uses percentage returns (not raw prices) and takes
    the absolute value of average loss so the ratio is always positive.
    """
    returns = closes.pct_change().dropna()
    gains = returns[returns >= 0]
    losses = returns[returns < 0]

    avg_gain = gains.mean() if len(gains) > 0 else 0.0
    avg_loss = abs(losses.mean()) if len(losses) > 0 else 1e-10  # avoid /0

    return avg_gain / avg_loss


def rs_rating(stock_rs: float, index_rs: float) -> float:
    """
    Relative Strength rating: how the stock's RS compares to the index.
    Clamped to [0, 200] to keep the value meaningful.
    """
    if index_rs == 0:
        return 0.0
    return min(200.0, round(100.0 * (stock_rs / index_rs), 2))


# ---------------------------------------------------------------------------
# RSI  (Wilder's Relative Strength Index)
# ---------------------------------------------------------------------------

def rsi(closes: pd.Series, period: int = 14) -> pd.Series:
    """
    Wilder's RSI using exponential moving average of gains/losses.
    Returns a Series of RSI values (0-100).
    """
    delta = closes.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100.0 - (100.0 / (1.0 + rs))).fillna(50.0)


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------

def macd(closes: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """
    MACD line, Signal line, and Histogram.
    Returns (macd_line, signal_line, histogram) as Series.
    """
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


# ---------------------------------------------------------------------------
# ADX  (Average Directional Index)
# ---------------------------------------------------------------------------

def adx(high: pd.Series, low: pd.Series, close: pd.Series,
        period: int = 14) -> pd.Series:
    """
    Average Directional Index — measures trend strength (0-100).
    Values > 25 indicate a strong trend.
    """
    plus_dm = high.diff()
    minus_dm = -low.diff()

    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    tr = _true_range(high, low, close)

    atr_val = tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    plus_di = 100.0 * (plus_dm.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean() / atr_val)
    minus_di = 100.0 * (minus_dm.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean() / atr_val)

    dx = 100.0 * (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan))
    adx_val = dx.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    return adx_val.fillna(0.0)


# ---------------------------------------------------------------------------
# Bollinger Bands
# ---------------------------------------------------------------------------

def bollinger_bands(closes: pd.Series, window: int = 20, num_std: float = 2.0):
    """
    Returns (upper_band, middle_band, lower_band, %B) as Series.
    %B shows where price is relative to the bands (0 = lower, 1 = upper).
    """
    middle = sma(closes, window)
    std = closes.rolling(window=window, min_periods=window).std()
    upper = middle + num_std * std
    lower = middle - num_std * std
    pct_b = ((closes - lower) / (upper - lower)).fillna(0.5)
    return upper, middle, lower, pct_b


# ---------------------------------------------------------------------------
# ATR  (Average True Range)
# ---------------------------------------------------------------------------

def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """True Range — needed for ATR and ADX."""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series,
        period: int = 14) -> pd.Series:
    """Average True Range — volatility measure."""
    tr = _true_range(high, low, close)
    return tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()


# ---------------------------------------------------------------------------
# OBV  (On-Balance Volume)
# ---------------------------------------------------------------------------

def obv(closes: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume — cumulative volume confirming price trends."""
    direction = np.sign(closes.diff()).fillna(0)
    return (volume * direction).cumsum()


# ---------------------------------------------------------------------------
# Volume Rate of Change
# ---------------------------------------------------------------------------

def volume_roc(volume: pd.Series, period: int = 20) -> pd.Series:
    """Volume Rate of Change (%) — spikes suggest breakouts."""
    prev = volume.shift(period)
    return ((volume - prev) / prev.replace(0, np.nan) * 100.0).fillna(0.0)


# ---------------------------------------------------------------------------
# Stochastic Oscillator
# ---------------------------------------------------------------------------

def stochastic(high: pd.Series, low: pd.Series, close: pd.Series,
               k_period: int = 14, d_period: int = 3):
    """
    Stochastic Oscillator (%K and %D).
    Returns (percent_k, percent_d) as Series.
    """
    lowest_low = low.rolling(window=k_period, min_periods=k_period).min()
    highest_high = high.rolling(window=k_period, min_periods=k_period).max()
    denom = (highest_high - lowest_low).replace(0, np.nan)
    percent_k = ((close - lowest_low) / denom * 100.0).fillna(50.0)
    percent_d = percent_k.rolling(window=d_period).mean()
    return percent_k, percent_d


# ---------------------------------------------------------------------------
# VWAP  (Volume Weighted Average Price)  — intraday proxy on daily data
# ---------------------------------------------------------------------------

def vwap_proxy(high: pd.Series, low: pd.Series, close: pd.Series,
               volume: pd.Series) -> pd.Series:
    """
    Approximated daily VWAP using typical price * volume.
    Rolling 20-day VWAP proxy.
    """
    typical_price = (high + low + close) / 3.0
    cum_tp_vol = (typical_price * volume).rolling(20).sum()
    cum_vol = volume.rolling(20).sum().replace(0, np.nan)
    return (cum_tp_vol / cum_vol).fillna(typical_price)


# ---------------------------------------------------------------------------
# Minervini 8-Condition Trend Template
# ---------------------------------------------------------------------------

class TrendTemplate:
    """
    Evaluates Mark Minervini's 8 Trend Template conditions for a stock.

    Accepts a DataFrame with columns: Open, High, Low, Close, Volume
    (standard yfinance output).
    """

    def __init__(self, ticker: str, df: pd.DataFrame,
                 index_rs: float, min_rs_rating: float = 70.0):
        self.ticker = ticker
        self.df = df.copy()

        # Ensure we have enough data
        if len(self.df) < 200:
            self._valid = False
            return
        self._valid = True

        close = self.df["Close"]

        # Moving averages
        self.df["SMA_50"] = sma(close, 50)
        self.df["SMA_150"] = sma(close, 150)
        self.df["SMA_200"] = sma(close, 200)
        self.df["EMA_21"] = ema(close, 21)

        # Current values (last row)
        self.price = close.iloc[-1]
        self.sma_50 = self.df["SMA_50"].iloc[-1]
        self.sma_150 = self.df["SMA_150"].iloc[-1]
        self.sma_200 = self.df["SMA_200"].iloc[-1]
        self.ema_21 = self.df["EMA_21"].iloc[-1]

        # 200 SMA 20 trading days ago (for trend check)
        self.sma_200_20d_ago = (
            self.df["SMA_200"].iloc[-20]
            if len(self.df) >= 220
            else self.df["SMA_200"].iloc[0]
        )

        # 52-week high/low (260 trading days)
        lookback = min(260, len(close))
        self.low_52w = close.iloc[-lookback:].min()
        self.high_52w = close.iloc[-lookback:].max()

        # RS Rating
        self.stock_rs = relative_strength(close)
        self.index_rs = index_rs
        self.rs_rating_val = rs_rating(self.stock_rs, index_rs)
        self.min_rs_rating = min_rs_rating

        # Additional indicators
        self._compute_extra_indicators()

    def _compute_extra_indicators(self):
        """Compute all additional technical indicators."""
        close = self.df["Close"]
        high = self.df["High"]
        low = self.df["Low"]
        volume = self.df["Volume"]

        # RSI
        self.df["RSI_14"] = rsi(close, 14)
        self.rsi_val = self.df["RSI_14"].iloc[-1]

        # MACD
        macd_line, signal_line, hist = macd(close)
        self.df["MACD"] = macd_line
        self.df["MACD_Signal"] = signal_line
        self.df["MACD_Hist"] = hist
        self.macd_val = macd_line.iloc[-1]
        self.macd_signal_val = signal_line.iloc[-1]
        self.macd_hist_val = hist.iloc[-1]

        # ADX
        self.df["ADX_14"] = adx(high, low, close, 14)
        self.adx_val = self.df["ADX_14"].iloc[-1]

        # Bollinger Bands
        bb_upper, bb_mid, bb_lower, bb_pctb = bollinger_bands(close)
        self.df["BB_Upper"] = bb_upper
        self.df["BB_Mid"] = bb_mid
        self.df["BB_Lower"] = bb_lower
        self.df["BB_PctB"] = bb_pctb
        self.bb_pctb_val = bb_pctb.iloc[-1]

        # ATR
        self.df["ATR_14"] = atr(high, low, close, 14)
        self.atr_val = self.df["ATR_14"].iloc[-1]

        # OBV
        self.df["OBV"] = obv(close, volume)
        self.obv_val = self.df["OBV"].iloc[-1]

        # Volume ROC
        self.df["Vol_ROC"] = volume_roc(volume, 20)
        self.vol_roc_val = self.df["Vol_ROC"].iloc[-1]

        # Stochastic
        pct_k, pct_d = stochastic(high, low, close)
        self.df["Stoch_K"] = pct_k
        self.df["Stoch_D"] = pct_d
        self.stoch_k_val = pct_k.iloc[-1]
        self.stoch_d_val = pct_d.iloc[-1]

        # VWAP Proxy
        self.df["VWAP"] = vwap_proxy(high, low, close, volume)
        self.vwap_val = self.df["VWAP"].iloc[-1]

        # Average volume (20-day)
        self.avg_volume_20d = volume.iloc[-20:].mean()
        self.current_volume = volume.iloc[-1]

    # ---- Minervini 8 Conditions ----

    def condition1(self) -> bool:
        """Current Price > 150 SMA AND > 200 SMA."""
        return self.price > self.sma_150 and self.price > self.sma_200

    def condition2(self) -> bool:
        """150 SMA > 200 SMA."""
        return self.sma_150 > self.sma_200

    def condition3(self) -> bool:
        """200 SMA trending up for at least 1 month."""
        return self.sma_200 > self.sma_200_20d_ago

    def condition4(self) -> bool:
        """50 SMA > 150 SMA > 200 SMA."""
        return self.sma_50 > self.sma_150 > self.sma_200

    def condition5(self) -> bool:
        """Current Price > 50 SMA."""
        return self.price > self.sma_50

    def condition6(self) -> bool:
        """Price at least 30% above 52-week low."""
        return self.price >= 1.3 * self.low_52w

    def condition7(self) -> bool:
        """Price within 25% of 52-week high."""
        return self.price >= 0.75 * self.high_52w

    def condition8(self) -> bool:
        """RS Rating >= minimum threshold."""
        return self.rs_rating_val >= self.min_rs_rating

    def passes_all(self) -> bool:
        """Returns True only if all 8 conditions are met."""
        if not self._valid:
            return False
        return all([
            self.condition1(), self.condition2(), self.condition3(),
            self.condition4(), self.condition5(), self.condition6(),
            self.condition7(), self.condition8(),
        ])

    def condition_details(self) -> dict:
        """Returns a dict of each condition name -> pass/fail bool."""
        if not self._valid:
            return {f"Condition {i}": False for i in range(1, 9)}
        return {
            "C1: Price > 150 & 200 SMA": self.condition1(),
            "C2: 150 SMA > 200 SMA": self.condition2(),
            "C3: 200 SMA trending up": self.condition3(),
            "C4: 50 > 150 > 200 SMA": self.condition4(),
            "C5: Price > 50 SMA": self.condition5(),
            "C6: Price ≥ 30% above 52w low": self.condition6(),
            "C7: Price within 25% of 52w high": self.condition7(),
            "C8: RS Rating ≥ threshold": self.condition8(),
        }

    def summary_dict(self) -> dict:
        """Full summary row for results table."""
        if not self._valid:
            return {"Ticker": self.ticker, "Valid": False}

        conditions = self.condition_details()
        conditions_passed = sum(conditions.values())

        return {
            "Ticker": self.ticker,
            "Price": round(self.price, 2),
            "RS Rating": round(self.rs_rating_val, 1),
            "RSI (14)": round(self.rsi_val, 1),
            "MACD Hist": round(self.macd_hist_val, 3),
            "ADX (14)": round(self.adx_val, 1),
            "Stoch %K": round(self.stoch_k_val, 1),
            "BB %B": round(self.bb_pctb_val, 2),
            "ATR (14)": round(self.atr_val, 2),
            "Vol ROC %": round(self.vol_roc_val, 1),
            "Avg Vol (20d)": int(self.avg_volume_20d),
            "SMA 50": round(self.sma_50, 2),
            "SMA 150": round(self.sma_150, 2),
            "SMA 200": round(self.sma_200, 2),
            "EMA 21": round(self.ema_21, 2),
            "52w Low": round(self.low_52w, 2),
            "52w High": round(self.high_52w, 2),
            "% From 52w Low": round((self.price / self.low_52w - 1) * 100, 1),
            "% From 52w High": round((self.price / self.high_52w - 1) * 100, 1),
            "Conditions Passed": f"{conditions_passed}/8",
            **conditions,
        }
