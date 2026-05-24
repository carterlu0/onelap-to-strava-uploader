@echo off
chcp 65001 >nul
echo ========================================
echo   Magene-link Telegram Bot
echo ========================================
echo.
echo 正在启动 Telegram Bot...
echo 请勿关闭此窗口
echo.
echo 手机端: 顽鹿运动 APP -> 分享 FIT -> Telegram -> 你的 Bot
echo.
call .venv\Scripts\python.exe telegram_bot.py
pause
