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
echo 本机访问: http://127.0.0.1:5000
echo 公网访问: http://你的公网IP:5000  （需路由器端口转发 5000，且 .env 勿设 HOST=127.0.0.1）
echo 按 Ctrl+C 停止
echo.
python app.py
pause
