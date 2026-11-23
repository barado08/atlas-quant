"""Standalone Streamlit view integrated into the existing dashboard."""
import json
import streamlit as st
from trading_ai.vision import analyze_image, prepare_image
from trading_ai.data import fetch

def render():
    st.subheader('Interpretación de gráficos con IA local')
    st.caption('Capturas PNG/JPG/WEBP · IA ejecutada en tu propio ordenador mediante Ollama · sin API de pago · sin conectar bróker')
    st.warning('La IA puede leer mal símbolos, velas y números. Su lectura visual NO es una señal verificada ni una predicción de rentabilidad.')
    with st.expander('Instalación del modelo de visión gratuito',expanded=True):
        st.markdown('''1. Instala [Ollama](https://ollama.com/download) en Windows/macOS/Linux.
2. Abre PowerShell o una terminal y ejecuta `ollama pull qwen2.5vl:3b` (descarga de varios GB; requiere memoria suficiente).
3. Asegúrate de que Ollama esté en ejecución (`ollama serve` si no se ha iniciado automáticamente).
4. Sube una captura legible de TradingView y pulsa **Analizar captura**.

El modelo puede cambiarse por otro multimodal instalado localmente. **No hay coste de API**, pero sí consumo de memoria, procesamiento, almacenamiento y electricidad.''')
    model=st.text_input('Modelo local de Ollama',value='qwen2.5vl:3b',help='Ej. qwen2.5vl:3b; debe admitir imágenes.')
    upload=st.file_uploader('Sube tu captura (máximo 8 MB)',type=['png','jpg','jpeg','webp'],key='vision_upload')
    blob=None
    if upload:
        blob=upload.getvalue()
        try:
            _,meta=prepare_image(blob)
            st.image(blob,caption='Imagen original: el sistema no coloca órdenes',use_container_width=True)
            st.caption('Huella SHA-256: '+meta['sha256_original'])
        except ValueError as exc:st.error(str(exc));blob=None
    if st.button('Analizar captura con IA local',type='primary',disabled=blob is None):
        try:
            with st.spinner('Procesando imagen en tu equipo...'):
                st.session_state['vision_report']=analyze_image(blob,model=model)
        except (ValueError,RuntimeError,TimeoutError, OSError) as e:st.error(str(e))
    report=st.session_state.get('vision_report')
    if not report:return
    st.divider()
    if report['image_sha256']!=(meta['sha256_original'] if upload and blob else None):
        st.info('El informe mostrado corresponde a otra captura. Pulsa Analizar para actualizarlo.')
    if not report['is_chart']:
        st.error('El modelo no ha identificado un gráfico financiero. Comprueba la imagen.');return
    c1,c2,c3=st.columns(3)
    c1.metric('Símbolo detectado',report['symbol'] or 'No legible')
    c2.metric('Temporalidad',report['timeframe'] or 'No legible')
    c3.metric('Tendencia visual',report['visual_trend'].capitalize())
    st.markdown('**Resumen del modelo**')
    st.write(report['summary'] or 'El modelo no proporcionó un resumen.')
    if report['visible_levels']:
        st.markdown('**Niveles visibles (no verificados)**')
        st.dataframe(report['visible_levels'],use_container_width=True,hide_index=True)
    for label,key in [('Observaciones','observations'),('Patrones aparentes','visual_patterns'),('Indicadores identificados','visible_indicators'),('Limitaciones','limitations'),('Qué verificar','needs_verification')]:
        if report[key]:st.markdown('**'+label+'**');st.write('\n'.join('• '+s+'\n' for s in report[key]))
    st.caption('Modelo '+report['model']+' · SHA-256 '+report['image_sha256']+' · '+report['generated_at_utc'])
    st.download_button('Descargar análisis auditable (JSON)',json.dumps(report,ensure_ascii=False,indent=2).encode('utf-8'),'analisis_captura.json','application/json')
    st.divider()
    st.markdown('**Comprobación independiente contra precios históricos**')
    st.caption('Para verificar activo y precios se usa Yahoo Finance de forma independiente. No se acepta el símbolo ni la temporalidad inferidos como garantía.')
    ticker=st.text_input('Ticker Yahoo Finance confirmado por ti',value='',placeholder='BTC-USD, SPY, EURUSD=X...',key='vision_ticker')
    if st.button('Consultar últimos cierres diarios reales',disabled=not ticker.strip()):
        from datetime import date,timedelta
        try:
            end=date.today()+timedelta(days=1)
            raw=fetch(ticker.strip().upper(),str(end-timedelta(days=250)),str(end))
            last=raw.iloc[-1]
            st.success(f'Último cierre diario disponible de {ticker}: {float(last.Close):,.6f} ({raw.index[-1].date()}). Fuente Yahoo Finance.')
            st.dataframe(raw.tail(10),use_container_width=True)
            if report['visible_last_price'] is not None:
                st.info('Precio leído en la imagen: '+str(report['visible_last_price'])+'. No deben compararse directamente precios de distintos instantes o temporalidades.')
            st.info('Para evaluar una estrategia con este activo, vuelve a «Laboratorio de backtesting» y ejecútalo sobre sus datos históricos.')
        except Exception as e:st.error('No fue posible verificar los datos históricos: '+str(e))
