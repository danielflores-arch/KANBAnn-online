@echo off
title Actualizar Datos Kanban (TOTVS -> Local -> Vercel)
cd /d "%~dp0"
echo ======================================================
echo    ACTUALIZADOR DE DATOS KANBAN (TOTVS A LOCAL Y VERCEL)
echo ======================================================
echo.
python run_pipeline.py
echo.
pause
