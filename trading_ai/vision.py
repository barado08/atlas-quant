"""Chart image interpreter using a local Ollama vision model.

The LLM interprets pixels, not verified OHLC data. Every reported price must be
visibly legible; probabilities and future performance are deliberately excluded.
"""
from __future__ import annotations
import base64
import hashlib
import io
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 8 * 1024 * 1024
MAX_DIM = 1800
ALLOWED = {'PNG', 'JPEG', 'WEBP'}
SCHEMA_VERSION = '1.0'

SYSTEM = '''Eres un analista visual de gráficos financieros. Analiza ÚNICAMENTE lo visible en la captura. No eres un asesor financiero.
Reglas estrictas:
- No inventes símbolo, precio, timeframe, fecha, indicadores o indicadores que no se ven. Usa null en campos desconocidos.
- Los valores numéricos sólo si son claramente legibles en los ejes o anotaciones. Nunca deduzcas un precio exacto por la posición de un pixel.
- Identifica si parece un gráfico financiero; si no, marca is_chart false.
- No pronostiques porcentajes de acierto, probabilidad de beneficio, ni señales de compra/venta ejecutables a partir de una imagen aislada.
- Distingue tendencias aparentes, patrones visuales y limitaciones. No afirmes datos OHLC, volumen ni indicadores calculados si no están disponibles.
- Devuelve estrictamente JSON en español, cumpliendo el esquema de claves solicitado y sin markdown.'''

PROMPT = '''Analiza la captura y devuelve JSON con estas claves exactas:
{"is_chart":true,"symbol":null,"timeframe":null,"chart_type":null,"visible_last_price":null,"visual_trend":"indeterminada","visual_patterns":[],"visible_indicators":[],"visible_levels":[],"observations":[],"limitations":[],"needs_verification":[],"summary":""}.
chart_type puede ser velas, linea, barras u otro. visual_trend: alcista, bajista, lateral, indeterminada. visible_levels: objetos {"kind":"soporte|resistencia|otro","price":numero_o_null,"why":"explicacion"}; incluye como máximo 5. No inventes cifras. Necesita verificación con OHLC para evaluar cualquier señal, stop o objetivo. Máximo 6 observaciones; resumen <=500 caracteres.'''

def prepare_image(blob: bytes):
    if not blob or len(blob)>MAX_BYTES:
        raise ValueError('Imagen vacía o demasiado grande (máximo 8 MB).')
    try:
        im=Image.open(io.BytesIO(blob))
        if im.format not in ALLOWED:raise ValueError('Formato no admitido: utiliza PNG, JPG o WEBP.')
        im.load()
        im=ImageOps.exif_transpose(im).convert('RGB')
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
        raise ValueError('No se ha podido leer la imagen de forma segura.') from e
    im.thumbnail((MAX_DIM,MAX_DIM))
    buffer=io.BytesIO();im.save(buffer,format='JPEG',quality=88,optimize=True)
    return buffer.getvalue(), {'sha256_original': hashlib.sha256(blob).hexdigest(), 'width': im.width, 'height': im.height}

def parse_json(text: str)->dict:
    text=text.strip()
    if text.startswith('```'):
        text=re.sub(r'^```(?:json)?\s*|\s*```$', '', text, flags=re.I).strip()
    try:obj=json.loads(text)
    except json.JSONDecodeError as e:raise ValueError('El modelo local no devolvió JSON válido. Prueba otro modelo de visión.') from e
    if not isinstance(obj,dict):raise ValueError('Respuesta inesperada del modelo local.')
    return obj

def normalize_report(result: dict)->dict:
    trend=str(result.get('visual_trend') or 'indeterminada').lower().strip()
    if trend not in ('alcista','bajista','lateral','indeterminada'):trend='indeterminada'
    def text_or_none(v):
        return str(v).strip()[:160] if isinstance(v,(str,int,float)) and str(v).strip() else None
    def number_or_none(v):
        if isinstance(v,bool) or v is None:return None
        if isinstance(v,str):
            v=v.strip().replace(' ','')
            if not re.fullmatch(r'-?\d+(?:\.\d+)?',v):return None
        try:
            x=float(v)
            return x if 0<x<1e12 else None
        except (ValueError,TypeError,OverflowError):return None
    def strs(key,limit):
        vals=result.get(key)
        return [str(x)[:300] for x in vals[:limit] if isinstance(x,(str,int,float))] if isinstance(vals,list) else []
    levels=[]
    for x in (result.get('visible_levels') or [])[:5] if isinstance(result.get('visible_levels'),list) else []:
        if not isinstance(x,dict):continue
        kind=str(x.get('kind','otro')).lower()
        levels.append({'kind':kind if kind in ('soporte','resistencia','otro') else 'otro','price':number_or_none(x.get('price')),'why':str(x.get('why') or '')[:300]})
    return {'schema_version':SCHEMA_VERSION,'is_chart':result.get('is_chart') is True,
        'symbol':text_or_none(result.get('symbol')),'timeframe':text_or_none(result.get('timeframe')),
        'chart_type':text_or_none(result.get('chart_type')),'visible_last_price':number_or_none(result.get('visible_last_price')),
        'visual_trend':trend,'visual_patterns':strs('visual_patterns',6),'visible_indicators':strs('visible_indicators',8),
        'visible_levels':levels,'observations':strs('observations',6),'limitations':strs('limitations',6),
        'needs_verification':strs('needs_verification',6),'summary':str(result.get('summary') or '')[:500]}

def analyze_image(blob: bytes, model: str='qwen2.5vl:3b', endpoint: str='http://127.0.0.1:11434', timeout: int=180)->dict:
    """Call local Ollama only (no hosted API or paid key)."""
    if not re.fullmatch(r'[A-Za-z0-9_.:\-]{2,100}',model):raise ValueError('Nombre de modelo inválido.')
    if endpoint.rstrip('/') not in ('http://127.0.0.1:11434','http://localhost:11434'):
        raise ValueError('Por privacidad, sólo se permite Ollama local en puerto 11434.')
    jpg,meta=prepare_image(blob)
    body={'model':model,'stream':False,'format':'json','options':{'temperature':0,'num_predict':1500},
          'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':PROMPT,'images':[base64.b64encode(jpg).decode('ascii')]}]}
    request=urllib.request.Request(endpoint.rstrip('/')+'/api/chat',data=json.dumps(body).encode('utf-8'),headers={'Content-Type':'application/json'},method='POST')
    try:
        with urllib.request.urlopen(request,timeout=timeout) as resp:
            if resp.status!=200:raise RuntimeError(f'Ollama respondió con código HTTP {resp.status}.')
            data=json.load(resp)
    except urllib.error.URLError as e:
        raise RuntimeError('No se pudo conectar a Ollama local. Comprueba que está instalado, iniciado y que el modelo está descargado.') from e
    content=data.get('message',{}).get('content','')
    report=normalize_report(parse_json(content))
    report.update({'generated_at_utc':datetime.now(timezone.utc).isoformat(),'model':model,
                   'image_sha256':meta['sha256_original'],'image_width':meta['width'],'image_height':meta['height'],
                   'source':'captura de pantalla; estimación visual sin validación OHLC',
                   'trading_signal':'NO VALIDADA: una captura no demuestra rentabilidad ni determina ejecución'})
    return report
