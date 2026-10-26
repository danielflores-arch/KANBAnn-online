@echo off
title BUCLE TOTVS (Cada 10 Minutos)
cd /d "%~dp0"

echo ==========================================================
echo   BUCLE CONTINUO DE DESCARGA TOTVS CADA 10 MINUTOS
echo ==========================================================
echo.
echo Presiona Ctrl + C para detener el bucle en cualquier momento.
echo.

python totvs_downloader.py --headless --loop --interval 600

pause
