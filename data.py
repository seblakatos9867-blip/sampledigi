"""Shared data-fetch module — hits Yahoo Finance chart API directly."""
import os
import requests
import pandas as pd

_SESSION = requests.Session()
_SESSION.verify = os.environ.get("SSL_CERT_FILE", True)
_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
if _proxy:
    _SESSION.proxies = {"https": _proxy, "http": _proxy}
_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})

_RANGE_MAP = {
    "5d": "5d", "1mo": "1mo", "3mo": "3mo", "6mo": "6mo",
    "1y": "1y", "2y": "2y", "5y": "5y", "max": "max",
}
_INTERVAL_MAP = {
    "1m": "1m", "2m": "2m", "5m": "5m", "15m": "15m", "30m": "30m",
    "60m": "60m", "1h": "60m", "1d": "1d", "1wk": "1wk", "1mo": "1mo",
}


def fetch(ticker: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
    range_  = _RANGE_MAP.get(period, period)
    intv    = _INTERVAL_MAP.get(interval, interval)
    url     = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker.upper()}"
    params  = {"interval": intv, "range": range_}
    r = _SESSION.get(url, params=params, timeout=20)
    r.raise_for_status()
    payload = r.json()

    result = payload["chart"]["result"]
    if not result:
        raise ValueError(f"No data returned for '{ticker}'")

    res       = result[0]
    ts        = res["timestamp"]
    quotes    = res["indicators"]["quote"][0]
    adjclose  = res["indicators"].get("adjclose", [{}])[0].get("adjclose", quotes["close"])

    df = pd.DataFrame({
        "Open":   quotes["open"],
        "High":   quotes["high"],
        "Low":    quotes["low"],
        "Close":  adjclose,
        "Volume": quotes["volume"],
    }, index=pd.to_datetime(ts, unit="s", utc=True).tz_convert("America/New_York"))
    df.index.name = "Datetime"
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    return df
