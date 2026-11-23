"""ATLAS QUANT scheduled multi-market strategy discovery.

Research ONLY: no brokerage connections, no trades, no claims of prospective alpha.
The final chronological holdout is read once *after* selecting by development+
validation. Re-running this workflow and choosing on holdout outcomes contaminates
that holdout; use fresh subsequent bars for true prospective evidence.
"""
import argparse
import csv
import hashlib
import itertools
import json
import math
import os
import statistics
import sys
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from trading_ai.data import fetch
from trading_ai.engine import Config, backtest, benchmark
from scripts.global_universe import UNIVERSE as WORLD_UNIVERSE, catalog as global_catalog

# Broad scope; yfinance accessibility and data licensing differ by instrument.
UNIVERSE={
 'Cripto': ['BTC-USD','ETH-USD','SOL-USD','BNB-USD','XRP-USD','ADA-USD','DOGE-USD','AVAX-USD','LINK-USD','LTC-USD','BCH-USD','DOT-USD'],
 'Divisas': ['EURUSD=X','GBPUSD=X','JPY=X','AUDUSD=X','USDCAD=X','USDCHF=X','NZDUSD=X','EURGBP=X'],
 'ETF índices': ['SPY','QQQ','IWM','EFA','EEM','DIA'],
 'Acciones': ['AAPL','MSFT','NVDA','AMZN','GOOGL','META'],
 'Bonos y metales ETF': ['TLT','IEF','GLD','SLV'],
 'Materias primas (futuros proxy)': ['GC=F','SI=F','CL=F','NG=F'],
}
# Predeclared independent candidate configurations. No mutation based on holdout.
CANDIDATES=[
    ('Tendencia + pullback',12,80,20,1.5,2.0),
    ('Tendencia + pullback',20,100,20,2.0,2.0),
    ('Tendencia + pullback',25,150,20,2.0,3.0),
    ('Tendencia + pullback',40,200,20,2.5,2.0),
    ('Ruptura Donchian',12,80,15,1.5,2.0),
    ('Ruptura Donchian',20,100,20,2.0,2.0),
    ('Ruptura Donchian',25,150,40,2.0,3.0),
    ('Ruptura Donchian',40,200,55,2.5,2.0),
    ('Cruce EMA',8,60,20,1.5,2.0),
    ('Cruce EMA',12,80,20,2.0,2.0),
    ('Cruce EMA',20,100,20,2.0,3.0),
    ('Cruce EMA',40,200,20,2.5,2.0),
]

def config_for(candidate):
    strategy,fast,slow,breakout,stop_atr,reward_risk=candidate
    return Config(strategy=strategy,fast=fast,slow=slow,breakout=breakout,
                  stop_atr=stop_atr,reward_risk=reward_risk,
                  initial_cash=10000,risk_pct=1,max_allocation_pct=20,
                  fee_bps=10,slippage_bps=5)

def windows(d):
    """60% train / 20% validation / 20% untouched final.
    Each stage gets earlier warmup bars for indicator values but backtest only
    executes after its first designated date.
    """
    if len(d)<650:raise ValueError(f'Insufficient daily bars ({len(d)} < 650)')
    i=int(len(d)*.60);j=int(len(d)*.80)
    return d.index[0],d.index[i],d.index[j],d.index[-1]

def finite(x):
    if isinstance(x,dict):return {k:finite(v) for k,v in x.items()}
    if isinstance(x,(tuple,list)):return [finite(y) for y in x]
    if isinstance(x,(np.integer,)):return int(x)
    if isinstance(x,(np.floating,float)):
        z=float(x)
        return round(z,5) if math.isfinite(z) else None
    return x

def stats_for(d,symbol,cfg,start,end,cost_factor=1):
    c=replace(cfg,fee_bps=cfg.fee_bps*cost_factor,slippage_bps=cfg.slippage_bps*cost_factor)
    res=backtest({symbol:d},c,start=start,end=end)
    m=res['metrics']
    buy=benchmark({symbol:d},res['equity'].index,c.initial_cash)
    passive_20=(float(buy.iloc[-1])/c.initial_cash-1)*100*.2
    return {
       'return_pct':round(m['total_return_pct'],4),
       'max_drawdown_pct':round(m['max_drawdown_pct'],4),
       'trades':int(m['trades']),
       'sharpe':finite(m['sharpe']),
       'win_rate_pct':finite(m['win_rate_pct']),
       'benchmark_20pct_passive_pct':round(passive_20,4),
       'excess_vs_passive_pct':round(m['total_return_pct']-passive_20,4)
    }

def pick_candidate(d,symbol):
    start,val_start,holdout_start,last=windows(d)
    train_end=d.index[d.index.get_loc(val_start)-1]
    val_end=d.index[d.index.get_loc(holdout_start)-1]
    # Selection uses *only* train and validation.
    scored=[]
    for candidate in CANDIDATES:
        cfg=config_for(candidate)
        train=stats_for(d,symbol,cfg,start,train_end)
        valid=stats_for(d,symbol,cfg,val_start,val_end)
        # Require trading observations. Weak candidates are recorded but not promoted.
        qualifies=(train['trades']>=4 and valid['trades']>=3)
        # Validation score penalizes drawdown and costs, and train overfitting.
        score=(valid['excess_vs_passive_pct']
               +0.15*train['excess_vs_passive_pct']
               +0.3*valid['max_drawdown_pct']
               -max(0,valid['return_pct']-train['return_pct'])*.05)
        scored.append({'candidate':candidate,'cfg':cfg,'train':train,'validation':valid,
                       'eligible':qualifies,'selection_score':round(score,5)})
    eligible=[c for c in scored if c['eligible']]
    if not eligible:
        return None,scored,{'train_end':str(train_end.date()),'validation_start':str(val_start.date()),
                            'validation_end':str(val_end.date()),'holdout_start':str(holdout_start.date()),'last':str(last.date())}
    # Ranking stops here. Never look at holdout before choosing.
    best=max(eligible,key=lambda v:(v['selection_score'],v['validation']['trades'],str(v['candidate'])))
    return best,scored,{'train_end':str(train_end.date()),'validation_start':str(val_start.date()),
                       'validation_end':str(val_end.date()),'holdout_start':str(holdout_start.date()),'last':str(last.date())}

def search_asset(d,symbol,category):
    best,candidates,periods=pick_candidate(d,symbol)
    result={'symbol':symbol,'category':category,'bars':len(d),
        'first':str(d.index[0].date()),'last':str(d.index[-1].date()),
        'ohlc_sha256':hashlib.sha256(d.to_csv().encode()).hexdigest(),
        'periods':periods,'candidates_tested':len(candidates),
        'eligible_candidates':sum(x['eligible'] for x in candidates),
        'selected':None,'status':'NO_ELIGIBLE_CANDIDATE'}
    if best is None:return result
    cfg=best['cfg'];start=pd.Timestamp(periods['holdout_start'])
    # Holdout is touched only after the winner has been selected.
    holdout=stats_for(d,symbol,cfg,start,d.index[-1])
    stressed={str(x):stats_for(d,symbol,cfg,start,d.index[-1],x) for x in [2,3,5]}
    # Operational gates are objective, NOT part of candidate selection.
    # Re-using the same holdout across recurring runs is NOT fresh evidence.
    valid=best['validation']
    gates={
      'validation_profit_after_costs':valid['return_pct']>0,
      'validation_beats_passive':valid['excess_vs_passive_pct']>0,
      'validation_drawdown_below_15pct':valid['max_drawdown_pct']>=-15,
      'holdout_positive':holdout['return_pct']>0,
      'holdout_beats_passive':holdout['excess_vs_passive_pct']>0,
      'holdout_trades_at_least_5':holdout['trades']>=5,
      'holdout_2x_cost_positive':stressed['2']['return_pct']>0,
      'holdout_drawdown_below_15pct':holdout['max_drawdown_pct']>=-15,
    }
    # This is a *research shortlist* only, not a product/risk approval.
    status='RESEARCH_SHORTLIST' if all(gates.values()) else 'FAILED_ROBUSTNESS_GATES'
    result.update(status=status,selected={
      'strategy':cfg.strategy,'params':asdict(cfg),'train':best['train'],
      'validation':valid,'holdout':holdout,'stress':stressed,
      'gates':gates,'selection_score':best['selection_score']})
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--max-assets',type=int,default=40)
    parser.add_argument('--universe',choices=['legacy','global'],default='legacy')
    parser.add_argument('--shard-count',type=int,default=1)
    parser.add_argument('--shard-index',type=int,default=0)
    parser.add_argument('--start',default='2018-01-01')
    parser.add_argument('--end',default=(date.today()+timedelta(days=1)).isoformat())
    parser.add_argument('--output',default='reports/discovery_latest.json')
    args=parser.parse_args()
    assert 1<=args.max_assets<=1000
    assert 1<=args.shard_count<=96
    assert 0<=args.shard_index<args.shard_count
    out=ROOT/args.output
    population=global_catalog() if args.universe=='global' else [(group,t) for group,tickers in UNIVERSE.items() for t in tickers]
    selected=([v for idx,v in enumerate(population) if idx%args.shard_count==args.shard_index]
              if args.shard_count>1 else population[:args.max_assets])
    if not selected:raise SystemExit('Empty shard configuration')
    report={
      'date_utc':datetime.now(timezone.utc).isoformat(),
      'commit_sha':os.environ.get('GITHUB_SHA'),
      'start_requested':args.start,'end_exclusive':args.end,
      'dataset':'REAL Yahoo Finance/yfinance daily OHLC (research use; not commercial redistributable license)',
      'selection_protocol':'60% train,20% validation,20% final holdout; 12 predefined configs per asset; holdout never consulted for selection',
      'limitations':[
        'Repeated scheduled reviews of the SAME holdout contaminate it if used to tune rules or choose marketed winners.',
        'A research shortlist does NOT certify expected profit; prospective forward paper-trading remains required.',
        'Non-survivorship-free hand-picked universe; instrument and historical-adjustment biases apply.',
        'Long-only engine, cash base and 20% max allocation; Forex is not a levered FX venue simulation.',
        'FX/futures cash/contract margin, rolls, swap, dividends, financing and bid-ask historically are not properly modelled.',
        'Reference 20%-invested/80%-cash is allocation-matched, not volatility- or risk-matched.',
        'Historical costs are simulated; no external account and NO actual trading.',
        'Data sources may fail, have gaps or be rate-limited; failed symbols excluded and explicitly counted.'
      ],
      'universe':{k:v for k,v in (WORLD_UNIVERSE if args.universe=='global' else UNIVERSE).items()},
      'coverage':{'catalog_size':len(population),'shard_count':args.shard_count,
                  'shard_index':args.shard_index,
                  'requested_in_shard':len(selected),
                  'scheduled':'best effort; not a real-time exchange feed',
                  'no_complete_world_claim':True},
      'candidates_per_asset':len(CANDIDATES),
      'results':[],'failures':[]}
    for ix,(group,symbol) in enumerate(selected,1):
        print(f'[{ix}/{len(selected)}] FETCH {symbol} ({group})',flush=True)
        try:
            d=fetch(symbol,args.start,args.end)
            result=search_asset(d,symbol,group)
            report['results'].append(result)
            chosen=result['selected']
            print('RESULT',symbol,result['status'],
                  'OOS',chosen['holdout']['return_pct'] if chosen else 'none',
                  'validation',chosen['validation']['return_pct'] if chosen else 'none',flush=True)
        except Exception as e:
            report['failures'].append({'symbol':symbol,'category':group,'error':f'{type(e).__name__}: {e}'})
            print('DATA_OR_BACKTEST_ERROR',symbol,str(e),flush=True)
    report['summary']={
      'requested':len(selected),'completed':len(report['results']),'failed':len(report['failures']),
      'tested_configs':sum(r['candidates_tested'] for r in report['results']),
      'eligible_assets':sum(bool(r['selected']) for r in report['results']),
      'research_shortlists':sum(r['status']=='RESEARCH_SHORTLIST' for r in report['results']),
      'holdout_positive_assets':sum(r['selected'] is not None and r['selected']['holdout']['return_pct']>0 for r in report['results']),
    }
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(finite(report),ensure_ascii=False,indent=2),encoding='utf-8')
    csv_path=out.with_suffix('.csv') if args.universe=='global' else out.parent/'discovery_summary.csv'
    with csv_path.open('w',encoding='utf-8',newline='') as f:
        cols=['category','symbol','status','strategy','validation_pct','holdout_pct','holdout_trades','oos_excess_passive_pct','oos_drawdown_pct']
        writer=csv.DictWriter(f,fieldnames=cols);writer.writeheader()
        for r in report['results']:
            x=r['selected'] or {}
            writer.writerow({'category':r['category'],'symbol':r['symbol'],'status':r['status'],
                'strategy':x.get('strategy'), 'validation_pct':x.get('validation',{}).get('return_pct'),
                'holdout_pct':x.get('holdout',{}).get('return_pct'),
                'holdout_trades':x.get('holdout',{}).get('trades'),
                'oos_excess_passive_pct':x.get('holdout',{}).get('excess_vs_passive_pct'),
                'oos_drawdown_pct':x.get('holdout',{}).get('max_drawdown_pct')})
    print('DISCOVERY_SUMMARY',json.dumps(report['summary']),flush=True)
    for r in report['results']:
        if r['status']=='RESEARCH_SHORTLIST':
            print('SHORTLIST',r['symbol'],r['selected']['strategy'],r['selected']['holdout'],flush=True)
    print('REPORT_PATH',str(out),flush=True)
    # Fail only if almost all of the universe is unavailable.
    if report['summary']['completed']<max(1,len(selected)//2):raise SystemExit(1)

if __name__=='__main__':main()
