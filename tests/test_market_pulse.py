from datetime import datetime, timezone
from unittest.mock import Mock
import pytest

from scripts.market_pulse import parse_coingecko,parse_kraken,pulse,COINS


T=datetime(2026,11,23,15,30,tzinfo=timezone.utc)


def test_coingecko_rejects_expired_prices():
    payload={key:{"usd":i+2.0,"last_updated_at":int(T.timestamp())-60}
             for i,key in enumerate(COINS)}
    result=parse_coingecko(payload,T)
    assert result["coverage"]==len(COINS)
    assert result["prices"]["BTC"]==2
    assert result["age_seconds"]["BTC"]==60
    payload["bitcoin"]["last_updated_at"]=int(T.timestamp())-1800
    result=parse_coingecko(payload,T)
    assert "BTC" not in result["prices"]


def test_kraken_parses_multiple_aliases():
    result=parse_kraken({"error":[],"result":{
        "XXBTZUSD":{"c":["60000.0","1"]},
        "XETHZUSD":{"c":["3200.0","1"]},
        "SOLUSD":{"c":["100.0","1"]}
    }})
    assert result["prices"]["BTC"]==60000.
    assert result["prices"]["ETH"]==3200.
    assert result["prices"]["SOL"]==100.


def test_kraken_rejects_api_errors():
    with pytest.raises(RuntimeError):
        parse_kraken({"error":["EGeneral:Invalid arguments"],"result":{}})


def test_uses_fallback_with_no_fake_values():
    called=[]
    def fetcher(url):
        called.append(url)
        if "coingecko" in url:raise OSError("rate limited")
        return {"error":[],"result":{
            "XXBTZUSD":{"c":["60000.0","1"]},
            "XETHZUSD":{"c":["3000.0","1"]}
        }}
    r=pulse(fetcher=fetcher,clock=T)
    assert r["provider"]=="Kraken public spot ticker"
    assert r["prices"]=={"BTC":60000.,"ETH":3000.}
    assert len(called)==2
    assert r["errors"]


def test_fails_if_both_sources_fail():
    with pytest.raises(RuntimeError,match="All public crypto price sources failed"):
        pulse(fetcher=lambda url: (_ for _ in ()).throw(OSError("offline")),clock=T)


def test_partial_coingecko_requires_minimum_quotes():
    fake={"bitcoin":{"usd":60000.0,"last_updated_at":int(T.timestamp())}}
    with pytest.raises(ValueError):parse_coingecko(fake,T)
