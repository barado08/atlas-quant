import io
import numpy as np
import pandas as pd

UNIVERSE={
 'Cripto': {'BTC-USD':'Bitcoin','ETH-USD':'Ethereum','SOL-USD':'Solana'},
 'Acciones': {'AAPL':'Apple','MSFT':'Microsoft','NVDA':'Nvidia','AMZN':'Amazon','SAN.MC':'Santander'},
 'Índices / ETF': {'SPY':'S&P 500 ETF','QQQ':'Nasdaq 100 ETF','IWM':'Russell 2000 ETF','GLD':'Oro ETF'},
 'Forex': {'EURUSD=X':'EUR/USD','GBPUSD=X':'GBP/USD','JPY=X':'USD/JPY'}
}

def normalize(raw: pd.DataFrame) -> pd.DataFrame:
    x=raw.copy()
    if isinstance(x.columns,pd.MultiIndex):
        x.columns=x.columns.get_level_values(0)
    x.columns=[str(c).strip().title() for c in x.columns]
    if 'Date' in x.columns:
        x=x.set_index('Date')
    if 'Datetime' in x.columns:
        x=x.set_index('Datetime')
    cols=['Open','High','Low','Close']
    missing=[c for c in cols if c not in x]
    if missing:
        raise ValueError('Faltan columnas OHLC: '+', '.join(missing))
    x.index=pd.to_datetime(x.index,utc=True,errors='coerce').tz_convert(None).normalize()
    x=x.loc[~x.index.isna()].copy()
    x=x.loc[~x.index.duplicated(keep='last')].sort_index()
    for c in cols+(['Volume'] if 'Volume' in x else []):
        x[c]=pd.to_numeric(x[c],errors='coerce')
    x=x.dropna(subset=cols)
    x=x[(x[cols]>0).all(axis=1)]
    x=x[(x.High>=x[['Open','Close','Low']].max(axis=1)) & (x.Low<=x[['Open','Close','High']].min(axis=1))]
    if len(x)<125:
        raise ValueError('Se necesitan al menos 125 velas diarias válidas para indicadores y evaluación')
    return x[['Open','High','Low','Close']+(['Volume'] if 'Volume' in x else [])].astype(float)

def from_csv(upload):
    return normalize(pd.read_csv(upload))

def fetch(ticker: str, start: str, end: str):
    import yfinance as yf
    data=yf.download(ticker,start=start,end=end,interval='1d',auto_adjust=True,progress=False,threads=False)
    if data is None or data.empty:
        raise ValueError('Fuente sin datos para '+ticker)
    return normalize(data)

def demo_data(days=1100, seed=42):
    """ÚNICAMENTE para probar la interfaz; nunca evidencia de rentabilidad."""
    rng=np.random.default_rng(seed)
    dates=pd.bdate_range(end=pd.Timestamp.today().normalize(),periods=days)
    returns=rng.normal(.00025,.018,days)
    close=100*np.exp(np.cumsum(returns))
    op=np.r_[close[0],close[:-1]]*(1+rng.normal(0,.003,days))
    hi=np.maximum(op,close)*(1+rng.uniform(.002,.025,days))
    lo=np.minimum(op,close)*(1-rng.uniform(.002,.025,days))
    return normalize(pd.DataFrame({'Open':op,'High':hi,'Low':lo,'Close':close,'Volume':rng.integers(1000,10000,days)},index=dates))
