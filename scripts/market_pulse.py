"""ATLAS QUANT lightweight 5-minute market pulse.

This is a heartbeat / quote-monitoring utility, NOT a trading signal generator.
Uses public HTTP price endpoints without credentials; failures are visible and
never replaced by made-up prices. Scheduled execution is best effort, not SLA.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

COINS={
    "bitcoin":"BTC", "ethereum":"ETH", "solana":"SOL", "binancecoin":"BNB",
    "ripple":"XRP", "cardano":"ADA", "dogecoin":"DOGE",
    "avalanche-2":"AVAX", "chainlink":"LINK", "litecoin":"LTC",
    "bitcoin-cash":"BCH", "polkadot":"DOT"
}
KRAKEN_PAIRS={"XBTUSD":"BTC","ETHUSD":"ETH","SOLUSD":"SOL",
              "ADAUSD":"ADA","DOGEUSD":"DOGE","XRPUSD":"XRP"}
USER_AGENT="ATLAS-QUANT-Research/0.4 (open source, no trading orders)"

def _fetch_json(url: str, timeout: int=15) -> dict:
    req=urllib.request.Request(url,headers={
        "User-Agent": USER_AGENT,
        "Accept":"application/json"
    })
    with urllib.request.urlopen(req, timeout=timeout) as response:
        if response.status!=200:
            raise RuntimeError("Market API returned HTTP "+str(response.status))
        blob=response.read(200_000)
    payload=json.loads(blob)
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object from market provider")
    return payload

def _numeric(value):
    if isinstance(value,bool):return None
    try: n=float(value)
    except (ValueError, TypeError):return None
    return n if math.isfinite(n) and n>0 else None

def parse_coingecko(payload, clock=None):
    now=(clock or datetime.now(timezone.utc)).timestamp()
    prices={}
    ages={}
    for key,symbol in COINS.items():
        item=payload.get(key,{})
        if not isinstance(item,dict):continue
        price=_numeric(item.get("usd"))
        updated=item.get("last_updated_at")
        if price is None or not isinstance(updated,(int,float)):continue
        age=now-float(updated)
        if not -90<=age<=1200: continue  # do not silently treat stale quotes as live
        prices[symbol]=price;ages[symbol]=round(age)
    if len(prices)<6:
        raise ValueError(f"CoinGecko returned only {len(prices)} valid/fresh quotes")
    return {"provider":"CoinGecko public API","prices":prices,"age_seconds":ages,
            "coverage":len(prices),"partial":len(prices)<len(COINS)}

def parse_kraken(payload):
    errors=payload.get("error",[])
    if errors:raise RuntimeError(f"Kraken API error: {errors[:3]}")
    raw=payload.get("result")
    if not isinstance(raw,dict) or not raw:raise ValueError("Kraken response has no market data")
    prices={}
    for pair,data in raw.items():
        if not isinstance(data,dict):continue
        # Kraken keys vary by API aliases (XXBTZUSD, XETHZUSD, etc).
        p=str(pair).upper()
        symbol=None
        for short,s in KRAKEN_PAIRS.items():
            if short.replace('XBT','XXBT').replace('USD','ZUSD') in p or short in p:
                symbol=s;break
        if symbol is None and 'XBT' in p and 'USD' in p:symbol='BTC'
        if symbol is None and 'ETH' in p and 'USD' in p:symbol='ETH'
        if symbol is None:continue
        close=(data.get("c") or [None])[0]
        v=_numeric(close)
        if v is not None:prices[symbol]=v
    if len(prices)<2:raise ValueError("Kraken did not provide enough usable prices")
    return {"provider":"Kraken public spot ticker","prices":prices,
            "age_seconds":None,"coverage":len(prices),"partial":True}

def pulse(fetcher=_fetch_json, clock=None):
    clock=clock or datetime.now(timezone.utc)
    url="https://api.coingecko.com/api/v3/simple/price?"+urllib.parse.urlencode({
        "ids": ",".join(COINS),"vs_currencies":"usd","include_last_updated_at":"true"
    })
    errors=[]
    try:
        snapshot=parse_coingecko(fetcher(url),clock)
    except (OSError,RuntimeError,ValueError,KeyError,TypeError,urllib.error.URLError) as exc:
        errors.append(f"CoinGecko: {type(exc).__name__}: {str(exc)[:160]}")
        url="https://api.kraken.com/0/public/Ticker?"+urllib.parse.urlencode({
            "pair":",".join(KRAKEN_PAIRS)
        })
        try:
            snapshot=parse_kraken(fetcher(url))
        except (OSError,RuntimeError,ValueError,KeyError,TypeError,urllib.error.URLError) as secondary:
            errors.append(f"Kraken: {type(secondary).__name__}: {str(secondary)[:160]}")
            raise RuntimeError("All public crypto price sources failed: "+ " | ".join(errors)) from secondary
    snapshot.update({
        "checked_at_utc":clock.isoformat(),
        "task":"5-minute cryptocurrency market pulse; NOT a buy/sell signal",
        "market_data_validated":True,
        "errors":errors,
        "limitations":[
            "Crypto spot only; ETF/equities/FX do not offer 24/7 trading.",
            "5-minute GitHub schedule is best effort and can be delayed or skipped.",
            "CoinGecko is an indicative aggregated quote, not an executable order-book price.",
            "Kraken fallback quotes do not include per-ticker update timestamps.",
            "No profit predictions or real trading; daily swing paper engine runs separately."
        ]
    })
    return snapshot

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",default="monitor/latest.json")
    args=parser.parse_args()
    result=pulse()
    path=Path(args.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("PULSE_OK",json.dumps({"checked_at_utc":result["checked_at_utc"],
         "provider":result["provider"],"markets":result["coverage"],
         "partial":result["partial"],"BTC":result["prices"].get("BTC"),
         "ETH":result["prices"].get("ETH"),"AVAX":result["prices"].get("AVAX")},
         ensure_ascii=False),flush=True)
    if result["errors"]:print("PROVIDER_FALLBACK",json.dumps(result["errors"]),flush=True)

if __name__=="__main__":main()
