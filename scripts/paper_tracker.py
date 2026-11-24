"""ATLAS QUANT prospective paper-trading tracker.

Only candidates in the scheduled discovery research shortlist are enrolled.
Never backfills historical P&L into a newly enrolled paper account.
Daily completed OHLC bars are processed strictly after the last recorded date.
No broker integration, no real order placement, no intraday/live claims.
Every account is independent: fixed starting paper cash, no leverage.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import math
import os
import sys
from dataclasses import asdict
from datetime import datetime, timezone, date, timedelta
from pathlib import Path

import pandas as pd
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from trading_ai.data import fetch
from trading_ai.indicators import enrich, signals
from trading_ai.engine import Config

DEFAULT_REPORT=ROOT/'reports'/'discovery_latest.json'
DEFAULT_STATE=ROOT/'paper'/'state.json'
DEFAULT_AUDIT=ROOT/'paper'/'status.json'
REPORT_VERSION=1

def utc_today():
    return datetime.now(timezone.utc).date()

def eligible_from_report(report):
    items=[]
    for item in report.get('results',[]):
        if item.get('status')!='RESEARCH_SHORTLIST': continue
        selected=item.get('selected') or {}
        params=selected.get('params') or {}
        symbol=item.get('symbol')
        if not symbol or not params:continue
        try:cfg=Config(**params);cfg.validate()
        except (TypeError, ValueError, AssertionError):continue
        fingerprint=hashlib.sha256(json.dumps(
            {'symbol':symbol,'config':asdict(cfg)},sort_keys=True).encode()).hexdigest()[:16]
        items.append((fingerprint,symbol,cfg))
    return items

def fresh_state():
    return {'version':REPORT_VERSION,'created_utc':datetime.now(timezone.utc).isoformat(),
            'accounts':{}, 'errors':[], 'last_run_utc':None}

def account_template(sym,cfg,d,now):
    last=d.index[-1]
    # No simulated P&L before enrolment; last completed bar is only a reference.
    # No historical entry may be filled retrospectively after enrollment.
    # Only signals observed on bars completed AFTER enrollment may place a future order.
    pending=None
    return {'symbol':sym,'strategy':cfg.strategy,'params':asdict(cfg),
       'enrolled_utc':now,'last_processed':str(last.date()),
       'initial_cash':cfg.initial_cash,'cash':cfg.initial_cash,
       'position':None,'pending':pending,
       'last_close':float(d.iloc[-1].Close),'equity_history':[],
       'trades':[],'events':[],'updated_utc':now}

def apply_completed_bar(account,bar,dt,cfg):
    """State transition uses only previously stored pending order and today's completed OHLC.
    Never use today's signal to fill at today's open.
    """
    account=copy.deepcopy(account)
    day=str(pd.Timestamp(dt).date())
    fee=cfg.fee_bps/10000
    slip=cfg.slippage_bps/10000
    pending=account.get('pending')
    pos=account.get('position')
    open_=float(bar.Open)
    if pending:
        account['pending']=None
        if pending['action']=='SELL' and pos is not None:
            exit_price=open_*(1-slip)
            proceeds=pos['qty']*exit_price
            account['cash']+=proceeds*(1-fee)
            pnl=proceeds*(1-fee)-pos['total_entry_cost']
            account['trades'].append({'entry_date':pos['entry_date'],'exit_date':day,
                'entry_price':pos['entry_price'],'exit_price':exit_price,'qty':pos['qty'],
                'pnl':pnl,'reason':'next_open_signal'})
            account['events'].append({'date':day,'action':'SELL','price':exit_price,'reason':'signal'})
            account['position']=None
            pos=None
        elif pending['action']=='BUY' and pos is None:
            entry=open_*(1+slip)
            atr=float(pending.get('atr') or 0)
            distance=cfg.stop_atr*atr
            if np.isfinite(distance) and distance>0:
                budget=min(account['cash']/(1+fee),
                    cfg.initial_cash*cfg.max_allocation_pct/100,
                    cfg.initial_cash*cfg.risk_pct/100*entry/distance)
                qty=max(0,budget/entry)
                cost=qty*entry*(1+fee)
                if qty>0 and cost>=1 and cost<=account['cash']+1e-8:
                    account['cash']-=cost
                    pos={'entry_date':day,'entry_price':entry,'qty':qty,
                         'stop':entry-distance,'target':entry+distance*cfg.reward_risk,
                         'total_entry_cost':cost}
                    account['position']=pos
                    account['events'].append({'date':day,'action':'BUY','price':entry,
                        'reason':f"signal {pending.get('signal_date')}"})
    pos=account['position']
    if pos is not None:
        reason=None;price=None
        if open_<=pos['stop']:price=open_*(1-slip);reason='gap_stop'
        elif open_>=pos['target']:price=open_*(1-slip);reason='gap_target'
        elif float(bar.Low)<=pos['stop']:price=pos['stop']*(1-slip);reason='stop'
        elif float(bar.High)>=pos['target']:price=pos['target']*(1-slip);reason='target'
        if reason:
            proceeds=pos['qty']*price
            account['cash']+=proceeds*(1-fee)
            pnl=proceeds*(1-fee)-pos['total_entry_cost']
            account['trades'].append({'entry_date':pos['entry_date'],'exit_date':day,
                'entry_price':pos['entry_price'],'exit_price':price,'qty':pos['qty'],
                'pnl':pnl,'reason':reason})
            account['events'].append({'date':day,'action':'SELL','price':price,'reason':reason})
            account['position']=None
    account['last_close']=float(bar.Close)
    account['last_processed']=day
    pos=account['position']
    equity=account['cash']+(pos['qty']*float(bar.Close) if pos else 0)
    account['equity_history'].append({'date':day,'equity':round(equity,6),
                                      'cash':round(account['cash'],6),
                                      'position':pos is not None})
    return account

def next_signal(account,indicator_row,dt):
    """After bar close, queue for next *future* bar open."""
    if account['position'] and bool(indicator_row.exit_signal):
        account['pending']={'action':'SELL','signal_date':str(pd.Timestamp(dt).date())}
    elif not account['position'] and bool(indicator_row.entry_signal) and np.isfinite(indicator_row.atr):
        account['pending']={'action':'BUY','atr':float(indicator_row.atr),
                            'signal_date':str(pd.Timestamp(dt).date())}
    return account

def evolve(account, prices, cfg):
    # Incomplete daily candle must never be used for a prospective observation.
    prices=prices[prices.index.date<utc_today()]
    last=pd.Timestamp(account['last_processed'])
    new_days=prices.index[prices.index>last]
    if not len(new_days):return account
    d=signals(enrich(prices,fast=cfg.fast,slow=cfg.slow,breakout=cfg.breakout),cfg.strategy)
    for dt in new_days:
        account=apply_completed_bar(account,d.loc[dt],dt,cfg)
        account=next_signal(account,d.loc[dt],dt)
    account['updated_utc']=datetime.now(timezone.utc).isoformat()
    return account

def summary(account):
    equity=account['cash']+(account['position']['qty']*account['last_close']
                            if account['position'] else 0)
    trades=account['trades']
    history=account['equity_history']
    dd=None
    if history:
        equity_series=np.array([row['equity'] for row in history])
        dd=float(np.min(equity_series/np.maximum.accumulate(
            np.r_[account['initial_cash'],equity_series])[1:]-1)*100)
    enrolled=datetime.fromisoformat(account['enrolled_utc'])
    days=max(0,(datetime.now(timezone.utc)-enrolled).days)
    profit=sum(x['pnl'] for x in trades)
    return {'symbol':account['symbol'],'strategy':account['strategy'],
        'enrolled_utc':account['enrolled_utc'],'last_processed':account['last_processed'],
        'days_under_observation':days,
        'completed_trades':len(trades),
        'closed_trade_pnl':round(profit,2),
        'current_equity':round(equity,2),
        'return_pct':round(100*(equity/account['initial_cash']-1),3),
        'max_drawdown_observed_pct':round(dd,3) if dd is not None else None,
        'open_position':account['position'] is not None,
        'research_ready_for_review': days>=90 and len(trades)>=30,
        'paper_only':True}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--report',default=str(DEFAULT_REPORT))
    parser.add_argument('--state',default=str(DEFAULT_STATE))
    parser.add_argument('--status',default=str(DEFAULT_AUDIT))
    args=parser.parse_args()
    report_path=Path(args.report);state_path=Path(args.state);status_path=Path(args.status)
    shard_dir=ROOT/'reports'/'shards'
    sources=([report_path] if report_path.exists() else []) + sorted(shard_dir.glob('slot_*.json'))
    if not sources:
        print('NO_DISCOVERY_REPORT: awaiting first successful scheduled report; no paper positions created.')
        return 0
    reports=[json.loads(path.read_text(encoding='utf-8')) for path in sources]
    state=json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else fresh_state()
    # Merge research candidates across all 12 rotating market slices.
    candidates_map={}
    for report in reports:
        for key,sym,cfg in eligible_from_report(report):
            candidates_map[key]=(sym,cfg)
    candidates=[(key,sym,cfg) for key,(sym,cfg) in sorted(candidates_map.items())]
    now=datetime.now(timezone.utc).isoformat()
    # Keep existing enrolled accounts frozen even when future discovery no longer selects them.
    known={key:(a['symbol'],Config(**a['params'])) for key,a in state['accounts'].items()}
    for key,sym,cfg in candidates:
        known.setdefault(key,(sym,cfg))
    fetched={}
    errors=[]
    for key,(sym,cfg) in known.items():
        try:
            if sym not in fetched:
                d=fetch(sym,(utc_today()-timedelta(days=900)).isoformat(),
                        (utc_today()+timedelta(days=1)).isoformat())
                fetched[sym]=d[d.index.date<utc_today()]
            d=fetched[sym]
            if len(d)<125:raise ValueError('Insufficient fully completed candles')
            if key not in state['accounts']:
                state['accounts'][key]=account_template(sym,cfg,d,now)
                print('ENROLLED',sym,cfg.strategy,'starting at',state['accounts'][key]['last_processed'])
            else:
                state['accounts'][key]=evolve(state['accounts'][key],d,cfg)
            print('PAPER',key,json.dumps(summary(state['accounts'][key])))
        except Exception as e:
            errors.append({'id':key,'symbol':sym,'error':f'{type(e).__name__}: {e}'})
            print('PAPER_DATA_ERROR',sym,str(e),flush=True)
    state['errors']=errors;state['last_run_utc']=now
    audit={'as_of_utc':now,'discovery_report_date':max((report.get('date_utc') or '' for report in reports),default=''),
        'candidate_count':len(candidates),'tracked_accounts':len(state['accounts']),
        'errors':errors,'paper_only':True,
        'cannot_certify':'No automated live trading approval. Need 90+ days and 30+ real prospective closed trades per strategy, plus independent review of execution, costs, multiple testing, benchmarks.',
        'accounts':[summary(v) for v in state['accounts'].values()]}
    state_path.parent.mkdir(parents=True,exist_ok=True)
    status_path.parent.mkdir(parents=True,exist_ok=True)
    state_path.write_text(json.dumps(state,indent=2,ensure_ascii=False),encoding='utf-8')
    status_path.write_text(json.dumps(audit,indent=2,ensure_ascii=False),encoding='utf-8')
    print('PAPER_SUMMARY',json.dumps({'tracked':len(state['accounts']),
          'errors':len(errors),'ready_for_review':sum(x['research_ready_for_review'] for x in audit['accounts'])}),flush=True)
    return 0 if not errors else 1

if __name__=='__main__':raise SystemExit(main())
