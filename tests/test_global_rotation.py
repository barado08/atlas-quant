from datetime import datetime, timezone, timedelta

from scripts.global_universe import catalog,choose_shard,UNIVERSE
from scripts.rotate_discovery import slot_for, next_unscanned_or_oldest


def test_world_catalog_covers_all_families_and_regions():
    c=catalog()
    assert len(c)>=200
    assert len(c)==len({x[1] for x in c})
    assert set(g for g,_ in c)==set(UNIVERSE)
    assert all(g and s for g,s in c)


def test_every_symbol_appears_exactly_once_per_12_shard_cycle():
    full=catalog()
    shards=[choose_shard(i,12) for i in range(12)]
    combined=[p for part in shards for p in part]
    assert set(combined)==set(full)
    assert len(combined)==len(full)
    assert max(len(part) for part in shards)-min(len(part) for part in shards)<=1


def test_shards_include_several_market_families():
    c=catalog()
    for i in range(12):
        assert len({g for g,_ in choose_shard(i,12)})>=4


def test_slot_advances_every_five_minutes_and_repeats_after_one_hour():
    t=datetime(2026,11,23,0,0,tzinfo=timezone.utc)
    slots=[slot_for(t+timedelta(minutes=5*i),12) for i in range(12)]
    assert len(set(slots))==12
    assert slot_for(t+timedelta(minutes=60),12)==slots[0]

def test_missing_shards_get_priority_over_recent_shards(tmp_path):
    import json
    (tmp_path/'slot_00.json').write_text(json.dumps({'date_utc':'2026-11-24T02:00:00+00:00'}))
    (tmp_path/'slot_01.json').write_text(json.dumps({'date_utc':'2026-11-24T01:00:00+00:00'}))
    assert next_unscanned_or_oldest(tmp_path,4)==2


def test_when_complete_oldest_report_gets_priority(tmp_path):
    import json
    for slot,date in enumerate(['2026-11-24T03:00:00+00:00','2026-11-24T01:00:00+00:00','2026-11-24T02:00:00+00:00']):
        (tmp_path/f'slot_{slot:02d}.json').write_text(json.dumps({'date_utc':date}))
    assert next_unscanned_or_oldest(tmp_path,3)==1


def test_corrupted_report_is_treated_as_missing(tmp_path):
    (tmp_path/'slot_00.json').write_text('bad JSON')
    (tmp_path/'slot_01.json').write_text('{"date_utc":"2026-11-24T00:00:00+00:00"}')
    assert next_unscanned_or_oldest(tmp_path,2)==0
