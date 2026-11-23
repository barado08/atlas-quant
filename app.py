import io, json, zipfile
from datetime import date, timedelta
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from trading_ai.data import UNIVERSE, fetch, normalize, demo_data
from trading_ai.engine import Config, backtest, benchmark

st.set_page_config(page_title='ATLAS QUANT | Research Terminal',page_icon='📊',layout='wide',initial_sidebar_state='expanded')
st.markdown('''<style>.block-container{padding-top:1.8rem;max-width:1550px}.stMetric{padding:12px 16px;border:1px solid #334155;border-radius:10px}h1{letter-spacing:-.04em}</style>''',unsafe_allow_html=True)
st.title('ATLAS QUANT  /  Research Terminal')
st.caption('Laboratorio cuantitativo multi-mercado · Swing diario · Backtesting reproducible · Sin órdenes reales')

with st.sidebar:
    workspace=st.radio('Módulo', ['Laboratorio de backtesting','IA visual: analizar capturas'], key='workspace')
if workspace=='IA visual: analizar capturas':
    from trading_ai.vision_ui import render
    render()
    st.stop()

@st.cache_data(ttl=3600,show_spinner=False)
def load_market(symbol,start,end):return fetch(symbol,start,end)

with st.sidebar:
    st.header('01 / Datos y universo')
    mode=st.radio('Origen', ['Mercados (Yahoo Finance)','CSV propio','DEMOSTRACIÓN SINTÉTICA'],help='Los datos sintéticos nunca acreditan resultados reales')
    raw={}
    if mode=='Mercados (Yahoo Finance)':
        category=st.multiselect('Mercados',list(UNIVERSE),default=['Cripto','Acciones','Índices / ETF','Forex'])
        choices={sym:f'{name} · {cat} · {sym}' for cat in category for sym,name in UNIVERSE[cat].items()}
        defaults=[s for s in ['BTC-USD','AAPL','SPY','EURUSD=X'] if s in choices]
        symbols=st.multiselect('Activos', list(choices),default=defaults,format_func=lambda s:choices[s],help='Se recomienda comenzar con 2–6 activos para pruebas rápidas')
        custom=st.text_input('Añadir ticker Yahoo (opcional)',placeholder='Ej. GC=F')
        if custom.strip():symbols=list(dict.fromkeys(symbols+[custom.strip().upper()]))
        start=st.date_input('Desde',date.today()-timedelta(days=6*365))
        end=st.date_input('Hasta (incluido)',date.today())
    elif mode=='CSV propio':
        uploads=st.file_uploader('Archivos CSV: Date,Open,High,Low,Close[,Volume]',type='csv',accept_multiple_files=True)
    else:
        st.error('SIMULACIÓN FICTICIA. NO USAR PARA EVALUAR RENTABILIDAD.')
        seed=st.number_input('Semilla reproducible',value=42,min_value=0,step=1)
    st.divider()
    st.header('02 / Estrategia')
    strategy=st.selectbox('Reglas', ['Tendencia + pullback','Ruptura Donchian','Cruce EMA'])
    fast=st.slider('EMA rápida',5,80,20)
    slow=st.slider('EMA lenta',81,250,100)
    breakout=st.slider('Canal Donchian',10,100,20)
    st.divider()
    st.header('03 / Riesgo realista')
    initial_cash=st.number_input('Capital inicial',min_value=100.,value=10000.,step=1000.)
    risk_pct=st.slider('Riesgo máximo por operación (%)',0.1,3.,1.,0.1)
    max_allocation=st.slider('Asignación máxima por activo (%)',5,100,20,5)
    max_positions=st.slider('Posiciones simultáneas',1,15,5)
    stop_atr=st.slider('Distancia stop (ATR)',0.5,5.,2.,0.25)
    rr=st.slider('Objetivo / riesgo',0.5,6.,2.,0.25)
    fee_bps=st.number_input('Comisión por lado (puntos básicos)',min_value=0.,value=10.,step=1.)
    slip_bps=st.number_input('Slippage por ejecución (pb)',min_value=0.,value=5.,step=1.)
    split=st.slider('Entrenamiento / evaluación fuera de muestra',50,85,70,5)
    run=st.button('▶ EJECUTAR BACKTEST',use_container_width=True,type='primary')

if run:
    try:
        if mode=='Mercados (Yahoo Finance)':
            if not symbols:raise ValueError('Selecciona al menos un activo.')
            if start>=end:raise ValueError('La fecha inicial debe ser anterior a la final')
            end_inclusive=(end+timedelta(days=1)).isoformat()
            for sym in symbols:
                try:raw[sym]=load_market(sym,start.isoformat(),end_inclusive)
                except Exception as e:st.warning(f'{sym}: {e}')
        elif mode=='CSV propio':
            if not uploads:raise ValueError('Carga al menos un CSV con datos reales')
            for u in uploads:raw[u.name.replace('.csv','')]=normalize(pd.read_csv(u))
        else:raw={'FICTICIO':demo_data(seed=int(seed))}
        if not raw:raise ValueError('Ningún activo válido disponible. Revisa fuente, fechas y símbolos.')
        cfg=Config(initial_cash=initial_cash,risk_pct=risk_pct,max_allocation_pct=max_allocation,fee_bps=fee_bps,slippage_bps=slip_bps,stop_atr=stop_atr,reward_risk=rr,max_positions=max_positions,strategy=strategy,fast=fast,slow=slow,breakout=breakout)
        all_dates=sorted(set().union(*(set(d.index) for d in raw.values())))
        if len(all_dates)<200:raise ValueError('Se recomiendan al menos 200 fechas disponibles para evaluar fuera de muestra.')
        cut=all_dates[int(len(all_dates)*split/100)]
        ins=backtest(raw,cfg,end=all_dates[int(len(all_dates)*split/100)-1])
        oos=backtest(raw,cfg,start=cut)
        full=backtest(raw,cfg)
        st.session_state['result']=dict(raw=raw,cfg=cfg,ins=ins,oos=oos,full=full,cut=cut,mode=mode,split=split)
    except Exception as exc:st.error(f'No se pudo ejecutar: {exc}')

if 'result' not in st.session_state:
    st.info('Configura los activos y pulsa «EJECUTAR BACKTEST». También puedes cargar OHLC en CSV, sin ninguna cuenta ni API de pago.')
    st.markdown('''**Incluye:** motor de cartera multi-activo, tres estrategias, entradas a la siguiente apertura, stops y objetivos intradiarios, gaps, comisiones, deslizamiento, dimensionamiento por riesgo, comparación con buy & hold, validación fuera de muestra, reportes descargables y registro íntegro de operaciones.''')
    st.warning('El producto está orientado a investigación y validación, no contiene conexiones a bróker ni promesas de rentabilidad. Yahoo Finance puede limitar el acceso o restringir usos comerciales de sus datos.')
    st.stop()

r=st.session_state.result
if r['mode']=='DEMOSTRACIÓN SINTÉTICA':st.error('DATOS SINTÉTICOS — RESULTADOS FICTICIOS, SIN VALIDEZ FINANCIERA')
st.success(f"Backtest completado · {len(r['raw'])} activos · periodo fuera de muestra desde {r['cut'].date()} · reglas deterministas")
tabs=st.tabs(['Resumen y equity','Validación fuera de muestra','Operaciones y auditoría','Gráficos y señales','Robustez y stress','Datos y exportaciones','Metodología'])

def metric_row(result):
    m=result['metrics']
    cols=st.columns(6)
    for col,(name,key,suffix) in zip(cols,[('Rentabilidad','total_return_pct','%'),('CAGR','cagr_pct','%'),('Drawdown máx.','max_drawdown_pct','%'),('Sharpe','sharpe',''),('Operaciones','trades',''),('Acierto','win_rate_pct','%')]):
        val=m[key];col.metric(name, f"{val:,.2f}{suffix}" if np.isfinite(val) else 'N/D')

def plot_equity(result,title):
    e=result['equity'];b=benchmark(r['raw'],e.index,r['cfg'].initial_cash)
    fig=go.Figure()
    fig.add_trace(go.Scatter(x=e.index,y=e.equity,name='Estrategia',line=dict(width=2,color='#22c55e')))
    fig.add_trace(go.Scatter(x=b.index,y=b,name='Benchmark buy & hold (sin costes)',line=dict(color='#64748b',dash='dash')))
    fig.update_layout(title=title,template='plotly_dark',height=400,margin=dict(l=15,r=15,t=45,b=15),legend=dict(orientation='h'))
    st.plotly_chart(fig,use_container_width=True)

with tabs[0]:
    st.subheader('Cartera consolidada — periodo completo')
    metric_row(r['full'])
    plot_equity(r['full'],'Evolución del capital y referencia equiponderada')
    eq=r['full']['equity'].equity
    dd=(eq/eq.cummax()-1)*100
    fig=go.Figure(go.Scatter(x=dd.index,y=dd,fill='tozeroy',name='Drawdown',line=dict(color='#ef4444')))
    fig.update_layout(template='plotly_dark',height=220,margin=dict(l=15,r=15,t=10,b=10),yaxis_title='%')
    st.plotly_chart(fig,use_container_width=True)
with tabs[1]:
    st.subheader('Holdout cronológico: no evaluar solo en el pasado optimizado')
    st.caption('70/30 por defecto. Los indicadores de test pueden usar historia anterior, pero el capital se reinicia en el corte. La estrategia no se optimiza automáticamente sobre test.')
    c1,c2=st.columns(2)
    with c1:
        st.markdown('**Periodo inicial / desarrollo**')
        metric_row_short=r['ins']['metrics']
        st.metric('Retorno IS',f"{metric_row_short['total_return_pct']:.2f}%")
        st.metric('Operaciones IS',metric_row_short['trades'])
    with c2:
        st.markdown('**Fuera de muestra / test**')
        metric_row_short=r['oos']['metrics']
        st.metric('Retorno OOS',f"{metric_row_short['total_return_pct']:.2f}%")
        st.metric('Operaciones OOS',metric_row_short['trades'])
    st.divider()
    metric_row(r['oos'])
    plot_equity(r['oos'],'Resultado estrictamente fuera de muestra')
    if r['oos']['metrics']['trades']<30:st.warning('Pocas operaciones OOS (<30). No hay evidencia estadística suficiente para inferir una ventaja robusta.')
    if r['oos']['metrics']['total_return_pct']<=0:st.error('El periodo fuera de muestra no fue rentable. No se ha validado ventaja para comercialización.')
    else:st.info('Un resultado positivo fuera de muestra es necesario, pero insuficiente para demostrar rentabilidad futura. Falta seguimiento prospectivo.')
with tabs[2]:
    st.subheader('Libro de operaciones auditables')
    trades=r['full']['trades']
    if len(trades):
        st.dataframe(trades.sort_values('exit',ascending=False),use_container_width=True,hide_index=True)
        counts=trades.groupby(['symbol','reason']).size().unstack(fill_value=0)
        st.dataframe(counts,use_container_width=True)
    else:st.warning('Sin operaciones: revisa rango, estrategias y reglas.')
    st.subheader('Eventos de órdenes')
    st.dataframe(r['full']['events'],use_container_width=True,hide_index=True)
    st.caption('Las señales se calculan al cierre de la sesión y las órdenes se cursan en la siguiente apertura disponible. No se realiza negociación real.')
with tabs[3]:
    sym=st.selectbox('Activo',list(r['raw']))
    d=r['full']['prepared'][sym]
    fig=go.Figure()
    fig.add_trace(go.Candlestick(x=d.index,open=d.Open,high=d.High,low=d.Low,close=d.Close,name=sym))
    fig.add_trace(go.Scatter(x=d.index,y=d.ema_fast,name='EMA rápida',line=dict(width=1)))
    fig.add_trace(go.Scatter(x=d.index,y=d.ema_slow,name='EMA lenta',line=dict(width=1)))
    ev=r['full']['events']
    if len(ev):
        es=ev[(ev.symbol==sym)&(ev.event=='BUY')];xs=ev[(ev.symbol==sym)&(ev.event=='SELL')]
        fig.add_trace(go.Scatter(x=es.date,y=es.price,mode='markers',name='Entradas',marker=dict(symbol='triangle-up',size=11,color='#22c55e')))
        fig.add_trace(go.Scatter(x=xs.date,y=xs.price,mode='markers',name='Salidas',marker=dict(symbol='triangle-down',size=11,color='#ef4444')))
    fig.update_layout(template='plotly_dark',height=550,xaxis_rangeslider_visible=False)
    st.plotly_chart(fig,use_container_width=True)
    st.subheader('Último cierre disponible y estado de señal')
    last=d.iloc[-1]
    st.write({'Fecha':str(d.index[-1].date()),'Último cierre':float(last.Close),'RSI':round(float(last.rsi),2) if pd.notna(last.rsi) else None,'ATR':round(float(last.atr),4) if pd.notna(last.atr) else None,'Señal entrada (al cierre)':bool(last.entry_signal),'Señal salida (al cierre)':bool(last.exit_signal)})
    st.caption('Una señal en la última vela no constituye una orden ni garantiza ejecución al día siguiente.')
with tabs[4]:
    st.subheader('Stress test de costes y sensibilidad')
    st.caption('Repetición de la misma estrategia OOS, variando comisiones y slippage. No constituye optimización ni validación independiente adicional.')
    rows=[]
    for multiple in [1,2,3,5]:
        c=r['cfg']
        from dataclasses import replace
        alt=replace(c,fee_bps=c.fee_bps*multiple,slippage_bps=c.slippage_bps*multiple)
        a=backtest(r['raw'],alt,start=r['cut'])['metrics']
        rows.append(dict(multiplicador_costes=multiple,retorno_oos_pct=round(a['total_return_pct'],2),drawdown_pct=round(a['max_drawdown_pct'],2),operaciones=a['trades']))
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    st.subheader('Ventanas cronológicas independientes (parámetros fijos)')
    dates=r['full']['equity'].index
    arr=[]
    bounds=np.array_split(np.array(dates),4)
    for i,b in enumerate(bounds):
        if len(b)<2:continue
        z=backtest(r['raw'],r['cfg'],start=pd.Timestamp(b[0]),end=pd.Timestamp(b[-1]))['metrics']
        arr.append(dict(ventana=i+1,inicio=str(pd.Timestamp(b[0]).date()),fin=str(pd.Timestamp(b[-1]).date()),retorno_pct=round(z['total_return_pct'],2),trades=z['trades'],drawdown_pct=round(z['max_drawdown_pct'],2)))
    st.dataframe(pd.DataFrame(arr),hide_index=True,use_container_width=True)
with tabs[5]:
    st.subheader('Calidad y procedencia')
    ds=[]
    for sym,d in r['raw'].items():
        ds.append(dict(symbol=sym,velas=len(d),desde=str(d.index.min().date()),hasta=str(d.index.max().date()),duplicadas=d.index.duplicated().sum(),nulos=int(d[['Open','High','Low','Close']].isna().sum().sum())))
    st.dataframe(pd.DataFrame(ds),use_container_width=True,hide_index=True)
    st.write('**Fuente:**',r['mode'])
    st.caption('Los datos públicos pueden ser retrasados, corregidos o tener limitaciones de licencia. En producción se necesita proveedor comercial autorizado y políticas de integridad, corporate actions, calendarios y survivorship bias.')
    c1,c2,c3=st.columns(3)
    c1.download_button('Operaciones CSV',r['full']['trades'].to_csv(index=False).encode(),'trades.csv','text/csv',use_container_width=True)
    c2.download_button('Equity CSV',r['full']['equity'].to_csv().encode(),'equity.csv','text/csv',use_container_width=True)
    report={'mode':r['mode'],'split_pct':r['split'],'cut':str(r['cut'].date()),'parameters':vars(r['cfg']),'symbols':list(r['raw']),'full':r['full']['metrics'],'in_sample':r['ins']['metrics'],'out_of_sample':r['oos']['metrics']}
    c3.download_button('Informe JSON',json.dumps(report,indent=2,default=str).encode(),'report.json','application/json',use_container_width=True)
    st.download_button('Eventos CSV',r['full']['events'].to_csv(index=False).encode(),'events.csv','text/csv')
with tabs[6]:
    st.markdown('''### Reglas y garantías de metodología
**Datos:** OHLC diario ajustado por splits/dividendos según fuente, con controles de integridad. La ejecución sobre datos ajustados es una aproximación que exige validación posterior con precios negociables originales.

**Señales:** indicadores calculados sin desplazar datos futuros; las señales nacen al cierre y se ejecutan en la siguiente apertura disponible. No es una simulación de ejecución intradía de alta frecuencia.

**Riesgo:** sólo posiciones largas y sin apalancamiento, cartera con capital compartido, tamaño condicionado a stop ATR, exposición máxima por activo y límite de posiciones. Stops/take-profit y gaps se evalúan usando OHLC; si se tocan ambos en una vela, gana el stop. Los stops no garantizan un precio ejecutable real.

**Costes:** comisiones en entradas/salidas y slippage aplicado al precio. No incluye fiscalidad, swap/financiación ni impacto de mercado variable, ni horquillas históricas reales.

**Validación:** holdout cronológico IS/OOS y stress de costes. Faltan tests prospectivos de meses, walk-forward con reoptimización estrictamente dentro de la muestra, intervalos de confianza y verificación en varios proveedores antes de afirmar eficacia o comercializar recomendaciones.

**Importante:** el backtest es una simulación, no evidencia de beneficios futuros. La selección retrospectiva de estrategias puede sobreajustar los datos. Ninguna métrica representa rentabilidad garantizada.

**Ámbito legal:** antes de ofrecer señales individualizadas o asesoramiento, estudiar normativa española/europea (CNMV/MiFID II), privacidad, protección de consumidores y licencias de datos. No reutilizar capturas/datos de terceros sin permiso comercial.''')
