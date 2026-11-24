from datetime import datetime, timezone, timedelta
from dataclasses import asdict
import json
from scripts.refresh_paper_if_due import candidate_ids, is_due
from trading_ai.engine import Config


NOW=datetime(2026,11,24,8,tzinfo=timezone.utc)


def test_new_candidates_force_immediate_paper_enrollment():
    state={"accounts":{"abc":{}},"last_run_utc":NOW.isoformat()}
    assert is_due(state,{"abc","new"},NOW)==(True,"new_research_candidates")


def test_recent_paper_avoids_yahoo_rate_limit():
    state={"accounts":{"abc":{}},"last_run_utc":(NOW-timedelta(minutes=20)).isoformat()}
    assert is_due(state,{"abc"},NOW)==(False,"already_fresh")


def test_freshness_catches_up_after_scheduled_workflow_is_skipped():
    state={"accounts":{},"last_run_utc":(NOW-timedelta(hours=8)).isoformat()}
    assert is_due(state,set(),NOW)==(True,"scheduled_refresh")


def test_malformed_clock_is_due():
    state={"accounts":{},"last_run_utc":"yesterday"}
    assert is_due(state,set(),NOW)==(True,"invalid_timestamp")


def test_candidate_aggregation_across_global_shards(tmp_path):
    shards=tmp_path/"shards";shards.mkdir()
    cfg=asdict(Config(strategy="Ruptura Donchian"))
    (shards/"slot_00.json").write_text(json.dumps({"results":[{
        "symbol":"ALGO-USD","status":"RESEARCH_SHORTLIST","selected":{"params":cfg}
    }]}))
    (shards/"slot_01.json").write_text(json.dumps({"results":[{
        "symbol":"AVAX-USD","status":"RESEARCH_SHORTLIST","selected":{"params":cfg}
    }]}))
    (shards/"slot_02.json").write_text(json.dumps({"results":[{
        "symbol":"ETH-USD","status":"FAILED_ROBUSTNESS_GATES","selected":{"params":cfg}
    }]}))
    assert len(candidate_ids(shards,tmp_path/"no_full_report.json"))==2
