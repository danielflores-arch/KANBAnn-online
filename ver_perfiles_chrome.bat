@echo off
title Ver Perfiles de Chrome
cd /d "%~dp0"

echo ==========================================================
echo   LISTA DE PERFILES DE CHROME EN ESTA COMPUTADORA
echo ==========================================================
echo.
python totvs_downloader.py --list-profiles
echo.
echo ==========================================================
echo   Copia el nombre de la carpeta (ej. 'Default', 'Profile 1')
echo   que corresponda a tu usuario de empresa.
echo ==========================================================
pause
