"""Fair round-robin worldwide research scanner.

Each best-effort five-minute GitHub trigger researches one twelfth of the
supported catalog. Missing or old slices get priority after delayed or dropped triggers; 12 successful\nruns are required for a full cycle, not necessarily one hour.
The exact same data may recur between runs; repeated backtests alone are
not independent validation and cannot certify new profitability.
"""
from __future__ import annotations
import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.global_universe import catalog


def slot_for(ts:datetime.datetime,shards:int)->int:
    if ts.tzinfo is None:raise ValueError("UTC clock must be timezone-aware")
    if shards<=0:raise ValueError("shards must be >0")
    return int(ts.timestamp()//300)%shards


def next_unscanned_or_oldest(report_dir:Path,shards:int)->int:
    """Always catch up missing/oldest shards after dropped scheduler events.

    Use persisted report timestamps, not wall-clock modulus. A delayed Actions run
    therefore covers the least recently scanned slice rather than repeating whichever
    wall-clock slot happened to be triggered.
    """
    if shards<=0:raise ValueError("shards must be >0")
    epoch=datetime.datetime(1970,1,1,tzinfo=datetime.timezone.utc)
    order=[]
    for i in range(shards):
        path=report_dir/f"slot_{i:02d}.json"
        timestamp=epoch
        if path.exists():
            try:
                obj=json.loads(path.read_text(encoding="utf-8"))
                stamp=datetime.datetime.fromisoformat(obj["date_utc"].replace("Z","+00:00"))
                if stamp.tzinfo is not None:timestamp=stamp.astimezone(datetime.timezone.utc)
            except (KeyError,TypeError,ValueError,OSError,json.JSONDecodeError):
                pass
        order.append((timestamp,i))
    return min(order)[1]


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--shards",type=int,default=12)
    ap.add_argument("--slot",type=int,default=None,
                    help="Explicit shard slot for tests; default oldest saved shard")
    opts=ap.parse_args()
    if not 1<=opts.shards<=48:raise SystemExit("Invalid shard count")
    slot=opts.slot if opts.slot is not None else next_unscanned_or_oldest(
        ROOT/"reports"/"shards",opts.shards)
    if not 0<=slot<opts.shards:raise SystemExit("Invalid shard slot")
    total=len(catalog())
    batch=sum(i%opts.shards==slot for i in range(total))
    print(f"WORLD_SHARD_START slot={slot} of {opts.shards} | assets={batch}/{total} "
          f"| each asset targeted every {opts.shards*5} minutes (best effort)",
          flush=True)
    if batch==0:raise SystemExit("Shard has no instruments")
    target=f"reports/shards/slot_{slot:02d}.json"
    cmd=[sys.executable,str(ROOT/"scripts"/"strategy_discovery.py"),
         "--universe","global","--shard-count",str(opts.shards),
         "--shard-index",str(slot),"--output",target]
    completed=subprocess.run(cmd,check=False,cwd=str(ROOT))
    print(f"WORLD_SHARD_EXIT status={completed.returncode} "
          f"output={target}",flush=True)
    return completed.returncode


if __name__=="__main__":raise SystemExit(main())
