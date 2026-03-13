#!/usr/bin/env bash
cd "$(dirname "$0")"

if [ ! -f .venv/Scripts/python.exe ] && [ ! -f .venv/bin/python ]; then
    echo "[首次运行] 正在创建虚拟环境并安装依赖..."
    python -m venv .venv
    if [ -f .venv/Scripts/pip ]; then
        .venv/Scripts/pip install -r requirements.txt
    else
        .venv/bin/pip install -r requirements.txt
    fi
fi

if [ -f .venv/Scripts/activate ]; then
    source .venv/Scripts/activate
elif [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
fi

echo ""
echo "启动网关 http://127.0.0.1:5000"
echo "按 Ctrl+C 停止"
echo ""
exec python app.py
