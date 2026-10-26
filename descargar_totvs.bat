@echo off
title Descargador TOTVS PCP - Kanban
cd /d "%~dp0"

echo ==========================================================
echo   DESCARGADOR DE LOTES Y OPERACIONES TOTVS (PCP MOD2)
echo ==========================================================
echo.
echo Iniciando Chrome en Modo Invitado (sin seleccion de perfiles)...
echo.

python totvs_downloader.py

echo.
echo ==========================================================
echo   Proceso finalizado.
echo ==========================================================
pause
