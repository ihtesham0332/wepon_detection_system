@echo off
title Push Sentry Vision App to GitHub
echo ====================================================
echo   SENTRY VISION - GITHUB REPOSITORY DEPLOYMENT
echo ====================================================
echo.

:: Check if git is installed
where git >nul 2>nul
if %errorlevel% neq 0 (
    echo ERROR: git is not installed or not in your system PATH.
    echo Please install Git and try again.
    pause
    exit /b
)

:: Initialize git repository if not already done
if not exist .git (
    echo [1/5] Initializing Git repository...
    git init
) else (
    echo [1/5] Git repository already initialized.
)

:: Add remote origin (remove existing one if it exists to avoid conflicts)
echo [2/5] Configuring Git remote origin...
git remote remove origin >nul 2>nul
git remote add origin https://github.com/ihtesham0332/wepon_detection_system.git

:: Add all files
echo [3/5] Adding project files to staging...
git add .

:: Commit
echo [4/5] Creating first commit...
git commit -m "Initial commit - Sentry Vision Threat Detection System"

:: Rename branch to main
git branch -M main

:: Push
echo [5/5] Pushing repository to GitHub (main branch)...
echo.
echo NOTE: If this is your first push, a browser window or login prompt
echo       may open requesting your GitHub credentials.
echo.
git push -u origin main

if %errorlevel% equ 0 (
    echo.
    echo ====================================================
    echo   SUCCESS: Code pushed to GitHub successfully!
    echo ====================================================
) else (
    echo.
    echo ====================================================
    echo   ERROR: Failed to push code to GitHub.
    echo   Please verify your internet connection and GitHub login.
    echo ====================================================
)
pause
