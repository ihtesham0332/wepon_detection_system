@echo off
title Sentry Vision App Server - YOLOv12
echo ====================================================
echo   SENTRY VISION - REAL-TIME DETECTOR STARTUP
echo ====================================================
echo.
echo Check python version...
python --version
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in your system PATH.
    echo Please install Python 3.8 or higher.
    pause
    exit /b
)
echo.
echo Starting Flask App Server...
echo Open your browser to: http://localhost:5001
echo.
python app.py
if %errorlevel% neq 0 (
    echo.
    echo App crashed or closed with error code %errorlevel%.
    pause
)
