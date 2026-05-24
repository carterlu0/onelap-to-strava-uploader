@echo off
chcp 65001 >nul
echo ========================================
echo   Magene-link 文件夹监听器
echo ========================================
echo.
echo 正在启动文件夹监听...
echo 手机操作: 顽鹿 APP -> 分享 -> QQ"我的电脑"
echo 自动检测新 FIT 文件并上传 Strava
echo.
echo 请勿关闭此窗口
echo.
call .venv\Scripts\python.exe file_watcher.py
pause
