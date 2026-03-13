@echo off
cd /d "%~dp0"
title 渡の网关

if not exist ".venv\Scripts\python.exe" (
    echo [首次运行] 正在创建虚拟环境并安装依赖...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

echo.
echo 启动网关 http://127.0.0.1:5000
echo 按 Ctrl+C 停止
echo.
python app.py
pause
