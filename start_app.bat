@echo off
chcp 65001 >nul
echo ========================================
echo   Magene-link ^=^> Strava 同步工具 v2.0
echo ========================================
echo.
echo 正在启动 Web 服务...
echo 请勿关闭此窗口
echo 浏览器访问: http://127.0.0.1:5000
echo.
start "" "http://127.0.0.1:5000"
call .venv\Scripts\python.exe app.py
pause