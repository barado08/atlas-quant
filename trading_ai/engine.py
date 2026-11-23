"""Backtester diario, sin apalancamiento, largo solamente. Señal al cierre -> orden siguiente apertura.
Si stop y target se tocan en la misma vela, stop tiene prioridad (conservador).
Comisiones en ambos lados, spread/slippage por ejecución. Sin uso de velas futuras.
"""
from dataclasses import dataclass
from typing import Dict
import numpy as np
import pandas as pd
from .indicators import enrich, signals

@dataclass(frozen=True)
class Config:
    initial_cash:float=10000.
    risk_pct:float=1.
    max_allocation_pct:float=20.
    fee_bps:float=10.
    slippage_bps:float=5.
    stop_atr:float=2.
    reward_risk:float=2.
    max_positions:int=5
    strategy:str='Tendencia + pullback'
    fast:int=20
    slow:int=100
    breakout:int=20

    def validate(self):
        assert self.initial_cash>0 and 0<self.risk_pct<=5
        assert 0<self.max_allocation_pct<=100 and self.max_positions>=1
        assert self.fee_bps>=0 and self.slippage_bps>=0
        assert self.stop_atr>0 and self.reward_risk>0
        assert self.slow>self.fast>=2 and self.breakout>=2

def backtest(raw:Dict[str,pd.DataFrame],cfg:Config,start=None,end=None):
    cfg.validate()
    prepared={s:signals(enrich(d,fast=cfg.fast,slow=cfg.slow,breakout=cfg.breakout),cfg.strategy) for s,d in raw.items()}
    dates=sorted(set().union(*(set(d.index) for d in prepared.values())))
    start=pd.Timestamp(start) if start is not None else dates[0]
    end=pd.Timestamp(end) if end is not None else dates[-1]
    dates=[d for d in dates if start<=d<=end]
    if len(dates)<2:raise ValueError('Periodo demasiado corto')
    cash=cfg.initial_cash
    positions={}
    pending={}
    rows=[]; records=[]; events=[]; last_close={}
    fee=cfg.fee_bps/10000; slip=cfg.slippage_bps/10000
    for dt in dates:
        today={s:d.loc[dt] for s,d in prepared.items() if dt in d.index}
        for sym in sorted(list(pending)):
            if sym not in today:continue
            action=pending.pop(sym)
            bar=today[sym]
            if action['kind']=='exit' and sym in positions:
                pos=positions.pop(sym)
                price=float(bar.Open)*(1-slip)
                proceeds=pos['qty']*price
                sell_fee=proceeds*fee
                cash+=proceeds-sell_fee
                pnl=proceeds-sell_fee-pos['cost']
                records.append(dict(symbol=sym,entry=pos['date'],exit=dt,entry_price=pos['entry_price'],exit_price=price,qty=pos['qty'],pnl=pnl,return_pct=100*pnl/pos['cost'],reason='Señal',bars=(dt-pos['date']).days))
                events.append(dict(date=dt,symbol=sym,event='SELL',price=price,reason='Señal'))
            elif action['kind']=='entry' and sym not in positions and len(positions)<cfg.max_positions:
                entry=float(bar.Open)*(1+slip)
                distance=float(action['atr'])*cfg.stop_atr
                if not np.isfinite(distance) or distance<=0:continue
                equity=cash+sum(pos['qty']*last_close.get(s,pos['entry_price']) for s,pos in positions.items())
                budget=min(equity*cfg.max_allocation_pct/100,cash/(1+fee),equity*cfg.risk_pct/100*entry/distance)
                qty=budget/entry
                if qty<=0 or budget<1:continue
                cost=qty*entry*(1+fee)
                if cost>cash+1e-7:continue
                cash-=cost
                positions[sym]=dict(qty=qty,entry_price=entry,date=dt,cost=cost,stop=entry-distance,target=entry+distance*cfg.reward_risk)
                events.append(dict(date=dt,symbol=sym,event='BUY',price=entry,reason='Señal previa'))
        for sym in sorted(list(positions)):
            if sym not in today:continue
            b=today[sym];pos=positions[sym]
            reason=None
            if float(b.Open)<=pos['stop']:
                price=float(b.Open)*(1-slip);reason='Gap stop'
            elif float(b.Open)>=pos['target']:
                price=float(b.Open)*(1-slip);reason='Gap objetivo'
            elif float(b.Low)<=pos['stop']:
                price=pos['stop']*(1-slip);reason='Stop'
            elif float(b.High)>=pos['target']:
                price=pos['target']*(1-slip);reason='Objetivo'
            if reason:
                proceeds=pos['qty']*price; sf=proceeds*fee
                cash+=proceeds-sf
                pnl=proceeds-sf-pos['cost']
                records.append(dict(symbol=sym,entry=pos['date'],exit=dt,entry_price=pos['entry_price'],exit_price=price,qty=pos['qty'],pnl=pnl,return_pct=100*pnl/pos['cost'],reason=reason,bars=(dt-pos['date']).days))
                del positions[sym]
                pending.pop(sym,None)
                events.append(dict(date=dt,symbol=sym,event='SELL',price=price,reason=reason))
        for sym,b in today.items():last_close[sym]=float(b.Close)
        equity=cash+sum(pos['qty']*last_close.get(sym,pos['entry_price']) for sym,pos in positions.items())
        rows.append(dict(date=dt,equity=equity,cash=cash,positions=len(positions)))
        for sym,b in today.items():
            if sym in positions:
                if bool(b.exit_signal):pending[sym]={'kind':'exit'}
            elif sym not in pending and bool(b.entry_signal):
                pending[sym]={'kind':'entry','atr':float(b.atr)}
    final_dt=dates[-1]
    for sym,pos in list(positions.items()):
        price=last_close.get(sym,pos['entry_price'])*(1-slip)
        proceeds=pos['qty']*price; sf=proceeds*fee
        cash+=proceeds-sf
        pnl=proceeds-sf-pos['cost']
        records.append(dict(symbol=sym,entry=pos['date'],exit=final_dt,entry_price=pos['entry_price'],exit_price=price,qty=pos['qty'],pnl=pnl,return_pct=100*pnl/pos['cost'],reason='Liquidación fin prueba',bars=(final_dt-pos['date']).days))
        events.append(dict(date=final_dt,symbol=sym,event='SELL',price=price,reason='Liquidación fin prueba'))
    rows[-1]['equity']=cash;rows[-1]['cash']=cash;rows[-1]['positions']=0
    equity=pd.DataFrame(rows).set_index('date')
    trades=pd.DataFrame(records)
    ev=pd.DataFrame(events)
    return dict(equity=equity,trades=trades,events=ev,prepared=prepared,metrics=metrics(equity,trades,cfg.initial_cash))

def metrics(equity,trades,initial):
    e=equity.equity
    ret=e.pct_change().dropna()
    length=max(1,(e.index[-1]-e.index[0]).days)
    total=(e.iloc[-1]/initial)-1
    cagr=(e.iloc[-1]/initial)**(365.25/length)-1 if e.iloc[-1]>0 else -1
    dd=e/e.cummax()-1
    annual=365 if (e.index.dayofweek>=5).mean()>0.1 else 252
    sharpe=(ret.mean()/ret.std(ddof=1)*np.sqrt(annual)) if len(ret)>2 and ret.std(ddof=1)>0 else np.nan
    realized=trades.pnl if len(trades) else pd.Series(dtype=float)
    wins=realized[realized>0]; losses=realized[realized<0]
    pf=(wins.sum()/abs(losses.sum())) if len(losses) else np.nan
    return dict(initial=initial,ending=float(e.iloc[-1]),total_return_pct=float(total*100),cagr_pct=float(cagr*100),max_drawdown_pct=float(dd.min()*100),sharpe=float(sharpe),trades=int(len(trades)),win_rate_pct=float(100*len(wins)/len(trades)) if len(trades) else np.nan,profit_factor=float(pf),net_profit=float(e.iloc[-1]-initial),exposure_pct=float(100*(equity.positions>0).mean()))

def benchmark(raw,dates,initial):
    """Buy&hold equiponderado, indicativo; no simula rebalanceo ni costes."""
    series=[]
    for sym,d in raw.items():
        cl=d.Close.reindex(dates).ffill()
        first=cl.first_valid_index()
        if first is None:continue
        base=cl.loc[first]
        series.append((cl/base).fillna(1))
    if not series:return pd.Series(initial,index=dates)
    return pd.concat(series,axis=1).mean(axis=1)*initial
