import requests
from datetime import datetime, timedelta
from config import FINNHUB_API_KEY


def get_finnhub_ma5(symbol):
    if not FINNHUB_API_KEY:
        return None

    now = datetime.now()
    from_ts = int((now - timedelta(days=14)).timestamp())
    to_ts = int(now.timestamp())

    try:
        resp = requests.get(
            "https://finnhub.io/api/v1/stock/candle",
            params={
                "symbol": symbol,
                "resolution": "D",
                "from": from_ts,
                "to": to_ts,
                "token": FINNHUB_API_KEY,
            },
            timeout=5,
        )
        data = resp.json()
        if data.get("s") != "ok":
            return None
        closes = [c for c in data.get("c", []) if c > 0]
        if not closes:
            return None
        recent = closes[-5:]
        return sum(recent) / len(recent)
    except Exception:
        return None
