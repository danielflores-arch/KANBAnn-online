@echo off
title Descargador TOTVS (Segundo Plano)
cd /d "%~dp0"

echo ==========================================================
echo   DESCARGANDO TOTVS EN SEGUNDO PLANO (MODO HEADLESS)
echo ==========================================================
echo.
echo Ejecutando sin abrir ventana de Chrome...
echo Por favor espera unos momentos mientras se descarga el archivo...
echo.

python totvs_downloader.py --headless

echo.
echo ==========================================================
echo   Proceso finalizado. Revisa la carpeta D:\Daniel Flores\TOTVS
echo ==========================================================
pause
