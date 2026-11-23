"""Curated global multi-market Yahoo Finance symbol universe for rotating research.

This is a RESEARCH COVERAGE CATALOG, not all securities worldwide.
Source data availability and rights are checked at runtime; delisted or renamed
instruments need point-in-time reference data for a commercial-grade universe.
"""
from __future__ import annotations

UNIVERSE = {
  "Cripto": [
    "BTC-USD","ETH-USD","SOL-USD","BNB-USD","XRP-USD","ADA-USD","DOGE-USD",
    "AVAX-USD","LINK-USD","LTC-USD","BCH-USD","DOT-USD","XLM-USD","TRX-USD",
    "ATOM-USD","ETC-USD","FIL-USD","NEAR-USD","UNI-USD","AAVE-USD",
    "ALGO-USD","ICP-USD","HBAR-USD","VET-USD","SUI20947-USD","APT21794-USD",
    "MKR-USD","EOS-USD","XTZ-USD","THETA-USD"
  ],
  "Divisas": [
    "EURUSD=X","GBPUSD=X","JPY=X","CHF=X","CAD=X","AUDUSD=X","NZDUSD=X",
    "EURGBP=X","EURJPY=X","GBPJPY=X","EURCHF=X","EURCAD=X","EURAUD=X",
    "GBPAUD=X","GBPCHF=X","AUDJPY=X","CADJPY=X","USDSEK=X","USDNOK=X",
    "USDMXN=X","USDBRL=X","USDZAR=X","USDSGD=X","USDINR=X",
  ],
  "ETF globales e indices": [
    "SPY","QQQ","DIA","IWM","VTI","VOO","EFA","EEM","VEA","VWO",
    "EWJ","EWG","EWU","EWQ","EWP","EWI","EWC","EWA","EWH","EWS",
    "EWY","EWT","INDA","FXI","MCHI","KWEB","ARKK","XLK","XLF","XLE",
    "XLI","XLV","XLP","XLY","XLU","XLB","XLC","XBI","SMH","SOXX",
  ],
  "Acciones EEUU": [
    "AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","AVGO","AMD",
    "NFLX","ORCL","CRM","ADBE","INTC","QCOM","TXN","COST","WMT",
    "HD","LOW","UNH","JNJ","PFE","ABBV","LLY","MRK","KO","PEP",
    "PG","MCD","DIS","UBER","JPM","BAC","GS","MS","V","MA","PYPL",
    "BRK-B","CAT","BA","GE","NKE","T","VZ","XOM","CVX",
  ],
  "Acciones Europa": [
    "SAN.MC","BBVA.MC","IBE.MC","ITX.MC","TEF.MC","REP.MC",
    "SAP.DE","SIE.DE","ALV.DE","DTE.DE","BMW.DE","BAS.DE","ADS.DE",
    "MC.PA","OR.PA","TTE.PA","AIR.PA","BNP.PA","SU.PA","CAP.PA",
    "ASML.AS","INGA.AS","AD.AS","SHELL.AS",
    "AZN.L","HSBA.L","ULVR.L","BP.L","RIO.L","GSK.L",
    "NESN.SW","NOVN.SW","ROG.SW","UBSG.SW",
    "ENI.MI","ISP.MI","ENEL.MI",
  ],
  "Acciones Asia Pacifico": [
    "7203.T","6758.T","9984.T","8306.T","6501.T","8035.T","7974.T",
    "0700.HK","9988.HK","1299.HK","0005.HK","3690.HK","1810.HK",
    "005930.KS","000660.KS","035420.KS",
    "2330.TW","2317.TW","2454.TW",
    "BHP.AX","CBA.AX","CSL.AX","WBC.AX","RIO.AX","NAB.AX"
  ],
  "Acciones America Canada Brasil": [
    "SHOP.TO","RY.TO","TD.TO","ENB.TO","SU.TO","BNS.TO","BCE.TO",
    "PETR4.SA","VALE3.SA","ITUB4.SA","BBDC4.SA","ABEV3.SA",
    "WEGE3.SA","BBAS3.SA","B3SA3.SA","RENT3.SA","SUZB3.SA",
  ],
  "Bonos materias primas REIT": [
    "TLT","IEF","SHY","BND","AGG","LQD","HYG","JNK","TIP","EMB",
    "GLD","IAU","SLV","PPLT","DBA","DBC","USO","UNG",
    "VNQ","IYR","SCHH","O","PLD","AMT","EQIX",
    "GC=F","SI=F","HG=F","CL=F","BZ=F","NG=F","ZC=F","ZS=F",
    "ZW=F","KC=F","SB=F","CT=F",
  ],
}

def catalog():
    """Round-robin interleaving prevents any batch being confined to one market."""
    groups=list(UNIVERSE)
    seen=set(); out=[]
    pos=0
    while True:
        added=False
        for group in groups:
            group_list=UNIVERSE[group]
            if pos<len(group_list):
                symbol=group_list[pos]
                if symbol not in seen:
                    out.append((group,symbol))
                    seen.add(symbol);added=True
        if not added:break
        pos+=1
    return out

def choose_shard(slot:int,shards:int=24):
    if shards<1 or slot<0:raise ValueError("Invalid shard parameters")
    records=catalog()
    return [item for i,item in enumerate(records) if i%shards==slot%shards]
