#!/usr/bin/env bash
cd "$(dirname "$0")"

# 云服务器常见只有 python3，没有 python
PYTHON=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
else
    echo "未找到 python3 或 python。请安装: apt install python3 python3-venv python3-pip"
    exit 1
fi

RUN_PYTHON=""
if [ -f .venv/Scripts/python.exe ]; then
    RUN_PYTHON=.venv/Scripts/python.exe
elif [ -f .venv/bin/python ]; then
    RUN_PYTHON=.venv/bin/python
fi

if [ -z "$RUN_PYTHON" ]; then
    echo "[首次运行] 正在创建虚拟环境..."
    $PYTHON -m venv .venv 2>&1
    if [ -f .venv/Scripts/python.exe ]; then
        RUN_PYTHON=.venv/Scripts/python.exe
    elif [ -f .venv/bin/python ]; then
        RUN_PYTHON=.venv/bin/python
    fi
    if [ -z "$RUN_PYTHON" ]; then
        echo "虚拟环境创建失败。请先安装: apt install python3-venv  然后重试。"
        exit 1
    fi
    echo "正在安装依赖..."
    $RUN_PYTHON -m pip install -q -r requirements.txt
fi

echo ""
echo "本机访问: http://127.0.0.1:5000"
PUB=$(curl -s --max-time 2 ifconfig.me 2>/dev/null || true)
if [ -n "$PUB" ]; then echo "公网访问: http://${PUB}:5000  （需路由器端口转发 5000）"; else echo "公网访问: 用你的公网IP:5000 并做路由器端口转发"; fi
echo "按 Ctrl+C 停止"
echo ""
exec "$RUN_PYTHON" app.py
