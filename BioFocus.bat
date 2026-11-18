@echo off
rem BioFocus: abre la app en el navegador (doble clic). Se cierra cerrando esta ventana.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Falta el entorno .venv: ver README.md, seccion Instalacion.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m streamlit run producto\app.py --server.headless false
