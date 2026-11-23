"""Append-only prospective signal journal, not an order executor or P&L simulator.

Daily scheduled at 02:20 UTC, deliberately excludes the current UTC day's bar
to avoid partial crypto candles. For equity/forex use date stamped by provider.
Stores one entry per asset/provider bar date and fixed frozen strategy set.
NO optimization from logged outcomes. Never backfills previous dates as predictions.
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from trading_ai.data import fetch
from trading_ai.indicators import enrich, signals
from trading_ai.engine import Config

# Fixed policy from the beginning of prospective tracking; do not retrospectively alter.
UNIVERSE=[
    'BTC-USD','ETH-USD','SOL-USD','BNB-USD','XRP-USD','ADA-USD','AVAX-USD',
    'LINK-USD','LTC-USD','SPY','QQQ','IWM','AAPL','MSFT','NVDA','GLD','TLT',
    'EURUSD=X','GBPUSD=X','JPY=X','AUDUSD=X','GC=F','CL=F'
]
STRATEGIES=['Tendencia + pullback','Ruptura Donchian','Cruce EMA']
STORE=ROOT/'research_state'/'prospective_signals.jsonl'
SUMMARY=ROOT/'reports'/'prospective_latest.json'

def main():
    now=datetime.now(timezone.utc)
    today=pd.Timestamp(now.date())
    old=[]
    if STORE.exists():
        old=[json.loads(line) for line in STORE.read_text(encoding='utf-8').splitlines() if line.strip()]
    existing={x['id'] for x in old}
    fresh=[]
    errors=[]
    for ticker in UNIVERSE:
        try:
            d=fetch(ticker,str((now.date()-timedelta(days=520))),str(now.date()+timedelta(days=1)))
            # Strictly exclude today's incomplete daily OHLC. Some feeds have lag.
            d=d.loc[d.index<today]
            if len(d)<125:raise ValueError('Not enough completed OHLC bars')
            if (today-d.index[-1]).days>6:raise ValueError('Stale provider bars')
            for name in STRATEGIES:
                x=signals(enrich(d),name)
                last=x.iloc[-1]
                candle_date=str(x.index[-1].date())
                uid=hashlib.sha256(f'prospective-v1|{ticker}|{name}|{candle_date}'.encode()).hexdigest()
                if uid in existing:continue
                entry={
                    'id':uid,'policy':'prospective-v1-fixed-20-100-20-2ATR-2R',
                    'observed_at_utc':now.isoformat(),
                    'source':'Yahoo Finance research OHLC', 'ticker':ticker,
                    'last_completed_candle_date':candle_date,
                    'strategy':name,
                    'close':round(float(last.Close),9),
                    'atr':round(float(last.atr),9) if pd.notna(last.atr) else None,
                    'entry_signal_for_next_open':bool(last.entry_signal),
                    'exit_signal_for_next_open':bool(last.exit_signal),
                    'ohlc_sha256':hashlib.sha256(d.to_csv().encode()).hexdigest(),
                    'no_order_sent':True
                }
                fresh.append(entry);existing.add(uid)
                print('FORWARD_SIGNAL',ticker,name,candle_date,int(last.entry_signal),int(last.exit_signal),flush=True)
        except Exception as exc:
            errors.append({'ticker':ticker,'error':f'{type(exc).__name__}: {exc}'})
            print('FORWARD_ERROR',ticker,str(exc),flush=True)
    # Append-only, existing lines never modified.
    STORE.parent.mkdir(parents=True,exist_ok=True)
    if fresh:
        with STORE.open('a',encoding='utf-8') as f:
            for entry in fresh:f.write(json.dumps(entry,ensure_ascii=False,sort_keys=True)+'\n')
    SUMMARY.parent.mkdir(parents=True,exist_ok=True)
    report={'created_utc':now.isoformat(),'assets_requested':len(UNIVERSE),
            'config_policy':'prospective-v1-fixed-20-100-20-2ATR-2R',
            'new_records':len(fresh),'total_records':len(old)+len(fresh),'errors':errors,
            'new_buy_signals':[{'ticker':x['ticker'],'date':x['last_completed_candle_date'],'strategy':x['strategy']} for x in fresh if x['entry_signal_for_next_open']],
            'status':'RESEARCH_ONLY_NO_ORDERS',
            'important':'A signal journal is not P&L paper trading. These signals require subsequent execution modelling and months of real-time validation.'}
    SUMMARY.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PROSPECTIVE_SUMMARY',json.dumps({k:report[k] for k in ['new_records','total_records','errors','new_buy_signals']},ensure_ascii=False),flush=True)
    if len(fresh)==0 and len(errors)>=len(UNIVERSE):
        raise SystemExit('No valid market data; no fake records created')
if __name__=='__main__':main()
