import io
import json
from unittest.mock import patch
from PIL import Image
import pytest
from trading_ai.vision import prepare_image, normalize_report, parse_json, analyze_image

def sample():
    x=Image.new('RGB',(600,300),'white');buf=io.BytesIO();x.save(buf,format='PNG');return buf.getvalue()

def test_image_hash_and_sizes():
    blob=sample();out,meta=prepare_image(blob)
    assert out.startswith(b'\xff\xd8') and meta['width']==600 and len(meta['sha256_original'])==64

def test_invalid_image():
    with pytest.raises(ValueError):prepare_image(b'not a photo')

def test_invalid_host_blocked():
    with pytest.raises(ValueError,match='local'):analyze_image(sample(),endpoint='https://example.com')

def test_parse_markdown():
    assert parse_json('```json\n{"is_chart":true}\n```')['is_chart'] is True

def test_sanitize_hallucinated_price():
    r=normalize_report({'is_chart':True,'visible_last_price':'not clear','visual_trend':'100% guaranteed','visible_levels':[{'kind':'soporte','price':'unknown','why':'pixel'}]})
    assert r['visible_last_price'] is None and r['visual_trend']=='indeterminada' and r['visible_levels'][0]['price'] is None

def test_local_api_mocked():
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def read(self):return b''
    payload={'message':{'content':json.dumps({'is_chart':True,'visual_trend':'lateral','symbol':'BTC/USDT','summary':'Consolidación visible'})}}
    class FakeResponse(Response):
        def read(self):return json.dumps(payload).encode()
    with patch('urllib.request.urlopen',return_value=FakeResponse()) as mocked:
        res=analyze_image(sample())
        assert res['is_chart'] is True and res['visual_trend']=='lateral'
        request=mocked.call_args.args[0]
        assert request.full_url=='http://127.0.0.1:11434/api/chat'
        assert json.loads(request.data)['messages'][1]['images']
