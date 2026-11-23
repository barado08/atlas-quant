# ATLAS QUANT — Research Terminal

Plataforma de investigación cuantitativa multi-mercado, swing trading con backtesting de cartera e interpretación **visual** de capturas mediante un modelo local de Ollama. Destinada a **validación antes de comercialización**; no conecta con brokers ni asegura rentabilidad.

## Código y entorno
Este repositorio contiene el código fuente de ATLAS QUANT v0.3, configuración **GitHub Codespaces** y CI **GitHub Actions**.

### Ejecutar en la nube
1. En el repositorio, selecciona **Code → Codespaces → Create codespace on main**.
2. Codespaces instala las dependencias Python indicadas en `requirements.txt`.
3. Abre una terminal y ejecuta:
   ```bash
   python -m pytest -q
   python scripts/online_smoke.py
   streamlit run app.py --server.address 0.0.0.0 --server.port 8501
   ```
4. Abre el puerto 8501 desde **Ports** y mantenlo privado.

### Funciones
- Descarga de históricos diarios de criptomonedas, acciones/ETF y Forex mediante yfinance, o CSV OHLC.
- Motor con tres estrategias swing, señales al cierre, órdenes a la apertura siguiente, stops/targets/gaps, costes y cartera con capital compartido.
- Separación temporal desarrollo/test, métricas, gráficos, stress de costes, benchmark y exportación de operaciones.
- Módulo **IA visual: analizar capturas** con Ollama `qwen2.5vl:3b`, JSON auditable, SHA-256, límites de lectura numérica y contraste de ticker.
- Pruebas automáticas locales y CI online con *smoke test* de BTC-USD, SPY y EURUSD=X. La prueba online falla si no recibe datos reales; no sustituye por datos ficticios.

### Limitaciones importantes
- La IA **no está instalada automáticamente en Codespaces**: Ollama y el modelo multimodal requieren recursos de RAM/CPU/GPU adicionales. Las pruebas actuales solo simulan su respuesta HTTP; no confirman precisión de lectura de capturas reales.
- Github Actions no prueba toda la interfaz gráficamente, ni demuestra rentabilidad, ni reemplaza un seguimiento prospectivo.
- Yahoo Finance puede bloquear peticiones y sus datos **no deben asumirse licenciados para redistribución comercial**.
- El corte cronológico no constituye walk-forward con optimización anidada. Hay sesgos y riesgos adicionales que auditar antes de vender.
- Los entornos Codespaces/Actions tienen cuotas; revisa el consumo en GitHub antes de ejecutarlos de manera intensiva.

## Ejecución local
Instala Python 3.12, `python -m pip install -r requirements.txt` y `streamlit run app.py`.
Para interpretación de imágenes, instala Ollama y ejecuta `ollama pull qwen2.5vl:3b`.

## Objetivo de validación
Reunir backtests fuera de muestra de múltiples activos, periodos y regímenes, comprobar sensibilidad a costes, controlar sesgos, fijar criterios de aceptación antes de analizar resultados y completar paper trading prospectivo documentado. Ninguna operación real hasta que el sistema haya pasado la validación correspondiente.
