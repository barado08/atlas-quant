# ATLAS QUANT — Research Terminal

Proyecto privado de investigación de estrategias swing multi-mercado. La finalidad es **validar**, con pruebas repetibles, señales y backtests antes de plantear comercialización. **La rentabilidad no está demostrada.**

## Estado de esta rama
El repositorio ha quedado inicializado. El código v0.3 completo está disponible en el paquete `ATLAS_QUANT_v0.3_Entorno_Online.zip` entregado en ChatGPT, pero **todavía no se ha transferido a este repositorio**. No presentar esta inicialización como un despliegue de la aplicación.

## Próxima acción
Descomprimir `ATLAS_QUANT_v0.3_Entorno_Online.zip` y subir **su contenido** a este repositorio (incluidas `.github/` y `.devcontainer/`, manteniendo rutas). Se puede utilizar Git local:

```bash
git clone https://github.com/barado08/atlas-quant.git
cd atlas-quant
# Copiar aquí los archivos extraídos del ZIP (sin carpetas .venv, __pycache__ ni .pytest_cache).
git add .
git commit -m "Import ATLAS QUANT v0.3 application and online validation"
git push origin main
```

Después, revisar Actions. Abrir Code > Codespaces > Create codespace on main; en la terminal ejecutar `python -m pytest -q`, `python scripts/online_smoke.py` y `streamlit run app.py --server.address 0.0.0.0 --server.port 8501`.

El módulo IA visual usa Ollama local y no puede considerarse validado en Codespaces sin aprovisionar un modelo compatible. Las pruebas automáticas locales se ejecutaron en noviembre de 2026 (13/13); **no** se han validado cotizaciones online.
