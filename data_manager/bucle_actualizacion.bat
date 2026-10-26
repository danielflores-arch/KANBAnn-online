@echo off
title Bucle de Actualizacion Continua (Cada 10 Minutos)
cd /d "%~dp0"
echo ======================================================
echo    BUCLE DE ACTUALIZACION CONTINUA (CADA 10 MINUTOS)
echo ======================================================
echo.
echo Presiona Ctrl+C para detener el proceso en cualquier momento.
echo.
python run_pipeline.py --loop --interval 600
pause
