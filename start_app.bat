@echo off
echo 正在启动服务...
echo 请勿关闭此窗口。
echo.
start "" "http://127.0.0.1:5000"
call .venv\Scripts\python.exe app.py
pause