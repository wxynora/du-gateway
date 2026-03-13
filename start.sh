#!/usr/bin/env bash
cd "$(dirname "$0")"

# 云服务器常见只有 python3，没有 python
PYTHON=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
else
    echo "未找到 python3 或 python，请先安装 Python。"
    exit 1
fi

if [ ! -f .venv/Scripts/python.exe ] && [ ! -f .venv/bin/python ]; then
    echo "[首次运行] 正在创建虚拟环境并安装依赖..."
    $PYTHON -m venv .venv
    if [ -f .venv/Scripts/pip ]; then
        .venv/Scripts/pip install -r requirements.txt
    elif [ -f .venv/bin/pip ]; then
        .venv/bin/pip install -r requirements.txt
    else
        .venv/bin/python -m pip install -r requirements.txt
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
