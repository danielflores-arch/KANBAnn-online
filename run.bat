@echo off
title Kanban Digital Local - SAI Planta
cd /d "%~dp0app_local"
echo ========================================================
echo     INICIANDO KANBAN DIGITAL LOCAL (SAI PLANTA)
echo ========================================================
echo Abriendo aplicacion en http://localhost:8000 ...
echo.

start "" http://localhost:8000
python server.py
pause
