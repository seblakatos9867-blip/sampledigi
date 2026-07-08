#!/usr/bin/env python3
"""Day trading guidance tool — fetches live data and signals buy/sell/hold."""

import sys
import argparse
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
from data import fetch

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich import box
    RICH = True
except ImportError:
    RICH = False

console = Console() if RICH else None


# ── Technical indicators ─────────────────────────────────────────────────────

def sma(series, period):
    return series.rolling(period).mean()


def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(series, fast=12, slow=26, signal=9):
    fast_ema = ema(series, fast)
    slow_ema = ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def bollinger(series, period=20, std_dev=2):
    mid = sma(series, period)
    std = series.rolling(period).std()
    return mid - std_dev * std, mid, mid + std_dev * std


def atr(high, low, close, period=14):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def volume_ratio(volume, period=20):
    return volume / volume.rolling(period).mean()


# ── Signal engine ─────────────────────────────────────────────────────────────

def compute_signals(df):
    c = df["Close"].squeeze()
    h = df["High"].squeeze()
    l = df["Low"].squeeze()
    v = df["Volume"].squeeze()

    signals = {}

    # Trend
    signals["sma20"] = sma(c, 20).iloc[-1]
    signals["sma50"] = sma(c, 50).iloc[-1]
    signals["ema9"]  = ema(c,  9).iloc[-1]
    signals["trend"] = "UP" if signals["sma20"] > signals["sma50"] else "DOWN"

    # RSI
    r = rsi(c)
    signals["rsi"] = r.iloc[-1]
    if signals["rsi"] < 30:
        signals["rsi_signal"] = ("BUY", "oversold")
    elif signals["rsi"] > 70:
        signals["rsi_signal"] = ("SELL", "overbought")
    else:
        signals["rsi_signal"] = ("HOLD", "neutral")

    # MACD
    macd_line, sig_line, hist = macd(c)
    signals["macd"] = macd_line.iloc[-1]
    signals["macd_signal"] = sig_line.iloc[-1]
    signals["macd_hist"] = hist.iloc[-1]
    prev_hist = hist.iloc[-2]
    if hist.iloc[-1] > 0 and prev_hist <= 0:
        signals["macd_cross"] = ("BUY", "bullish crossover")
    elif hist.iloc[-1] < 0 and prev_hist >= 0:
        signals["macd_cross"] = ("SELL", "bearish crossover")
    elif hist.iloc[-1] > prev_hist and hist.iloc[-1] > 0:
        signals["macd_cross"] = ("BUY", "histogram expanding bullish")
    elif hist.iloc[-1] < prev_hist and hist.iloc[-1] < 0:
        signals["macd_cross"] = ("SELL", "histogram expanding bearish")
    else:
        signals["macd_cross"] = ("HOLD", "no clear crossover")

    # Bollinger Bands
    bb_lo, bb_mid, bb_hi = bollinger(c)
    price = c.iloc[-1]
    signals["bb_lo"] = bb_lo.iloc[-1]
    signals["bb_hi"] = bb_hi.iloc[-1]
    bb_pct = (price - bb_lo.iloc[-1]) / (bb_hi.iloc[-1] - bb_lo.iloc[-1]) * 100
    signals["bb_pct"] = bb_pct
    if bb_pct < 15:
        signals["bb_signal"] = ("BUY", "near lower band")
    elif bb_pct > 85:
        signals["bb_signal"] = ("SELL", "near upper band")
    else:
        signals["bb_signal"] = ("HOLD", f"{bb_pct:.0f}% of band")

    # Volume
    vr = volume_ratio(v)
    signals["vol_ratio"] = vr.iloc[-1]
    signals["high_volume"] = vr.iloc[-1] > 1.5

    # ATR (volatility / position sizing)
    signals["atr"] = atr(h, l, c).iloc[-1]
    signals["price"] = price

    # EMA9 cross
    if c.iloc[-1] > signals["ema9"] and c.iloc[-2] <= ema(c, 9).iloc[-2]:
        signals["ema_cross"] = ("BUY", "price crossed above EMA9")
    elif c.iloc[-1] < signals["ema9"] and c.iloc[-2] >= ema(c, 9).iloc[-2]:
        signals["ema_cross"] = ("SELL", "price crossed below EMA9")
    else:
        signals["ema_cross"] = ("HOLD", "no EMA9 cross")

    # Day range
    today = df.iloc[-1]
    signals["day_high"] = float(today["High"])
    signals["day_low"]  = float(today["Low"])
    signals["open"]     = float(today["Open"])

    # Overall score: +1 BUY, -1 SELL, 0 HOLD
    indicators = [
        signals["rsi_signal"][0],
        signals["macd_cross"][0],
        signals["bb_signal"][0],
        signals["ema_cross"][0],
        "BUY" if signals["trend"] == "UP" else "SELL",
    ]
    score = sum(1 if s == "BUY" else -1 if s == "SELL" else 0 for s in indicators)
    if score >= 2:
        signals["overall"] = "BUY"
    elif score <= -2:
        signals["overall"] = "SELL"
    else:
        signals["overall"] = "HOLD"
    signals["score"] = score

    return signals


# ── Risk / position sizing ────────────────────────────────────────────────────

def position_guidance(price, atr_val, account_size=10000, risk_pct=1.0):
    risk_amount = account_size * risk_pct / 100
    stop_distance = atr_val * 1.5          # 1.5× ATR stop
    shares = int(risk_amount / stop_distance) if stop_distance > 0 else 0
    stop_price = price - stop_distance
    target_1r = price + stop_distance      # 1:1
    target_2r = price + stop_distance * 2  # 1:2
    return {
        "shares": shares,
        "stop": stop_price,
        "target_1r": target_1r,
        "target_2r": target_2r,
        "risk_amount": risk_amount,
        "stop_distance": stop_distance,
    }


# ── Display ───────────────────────────────────────────────────────────────────

def color(val):
    if val == "BUY":  return "[bold green]BUY[/]"
    if val == "SELL": return "[bold red]SELL[/]"
    return "[yellow]HOLD[/]"


def overall_panel(ticker, sig):
    ov = sig["overall"]
    score = sig["score"]
    col = "green" if ov == "BUY" else "red" if ov == "SELL" else "yellow"
    vol_str = "[bold cyan]HIGH[/]" if sig['high_volume'] else "normal"
    trend_str = "↑ UP" if sig['trend'] == 'UP' else "↓ DOWN"
    body = (
        f"[bold {col}]{ov}[/]   (score {score:+d}/5)\n"
        f"Price: [bold]${sig['price']:.2f}[/]   "
        f"Open: ${sig['open']:.2f}   "
        f"Day: ${sig['day_low']:.2f} – ${sig['day_high']:.2f}\n"
        f"Trend (SMA20 vs SMA50): [bold]{trend_str}[/]   "
        f"Volume ratio: {vol_str}  "
        f"({sig['vol_ratio']:.1f}×)"
    )
    return Panel(body, title=f"[bold]{ticker.upper()}[/]  Day-Trading Guidance", border_style=col)


def indicator_table(sig):
    t = Table(box=box.SIMPLE_HEAVY, show_header=True)
    t.add_column("Indicator", style="bold")
    t.add_column("Value", justify="right")
    t.add_column("Signal")
    t.add_column("Reason")

    rsi_s, rsi_r = sig["rsi_signal"]
    t.add_row("RSI(14)", f"{sig['rsi']:.1f}", color(rsi_s), rsi_r)

    macd_s, macd_r = sig["macd_cross"]
    t.add_row("MACD(12,26,9)", f"{sig['macd']:.4f} / hist {sig['macd_hist']:.4f}", color(macd_s), macd_r)

    bb_s, bb_r = sig["bb_signal"]
    t.add_row("Bollinger %B", f"{sig['bb_pct']:.0f}%", color(bb_s), bb_r)

    ema_s, ema_r = sig["ema_cross"]
    t.add_row("EMA9 cross", f"${sig['ema9']:.2f}", color(ema_s), ema_r)

    trend_s = "BUY" if sig["trend"] == "UP" else "SELL"
    t.add_row("SMA trend", f"SMA20 ${sig['sma20']:.2f}  SMA50 ${sig['sma50']:.2f}", color(trend_s), sig["trend"])

    return t


def risk_table(sig, pos):
    t = Table(box=box.SIMPLE_HEAVY, title="[bold]Position Sizing  (1% account risk)[/]")
    t.add_column("Field")
    t.add_column("Value", justify="right")
    t.add_row("Account size",      "$10,000")
    t.add_row("Max risk per trade", f"${pos['risk_amount']:.2f}")
    t.add_row("ATR(14)",            f"${sig['atr']:.2f}")
    t.add_row("Suggested stop",     f"${pos['stop']:.2f}  (-${pos['stop_distance']:.2f})")
    t.add_row("Shares (at risk)",   str(pos["shares"]))
    t.add_row("Target 1:1",         f"${pos['target_1r']:.2f}")
    t.add_row("Target 1:2",         f"${pos['target_2r']:.2f}")
    return t


def plain_output(ticker, sig, pos):
    ov = sig["overall"]
    print(f"\n{'='*50}")
    print(f" {ticker.upper()}  →  {ov}  (score {sig['score']:+d}/5)")
    print(f"{'='*50}")
    print(f" Price:  ${sig['price']:.2f}  |  Open: ${sig['open']:.2f}")
    print(f" Day:    ${sig['day_low']:.2f} – ${sig['day_high']:.2f}")
    print(f" Trend:  {sig['trend']}  |  Volume: {sig['vol_ratio']:.1f}×")
    print()
    print(" INDICATORS")
    for name, s_key, r_key in [
        ("RSI(14)", "rsi_signal", "rsi"),
        ("MACD",    "macd_cross", "macd_hist"),
        ("BB %B",   "bb_signal",  "bb_pct"),
        ("EMA9",    "ema_cross",  "ema9"),
    ]:
        sv, sr = sig[s_key]
        print(f"   {name:<12} {sv:<5}  {sr}")
    print()
    print(" POSITION SIZING (1% risk on $10,000 account)")
    print(f"   Shares:       {pos['shares']}")
    print(f"   Stop:        ${pos['stop']:.2f}  (-${pos['stop_distance']:.2f})")
    print(f"   Target 1:1:  ${pos['target_1r']:.2f}")
    print(f"   Target 1:2:  ${pos['target_2r']:.2f}")
    print()


def run(ticker, period="5d", interval="5m", account=10000):
    if RICH:
        console.print(f"[dim]Fetching {ticker.upper()} — {interval} bars, last {period}…[/]")

    df = fetch(ticker, period=period, interval=interval)
    if df.empty:
        sys.exit(f"No data returned for '{ticker}'. Check the symbol.")

    sig = compute_signals(df)
    pos = position_guidance(sig["price"], sig["atr"], account_size=account)

    if RICH:
        console.print(overall_panel(ticker, sig))
        console.print(indicator_table(sig))
        console.print(risk_table(sig, pos))
        console.print(
            "[dim italic]This is technical analysis only — not financial advice. "
            "Always manage your own risk.[/]"
        )
    else:
        plain_output(ticker, sig, pos)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Day-trading guidance: technical indicators + position sizing"
    )
    parser.add_argument("tickers", nargs="+", help="Stock ticker(s), e.g. AAPL TSLA SPY")
    parser.add_argument("--period",   default="5d",    help="History period (default: 5d)")
    parser.add_argument("--interval", default="5m",    help="Bar interval (default: 5m)")
    parser.add_argument("--account",  default=10000, type=float,
                        help="Account size in USD for position sizing (default: 10000)")
    args = parser.parse_args()

    for ticker in args.tickers:
        run(ticker, period=args.period, interval=args.interval, account=args.account)
        if len(args.tickers) > 1 and RICH:
            console.rule()


if __name__ == "__main__":
    main()
