@echo off
title Procesar Ultimo Archivo Descargado
cd /d "%~dp0"
echo ======================================================
echo    PROCESANDO ULTIMO ARCHIVO DESCARGADO DE TOTVS
echo ======================================================
echo.
python run_pipeline.py --no-download
echo.
pause
