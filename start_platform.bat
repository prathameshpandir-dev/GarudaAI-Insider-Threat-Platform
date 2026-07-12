@echo off
title SentinelAI Platform Launcher
echo ===================================================
echo             SENTINELAI SECURITY PLATFORM
echo ===================================================
echo.
echo [1/3] Starting Python Flask API Backend...
start "SentinelAI Backend Server" cmd /k "title SentinelAI Backend && python backend/app.py"

echo [2/3] Starting Vite React Frontend Client...
start "SentinelAI Frontend Client" cmd /k "title SentinelAI Frontend && cd frontend && npm.cmd run dev"

echo [3/3] Launching your browser dashboard in 5 seconds...
timeout /t 5 > nul
start http://localhost:5173

echo.
echo SentinelAI successfully launched!
echo Keep the backend and frontend terminal windows open.
echo Press any key to close this launcher menu.
pause > nul
