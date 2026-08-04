@echo off
chcp 65001 >nul
title AISleepGen
cd /d D:\AISleepGen_Optimized

echo Finding process on port 8090...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8090" ^| findstr "LISTENING"') do (
    echo     Killing PID %%a...
    taskkill /f /pid %%a 2>nul
    timeout /t 2 /nobreak >nul
)

echo Cleaning cache...
if exist __pycache__ rmdir /s /q __pycache__ 2>nul
if exist data\__pycache__ rmdir /s /q data\__pycache__ 2>nul

echo Starting server...
python -B -X utf8 asyncio_server.py 8090

if errorlevel 1 (
    echo Server exited with code %errorlevel%
    pause
)
