"""Extended multi-asset / multi-regime research audit on REAL daily prices.
No tuning or selection on holdout. Stop on fetch failures; never silently substitute synthetic data.
Outputs an inspectable JSON and CSV artifacts. This is not evidence of future returns.
"""
import sys, os, json, math, csv, statistics, hashlib
from pathlib import Path
from datetime import date, timedelta, datetime, timezone
from dataclasses import replace
import pandas as pd
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from trading_ai.data import fetch
from trading_ai.engine import Config, backtest, benchmark

ASSETS = {
    'BTC-USD':'Crypto/BTC', 'ETH-USD':'Crypto/ETH',
    'SPY':'US equities/SPY', 'QQQ':'US equities/QQQ',
    'GLD':'Gold ETF/GLD', 'TLT':'Bond ETF/TLT',
    'EURUSD=X':'Forex/EURUSD', 'GBPUSD=X':'Forex/GBPUSD',
    'AAPL':'Single equity/AAPL','MSFT':'Single equity/MSFT',
}
STRATEGIES = ['Tendencia + pullback','Ruptura Donchian','Cruce EMA']
START='2016-01-01'
END=(date.today()+timedelta(days=1)).isoformat()
RESULT=ROOT/'reports'/'full_backtest_audit.json'
CSV=ROOT/'reports'/'full_backtest_rows.csv'

def finite(obj):
    if isinstance(obj,dict):return {k:finite(v) for k,v in obj.items()}
    if isinstance(obj,list):return [finite(v) for v in obj]
    if isinstance(obj,(np.integer,)):return int(obj)
    if isinstance(obj,(float,np.floating)):
        return round(float(obj),5) if math.isfinite(float(obj)) else None
    return obj

def section(df, label):
    if len(df)<2:return None
    return {'label':label,'from':str(df.index[0].date()),'through':str(df.index[-1].date()),'bars':len(df)}

def evaluate(data, ticker, strategy, cut, cost_mult=1, since=None, until=None):
    cfg=Config(strategy=strategy,fee_bps=10*cost_mult,slippage_bps=5*cost_mult)
    res=backtest({ticker:data},cfg,start=since,end=until)
    m=finite(res['metrics'])
    b=benchmark({ticker:data},res['equity'].index,cfg.initial_cash)
    full_buyhold=100*(float(b.iloc[-1])/cfg.initial_cash-1)
    # Comparable notional risk: 20% invested once and 80% held in cash, no benchmark costs.
    capped_buyhold=full_buyhold * cfg.max_allocation_pct/100
    row=dict(ticker=ticker,strategy=strategy,period='OOS' if since else 'FULL',cost_multiplier=cost_mult,
        from_date=str(res['equity'].index[0].date()),through=str(res['equity'].index[-1].date()),
        oos_cut_date=str(cut.date()),**m,
        benchmark_100pct_buyhold_pct=round(full_buyhold,5),
        benchmark_20pct_buyhold_pct=round(capped_buyhold,5),
        excess_vs_20pct_buyhold_pct=round(m['total_return_pct']-capped_buyhold,5))
    # Audit checks
    if not np.isfinite(m['ending']) or m['ending']<=0:raise AssertionError('Invalid ending balance')
    if not (res['equity'].cash>=-1e-6).all():raise AssertionError('Negative cash')
    if res['equity'].positions.max()>cfg.max_positions:raise AssertionError('Max position breach')
    if abs(m['ending']-cfg.initial_cash-float(res['trades'].pnl.sum()))>1e-5:
        raise AssertionError('Capital reconciliation failure')
    return row

def main():
    report={'generated_utc':datetime.now(timezone.utc).isoformat(),
        'source':'yfinance publicly accessible research data; not licensed for commercial resale',
        'repository_commit':os.environ.get('GITHUB_SHA'),
        'start_requested':START,'end_exclusive':END,
        'methodology':'10 real ticker histories / 3 fixed swing strategies; 70:30 chronological test; 1x/2x/3x/5x trading costs; 20% cap; flat-cash risk-matched benchmark',
        'parameters':{'initial_cash':10000,'risk_pct':1,'max_allocation_pct':20,
            'fee_bps':10,'slippage_bps':5,'stop_atr':2,'reward_risk':2,'fast':20,'slow':100,'breakout':20},
        'assets':{},'rows':[],'regimes':[],'rolling_windows':[],'portfolio':[],
        'errors':[], 'warnings':[
            'No automated hyperparameter fitting, no nested walk-forward, no paper trading.',
            'Single-instrument costs are assumptions, not measured spreads or market impact.',
            'Adjusted OHLC for equities may not match actual executable opens/stops at ex-dividend/split events.',
            'Differences in instrument trading sessions, point-in-time availability, corporate actions and delisted assets matter.',
            'Selected universe is not an unbiased random universe; multiple comparison risk remains.',
            'Risk-matched passive benchmark holds 20% in the underlying, 80% cash (zero cash yield) and has no fees.']}
    fetched={}
    for ticker,category in ASSETS.items():
        try:
            d=fetch(ticker,START,END)
            if len(d)<500:raise ValueError(f'Insufficient historical daily bars ({len(d)})')
            fetched[ticker]=d
            report['assets'][ticker]={'category':category,'bars':len(d),
                'first':str(d.index[0].date()),'last':str(d.index[-1].date()),
                'sha256_ohlc':hashlib.sha256(d.to_csv().encode()).hexdigest()}
        except Exception as e:
            report['errors'].append({'asset':ticker,'error':str(e)})
            print('FETCH FAIL',ticker,str(e),flush=True)
    for ticker,d in fetched.items():
        dates=d.index
        cut=dates[int(len(d)*.7)]
        for strategy in STRATEGIES:
            try:
                full=evaluate(d,ticker,strategy,cut)
                report['rows'].append(full)
                base=evaluate(d,ticker,strategy,cut,since=cut)
                report['rows'].append(base)
                for multi in [2,3,5]:
                    report['rows'].append(evaluate(d,ticker,strategy,cut,cost_mult=multi,since=cut))
                # Three non-overlapping, chronologically ordered evaluation windows.
                for i, part in enumerate(np.array_split(dates,3)):
                    if len(part)<2:continue
                    segment=evaluate(d,ticker,strategy,cut,since=pd.Timestamp(part[0]),until=pd.Timestamp(part[-1]))
                    segment['window']=i+1
                    report['rolling_windows'].append(segment)
                print('DONE',ticker,strategy,'OOS',round(base['total_return_pct'],2),'trades',base['trades'],
                      'bench20',round(base['benchmark_20pct_buyhold_pct'],2),flush=True)
            except Exception as e:
                report['errors'].append({'asset':ticker,'strategy':strategy,'error':str(e)})
                print('BACKTEST FAIL',ticker,strategy,str(e),flush=True)

    # Shared-cash portfolio across a constrained group of heterogeneous assets; no leverage.
    groups={
        'Cross-asset basket':['BTC-USD','SPY','GLD','TLT','EURUSD=X'],
        'Crypto basket':['BTC-USD','ETH-USD'],
        'Equity basket':['SPY','QQQ','AAPL','MSFT'],
    }
    for name,syms in groups.items():
        subset={s:fetched[s] for s in syms if s in fetched}
        if len(subset)<len(syms):continue
        all_dates=sorted(set().union(*(set(df.index) for df in subset.values())))
        cut=pd.Timestamp(all_dates[int(len(all_dates)*.7)])
        for strategy in STRATEGIES:
            try:
                cfg=Config(strategy=strategy)
                res=backtest(subset,cfg,start=cut)
                m=finite(res['metrics'])
                report['portfolio'].append(dict(name=name,strategy=strategy,assets=syms,
                    oos_start=str(cut.date()),oos_end=str(res['equity'].index[-1].date()),**m))
                print('PORTFOLIO',name,strategy,round(m['total_return_pct'],2),'trades',m['trades'],flush=True)
            except Exception as e:
                report['errors'].append({'portfolio':name,'strategy':strategy,'error':str(e)})
    # Aggregate by strategy across assets; no optimistic ranking chosen after test.
    report['aggregate']={}
    for strategy in STRATEGIES:
        vals=[x for x in report['rows'] if x['strategy']==strategy and x['period']=='OOS' and x['cost_multiplier']==1]
        if vals:
            report['aggregate'][strategy]={'markets':len(vals),'positive_count':sum(x['total_return_pct']>0 for x in vals),
                'beats_capped_passive_count':sum(x['excess_vs_20pct_buyhold_pct']>0 for x in vals),
                'median_return_pct':round(statistics.median(x['total_return_pct'] for x in vals),3),
                'median_max_drawdown_pct':round(statistics.median(x['max_drawdown_pct'] for x in vals),3),
                'total_trades':sum(x['trades'] for x in vals)}
    report['summary']={'assets_success':len(fetched),'strategy_oos_results':len([x for x in report['rows'] if x['period']=='OOS' and x['cost_multiplier']==1]),
        'stress_results':len([x for x in report['rows'] if x['period']=='OOS' and x['cost_multiplier']>1]),
        'full_period_results':len([x for x in report['rows'] if x['period']=='FULL']),
        'portfolio_results':len(report['portfolio']),
        'errors':len(report['errors'])}
    RESULT.parent.mkdir(parents=True,exist_ok=True)
    RESULT.write_text(json.dumps(finite(report),ensure_ascii=False,indent=2),encoding='utf-8')
    keys=['ticker','strategy','period','cost_multiplier','from_date','through','oos_cut_date',
        'total_return_pct','max_drawdown_pct','sharpe','trades','win_rate_pct','profit_factor',
        'benchmark_100pct_buyhold_pct','benchmark_20pct_buyhold_pct','excess_vs_20pct_buyhold_pct']
    with CSV.open('w',newline='',encoding='utf-8') as fp:
        writer=csv.DictWriter(fp,fieldnames=keys,extrasaction='ignore');writer.writeheader();writer.writerows(report['rows'])
    print('AGGREGATE',json.dumps(report['aggregate'],ensure_ascii=False),flush=True)
    print('SUMMARY',json.dumps(report['summary']),flush=True)
    print('REPORTS',RESULT,CSV,flush=True)
    if report['errors'] or len(fetched)!=len(ASSETS) or report['summary']['strategy_oos_results']!=len(ASSETS)*len(STRATEGIES):
        raise SystemExit(1)
if __name__=='__main__':main()
