"""Prospective-ready baseline: real OHLC, fixed configurations, no synthetic fallback.
Results are descriptive holdout backtests, not proof of an investable edge.
"""
from datetime import date, timedelta, datetime, timezone
from pathlib import Path
import json
import math
import os
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from trading_ai.data import fetch
from trading_ai.engine import Config, backtest, benchmark

ASSETS=['BTC-USD','SPY','EURUSD=X']
STRATEGIES=['Tendencia + pullback','Ruptura Donchian','Cruce EMA']
START='2019-01-01'
END=(date.today()+timedelta(days=1)).isoformat()
OUT=ROOT/'reports'/'baseline_real_oos.json'

def clean(value):
    if isinstance(value,dict):return {k:clean(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [clean(v) for v in value]
    if isinstance(value,float) and not math.isfinite(value):return None
    return value

def main():
    result={'generated_at_utc':datetime.now(timezone.utc).isoformat(),
            'git_sha':os.getenv('GITHUB_SHA'),'source':'yfinance / Yahoo Finance (research only)',
            'start':START,'end_exclusive':END,'split':'first 70% dates / final 30% dates',
            'methods':'fixed strategies, no parameter fitting; daily OHLC adjusted; next open entries',
            'caveat':'Historical simulated performance, not audited or predictive; costs are assumptions',
            'results':[]}
    errors=[]
    for ticker in ASSETS:
        try:
            d=fetch(ticker,START,END)
            dates=d.index
            if len(d)<300:raise ValueError('insufficient daily candles')
            cut=dates[int(len(d)*.7)]
            for strategy in STRATEGIES:
                cfg=Config(strategy=strategy)
                full=backtest({ticker:d},cfg)
                oos=backtest({ticker:d},cfg,start=cut)
                bench=benchmark({ticker:d},oos['equity'].index,cfg.initial_cash)
                bench_pct=(float(bench.iloc[-1])/cfg.initial_cash-1)*100
                item={'ticker':ticker,'strategy':strategy,
                    'first_date':str(d.index[0].date()),'last_date':str(d.index[-1].date()),
                    'candles':len(d),'oos_start':str(cut.date()),
                    'oos_benchmark_buyhold_pct':round(bench_pct,3),
                    'oos':clean(oos['metrics']),'whole_period':clean(full['metrics'])}
                result['results'].append(item)
                print(f"{ticker} | {strategy} | OOS return={oos['metrics']['total_return_pct']:.2f}% "
                      f"| buy&hold={bench_pct:.2f}% | OOS trades={oos['metrics']['trades']}",flush=True)
        except Exception as e:
            errors.append({'ticker':ticker,'error':f'{type(e).__name__}: {e}'})
            print(f'ERROR {ticker}: {e}',file=sys.stderr)
    result['errors']=errors
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(clean(result),ensure_ascii=False,indent=2),encoding='utf-8')
    print('Report:',OUT,flush=True)
    if errors or len(result['results'])!=len(ASSETS)*len(STRATEGIES):return 1
    return 0

if __name__=='__main__':
    raise SystemExit(main())
