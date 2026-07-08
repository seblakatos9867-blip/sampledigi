#!/usr/bin/env python3
"""
ML trade predictor — trains a Random Forest on technical indicator features
and predicts the next candle's direction (UP / DOWN).
Usage: python3 predict.py AAPL TSLA SPY
"""

import sys
import warnings
import argparse
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from data import fetch
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    RICH = True
    console = Console()
except ImportError:
    RICH = False
    console = None

# ── Technical indicator features ─────────────────────────────────────────────

def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    c = df["Close"].squeeze()
    h = df["High"].squeeze()
    l = df["Low"].squeeze()
    v = df["Volume"].squeeze()

    feat = pd.DataFrame(index=df.index)

    # RSI
    delta = c.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    feat["rsi"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))

    # MACD
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    macd  = ema12 - ema26
    sig   = macd.ewm(span=9, adjust=False).mean()
    feat["macd"]      = macd
    feat["macd_hist"] = macd - sig

    # Bollinger %B
    sma20 = c.rolling(20).mean()
    std20 = c.rolling(20).std()
    feat["bb_pct"] = (c - (sma20 - 2 * std20)) / (4 * std20 + 1e-9)

    # EMAs / SMAs
    feat["ema9"]  = c.ewm(span=9,  adjust=False).mean()
    feat["ema21"] = c.ewm(span=21, adjust=False).mean()
    feat["sma50"] = c.rolling(50).mean()

    # EMA ratios (price relative to MAs)
    feat["price_vs_ema9"]  = c / feat["ema9"]  - 1
    feat["price_vs_ema21"] = c / feat["ema21"] - 1
    feat["price_vs_sma50"] = c / feat["sma50"] - 1
    feat["ema9_vs_ema21"]  = feat["ema9"] / feat["ema21"] - 1

    # ATR (normalised)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    feat["atr_pct"] = tr.rolling(14).mean() / c

    # Volume ratio
    feat["vol_ratio"] = v / v.rolling(20).mean()

    # Candle body and shadow
    feat["body_pct"]   = (c - df["Open"].squeeze()) / (h - l + 1e-9)
    feat["upper_wick"] = (h - c.clip(lower=df["Open"].squeeze())) / (h - l + 1e-9)
    feat["lower_wick"] = (c.clip(upper=df["Open"].squeeze()) - l) / (h - l + 1e-9)

    # Returns
    for lag in [1, 2, 3, 5]:
        feat[f"ret_{lag}"] = c.pct_change(lag)

    # Momentum (ROC)
    feat["roc10"] = c.pct_change(10)

    # Stochastic %K
    low14  = l.rolling(14).min()
    high14 = h.rolling(14).max()
    feat["stoch_k"] = (c - low14) / (high14 - low14 + 1e-9) * 100

    return feat


def make_target(df: pd.DataFrame, horizon: int = 1) -> pd.Series:
    """1 = next candle UP, 0 = DOWN"""
    c = df["Close"].squeeze()
    return (c.shift(-horizon) > c).astype(int)


# ── Model ────────────────────────────────────────────────────────────────────

def train_and_predict(ticker: str, period: str = "2y", horizon: int = 1):
    if RICH:
        console.print(f"[dim]Fetching {ticker.upper()} — {period} of daily data…[/]")

    df = fetch(ticker, period=period, interval="1d")
    if len(df) < 100:
        print(f"Not enough data for {ticker}. Need at least 100 bars.")
        return None

    feat = compute_features(df)
    target = make_target(df, horizon)

    # Align and drop NaNs
    data = pd.concat([feat, target.rename("target")], axis=1).dropna()
    data = data.iloc[:-horizon]  # drop last rows (future unknown)

    X = data.drop(columns="target")
    y = data["target"]

    if len(X) < 60:
        print(f"Too little clean data after feature engineering ({len(X)} rows).")
        return None

    # Time-series cross-validation
    tscv   = TimeSeriesSplit(n_splits=5)
    scaler = StandardScaler()

    # Two models — ensemble their predictions
    rf  = RandomForestClassifier(n_estimators=200, max_depth=6, random_state=42, n_jobs=-1)
    gb  = GradientBoostingClassifier(n_estimators=150, max_depth=4, learning_rate=0.05, random_state=42)

    cv_accs = []
    for train_idx, val_idx in tscv.split(X):
        X_tr, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_tr, y_val = y.iloc[train_idx], y.iloc[val_idx]
        X_tr_s  = scaler.fit_transform(X_tr)
        X_val_s = scaler.transform(X_val)
        rf.fit(X_tr_s, y_tr)
        cv_accs.append(accuracy_score(y_val, rf.predict(X_val_s)))

    cv_acc = np.mean(cv_accs)

    # Final fit on all data
    X_s = scaler.fit_transform(X)
    rf.fit(X_s, y)
    gb.fit(X_s, y)

    # Predict on last full row
    last_feat  = feat.iloc[[-1]].dropna(axis=1)
    common_cols = [c for c in X.columns if c in last_feat.columns]
    last_X     = last_feat[common_cols].reindex(columns=X.columns, fill_value=0)
    last_X_s   = scaler.transform(last_X)

    rf_prob  = rf.predict_proba(last_X_s)[0]
    gb_prob  = gb.predict_proba(last_X_s)[0]
    ensemble = (rf_prob + gb_prob) / 2
    pred_class = int(np.argmax(ensemble))
    confidence = float(ensemble[pred_class])

    # Feature importance (top 8)
    importance = pd.Series(rf.feature_importances_, index=X.columns)\
                   .sort_values(ascending=False).head(8)

    # Last close
    last_close = float(df["Close"].squeeze().iloc[-1])

    return {
        "ticker":       ticker.upper(),
        "prediction":   "UP" if pred_class == 1 else "DOWN",
        "confidence":   confidence,
        "cv_accuracy":  cv_acc,
        "last_close":   last_close,
        "horizon":      horizon,
        "n_samples":    len(X),
        "importance":   importance,
        "rf_prob_up":   rf_prob[1],
        "gb_prob_up":   gb_prob[1],
    }


# ── Display ───────────────────────────────────────────────────────────────────

def display(result: dict):
    if result is None:
        return

    pred  = result["prediction"]
    conf  = result["confidence"]
    cv    = result["cv_accuracy"]
    col   = "green" if pred == "UP" else "red"
    arrow = "▲" if pred == "UP" else "▼"

    if RICH:
        body = (
            f"[bold {col}]{arrow} {pred}[/]   "
            f"Confidence: [bold]{conf:.1%}[/]   "
            f"(RF: {result['rf_prob_up']:.1%} up  |  GB: {result['gb_prob_up']:.1%} up)\n"
            f"Last close: [bold]${result['last_close']:.2f}[/]   "
            f"CV accuracy: {cv:.1%} over 5 time-series folds   "
            f"Trained on {result['n_samples']} samples   "
            f"Horizon: {result['horizon']} candle(s)"
        )
        console.print(Panel(body,
          title=f"[bold]{result['ticker']}[/]  ML Prediction (next {result['horizon']}d)",
          border_style=col))

        t = Table(title="Top Feature Importances", box=box.SIMPLE_HEAVY)
        t.add_column("Feature")
        t.add_column("Importance", justify="right")
        for feat_name, imp in result["importance"].items():
            bar = "█" * int(imp * 40)
            t.add_row(feat_name, f"{imp:.4f}  [dim]{bar}[/]")
        console.print(t)

        console.print(
            "[dim italic]ML predictions are probabilistic — not financial advice. "
            "Past accuracy does not guarantee future performance.[/]"
        )
    else:
        print(f"\n{'='*50}")
        print(f" {result['ticker']}  →  {arrow} {pred}  ({conf:.1%} confidence)")
        print(f"{'='*50}")
        print(f" Last close:   ${result['last_close']:.2f}")
        print(f" CV accuracy:  {cv:.1%}")
        print(f" RF prob UP:   {result['rf_prob_up']:.1%}")
        print(f" GB prob UP:   {result['gb_prob_up']:.1%}")
        print(f" Samples:      {result['n_samples']}")
        print()
        print(" Top features:")
        for fn, imp in result["importance"].items():
            print(f"   {fn:<20} {imp:.4f}")
        print()


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="ML trade predictor: Random Forest + Gradient Boosting on technical features"
    )
    parser.add_argument("tickers", nargs="+", help="Ticker(s) e.g. AAPL TSLA SPY")
    parser.add_argument("--period",  default="2y", help="Training data period (default: 2y)")
    parser.add_argument("--horizon", default=1, type=int,
                        help="Candles ahead to predict (default: 1 day)")
    args = parser.parse_args()

    for ticker in args.tickers:
        result = train_and_predict(ticker, period=args.period, horizon=args.horizon)
        display(result)
        if len(args.tickers) > 1 and RICH:
            console.rule()


if __name__ == "__main__":
    main()
