"""Conditionally refresh forward-only paper trading after a new research shard.

Avoids needless Yahoo requests on each five-minute scan. Intended to run
from an already refreshed main branch with current shard reports.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.paper_tracker import eligible_from_report

def candidate_ids(report_dir:Path, full_report:Path):
    paths=sorted(report_dir.glob('slot_*.json'))
    if full_report.exists():paths.append(full_report)
    ids=set()
    for path in paths:
        report=json.loads(path.read_text(encoding="utf-8"))
        ids.update(key for key,_,_ in eligible_from_report(report))
    return ids

def is_due(state:dict|None, ids:set[str], now:datetime, hours:int=6)->tuple[bool,str]:
    if state is None:return True,'first_run'
    saved=set(state.get('accounts',{}))
    if ids-saved:return True,'new_research_candidates'
    timestamp=state.get('last_run_utc')
    if not timestamp:return True,'no_prior_run'
    try:
        stamp=datetime.fromisoformat(timestamp.replace('Z','+00:00'))
        if stamp.tzinfo is None: return True,'invalid_timestamp'
        age=now.astimezone(timezone.utc)-stamp.astimezone(timezone.utc)
    except (ValueError,TypeError):
        return True,'invalid_timestamp'
    if age>=timedelta(hours=hours):return True,'scheduled_refresh'
    return False,'already_fresh'

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--max-age-hours',type=int,default=6)
    a=p.parse_args()
    if not 1<=a.max_age_hours<=24:raise SystemExit('Bad paper refresh interval')
    state_path=ROOT/'paper'/'state.json'
    state=json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else None
    ids=candidate_ids(ROOT/'reports'/'shards',ROOT/'reports'/'discovery_latest.json')
    due,reason=is_due(state,ids,datetime.now(timezone.utc),a.max_age_hours)
    print('PAPER_REFRESH_DECISION',json.dumps({'due':due,'reason':reason,
          'candidate_count':len(ids),'existing_accounts':len(state.get('accounts',{})) if state else 0}),flush=True)
    if not due:return 0
    cmd=[sys.executable,str(ROOT/'scripts'/'paper_tracker.py')]
    return subprocess.run(cmd,check=False,cwd=str(ROOT)).returncode

if __name__=='__main__':raise SystemExit(main())
