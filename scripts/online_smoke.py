"""Online connectivity and REAL market data validation. Fail closed (no demo fallback).
Run within a hosted environment with network access: python scripts/online_smoke.py
"""
from datetime import date, timedelta
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from trading_ai.data import fetch

RESULTS = []
for category, ticker in [('crypto', 'BTC-USD'), ('equity', 'SPY'), ('fx', 'EURUSD=X')]:
    try:
        today = date.today()
        df = fetch(ticker, (today-timedelta(days=550)).isoformat(), (today+timedelta(days=1)).isoformat())
        assert len(df) >= 125, 'not enough data'
        assert df.index.is_monotonic_increasing and df.index.is_unique
        assert (df.High >= df[['Open','Close','Low']].max(axis=1)).all()
        assert (df.Low <= df[['Open','Close','High']].min(axis=1)).all()
        RESULTS.append({'market':category,'ticker':ticker,'status':'PASS','rows':len(df), 'first_date':str(df.index.min().date()), 'last_date':str(df.index.max().date())})
    except Exception as exc:
        RESULTS.append({'market':category,'ticker':ticker,'status':'FAIL', 'error':f'{type(exc).__name__}: {exc}'})
print(json.dumps(RESULTS,ensure_ascii=False,indent=2))
raise SystemExit(0 if all(x['status']=='PASS' for x in RESULTS) else 1)
