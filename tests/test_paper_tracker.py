from datetime import datetime, timezone
from dataclasses import asdict

import pandas as pd
from trading_ai.engine import Config
from scripts.paper_tracker import (
    fresh_state, eligible_from_report, account_template,
    apply_completed_bar, next_signal, evolve, summary
)
from trading_ai.data import demo_data


def test_research_candidate_is_frozen_and_invalid_configs_ignored():
    cfg=Config(strategy='Ruptura Donchian')
    report={'results':[
        {'status':'RESEARCH_SHORTLIST','symbol':'BTC-USD','selected':{'params':asdict(cfg)}},
        {'status':'FAILED_ROBUSTNESS_GATES','symbol':'ETH-USD','selected':{'params':asdict(cfg)}}]}
    out=eligible_from_report(report)
    assert len(out)==1 and out[0][1]=='BTC-USD'


def test_no_historical_profit_on_enrolment():
    d=demo_data(300,11)
    a=account_template('FAKE',Config(),d,'2026-11-23T12:00:00+00:00')
    assert a['cash']==10000 and not a['trades'] and not a['equity_history']
    assert a['last_processed']==str(d.index[-1].date())


def test_previous_signal_fills_next_daily_open_only():
    cfg=Config(strategy='Ruptura Donchian',stop_atr=2.,reward_risk=3.)
    d=demo_data(250,7)
    a=account_template('FAKE',cfg,d,'2026-11-23T12:00:00+00:00')
    day=pd.Timestamp('2026-11-24')
    a['position']=None
    a['pending']={'action':'BUY','atr':4.,'signal_date':'2026-11-23'}
    bar=pd.Series({'Open':100.,'High':102.,'Low':99.,'Close':101.})
    b=apply_completed_bar(a,bar,day,cfg)
    assert b['position'] is not None
    assert b['position']['entry_price']>100
    assert b['position']['entry_date']=='2026-11-24'
    assert b['pending'] is None
    assert a['position'] is None  # original state unchanged


def test_stop_first_if_stop_and_target_both_hit():
    cfg=Config(strategy='Ruptura Donchian',stop_atr=2.,reward_risk=1.)
    d=demo_data(250,12)
    a=account_template('FAKE',cfg,d,'2026-11-23T12:00:00+00:00')
    a['pending']={'action':'BUY','atr':2.,'signal_date':'2026-11-23'}
    bar=pd.Series({'Open':100.,'High':120.,'Low':90.,'Close':102.})
    b=apply_completed_bar(a,bar,pd.Timestamp('2026-11-24'),cfg)
    assert len(b['trades'])==1
    assert b['trades'][0]['reason']=='stop'
    assert b['trades'][0]['pnl']<0


def test_no_double_processing_of_same_date():
    cfg=Config(strategy='Ruptura Donchian')
    d=demo_data(350,17)
    a=account_template('FAKE',cfg,d,'2026-11-23T12:00:00+00:00')
    b=evolve(a,d,cfg)
    assert b['last_processed']==a['last_processed']
    assert b['equity_history']==a['equity_history']
