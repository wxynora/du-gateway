# 随机模仿者文字塔防

纯 Python、纯文字的随机模仿者塔防原型，入口是一个单函数：

```python
from du_imitator_pvz import cmd

print(cmd("new_game level=1 seed=demo"))
print(cmd("cards 模仿者 模仿者 模仿者 模仿者 向日葵 窝瓜"))
print(cmd("种 模仿者 3-4; 种 向日葵 2-3"))
print(cmd("等待"))
```

也可以直接命令行运行：

```bash
python3 -m du_imitator_pvz help
python3 -m du_imitator_pvz new_game level=1 seed=demo
python3 -m du_imitator_pvz '种 模仿者 3-4; 种 向日葵 2-3'
```

## 单游戏接入

这个目录可以作为类似 `games/<name>/` 的单游戏模块使用：

- `manifest.json`：游戏元数据。
- `engine.py`：暴露 `cmd(text) -> str`。
- `game/`：核心规则、结算、观察、随机池。
- `data/`：植物、僵尸、开奖池数据。

不需要大厅层；外部框架只要 import `du_imitator_pvz.engine.cmd` 或复制本目录并调用 `engine.cmd(text)`。

## 命令

```text
help
status
look
new_game level=1 seed=demo
cards 模仿者 模仿者 模仿者 模仿者 向日葵 窝瓜
种 模仿者 3-4; 种 向日葵 2-3
铲 3-4
等待
结束本局
note 第一局自己的复盘
```

## 存档

默认存档为当前目录下的 `du_imitator_pvz_save.json`。可以用环境变量改位置：

```bash
DU_IMITATOR_PVZ_SAVE=/tmp/pvz_save.json python3 -m du_imitator_pvz look
```

存档是 JSON，包含棋盘状态、事件日志、玩家复盘、回合历史和随机流快照。
