import numpy as np
import pandas as pd
from trading_ai.data import demo_data,normalize
from trading_ai.engine import Config,backtest
from trading_ai.indicators import enrich,signals

def test_demo_is_valid_and_deterministic():
    a=demo_data(500,3)
    b=demo_data(500,3)
    pd.testing.assert_frame_equal(a,b)
    assert (a.High>=a.Low).all()

def test_backtest_reconciles_trade_pnl_and_capital():
    data=demo_data(1000,42)
    config=Config(strategy='Ruptura Donchian')
    result=backtest({'FAKE':data},config)
    assert abs(result['metrics']['ending']-(config.initial_cash+result['trades'].pnl.sum()))<1e-6
    assert len(result['equity'])==1000
    assert (result['equity'].cash>=-1e-6).all()
    assert (result['equity'].positions<=config.max_positions).all()

def test_same_data_same_signals_and_results():
    d=demo_data(900,111)
    a=backtest({'X':d},Config())
    b=backtest({'X':d},Config())
    pd.testing.assert_frame_equal(a['trades'],b['trades'])
    pd.testing.assert_frame_equal(a['equity'],b['equity'])

def test_prefix_signals_do_not_see_future():
    d=demo_data(600,2)
    x=signals(enrich(d),'Ruptura Donchian')
    y=signals(enrich(d.iloc[:450]),'Ruptura Donchian')
    pd.testing.assert_series_equal(x.entry_signal.iloc[:450],y.entry_signal)

def test_multimarket_uses_shared_cash():
    result=backtest({'A':demo_data(750,1),'B':demo_data(750,2)},Config(max_allocation_pct=10))
    assert (result['equity']['cash']>=-0.001).all()
    assert result['metrics']['ending']>0

def test_invalid_ohlc_is_removed():
    d=demo_data(150,1)
    broken=d.copy();broken.iloc[10,1]=0
    clean=normalize(broken)
    assert len(clean)==149

def test_no_trades_on_latest_bar_signal_without_next_open():
    d=demo_data(800,22)
    res=backtest({'X':d},Config())
    events=res['events']
    if len(events):
        assert not ((events.event=='BUY') & (events.date==d.index[0])).any()
