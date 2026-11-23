import numpy as np
import pandas as pd

def enrich(df: pd.DataFrame, fast=20, slow=100, rsi_n=14, atr_n=14, breakout=20) -> pd.DataFrame:
    x = df.copy().sort_index()
    c, h, l = x['Close'], x['High'], x['Low']
    x['ema_fast'] = c.ewm(span=fast, adjust=False, min_periods=fast).mean()
    x['ema_slow'] = c.ewm(span=slow, adjust=False, min_periods=slow).mean()
    diff = c.diff()
    gain = diff.clip(lower=0).ewm(alpha=1/rsi_n, adjust=False, min_periods=rsi_n).mean()
    loss = (-diff.clip(upper=0)).ewm(alpha=1/rsi_n, adjust=False, min_periods=rsi_n).mean()
    rs = gain / loss.replace(0, np.nan)
    x['rsi'] = (100-100/(1+rs)).where(loss != 0, 100).where(gain != 0, 0)
    tr = pd.concat([(h-l), (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    x['atr'] = tr.ewm(alpha=1/atr_n, adjust=False, min_periods=atr_n).mean()
    x['donchian'] = h.shift(1).rolling(breakout, min_periods=breakout).max()
    x['ret_1'] = c.pct_change()
    x['vol20'] = x['ret_1'].rolling(20).std() * np.sqrt(252)
    return x

def signals(df: pd.DataFrame, strategy: str) -> pd.DataFrame:
    x=df.copy()
    ready = x[['ema_fast','ema_slow','rsi','atr','donchian']].notna().all(axis=1)
    if strategy == 'Tendencia + pullback':
        enter=(x['Close']>x['ema_slow']) & (x['ema_fast']>x['ema_slow']) & (x['Close'].shift(1)<=x['ema_fast'].shift(1)) & (x['Close']>x['ema_fast']) & x['rsi'].between(40,75)
        exit_=(x['Close']<x['ema_fast']) | (x['rsi']>82)
    elif strategy == 'Ruptura Donchian':
        enter=(x['Close']>x['donchian']) & (x['Close']>x['ema_slow'])
        exit_=x['Close']<x['ema_fast']
    elif strategy == 'Cruce EMA':
        enter=(x['ema_fast']>x['ema_slow']) & (x['ema_fast'].shift(1)<=x['ema_slow'].shift(1))
        exit_=(x['ema_fast']<x['ema_slow'])
    else:
        raise ValueError('Estrategia desconocida')
    x['entry_signal'] = (enter & ready).fillna(False).astype(bool)
    x['exit_signal'] = exit_.fillna(False).astype(bool)
    return x
