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
echo "本机访问: http://127.0.0.1:5000"
PUB=$(curl -s --max-time 2 ifconfig.me 2>/dev/null || true)
if [ -n "$PUB" ]; then echo "公网访问: http://${PUB}:5000  （需路由器端口转发 5000）"; else echo "公网访问: 用你的公网IP:5000 并做路由器端口转发"; fi
echo "按 Ctrl+C 停止"
echo ""
exec python app.py
