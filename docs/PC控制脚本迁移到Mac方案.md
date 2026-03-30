# PC 控制脚本迁移到 macOS 方案（仅文档，不改代码）

## 1. 现状结论

当前电脑控制脚本在 `scripts/pc_command_agent.py`，是 **Windows 定制实现**，不能在 macOS 直接原样运行。

主要原因：

- 依赖 Windows API：`ctypes.windll.user32.LockWorkStation`
- 依赖 Windows 命令：`shutdown /s /t`、`shutdown /r /t`、`rundll32.exe`
- 依赖 Windows 程序：`notepad.exe`、`cmd /c start`
- 音量控制依赖 Windows 组件：`pycaw`、`comtypes`
- 静音兜底依赖 PowerShell COM：`WScript.Shell SendKeys`

说明：网关侧的 PCMD 解析与入队（`services/pc_command_handler.py`）基本可复用，主要是 **agent 执行层** 需要做 macOS 适配。

---

## 2. 现有指令在 macOS 的适配建议

| 指令 | Windows 现状 | macOS 建议实现 |
| --- | --- | --- |
| `lock` | `ctypes.windll.user32.LockWorkStation()` | `osascript -e 'tell application "System Events" to keystroke "q" using {control down, command down}'` |
| `shutdown[:sec]` | `shutdown /s /t <sec>` | `sudo shutdown -h +<min>`（秒需转分钟） |
| `restart[:sec]` | `shutdown /r /t <sec>` | `sudo shutdown -r +<min>`（秒需转分钟） |
| `sleep` | `rundll32 ... SetSuspendState` | `pmset sleepnow` |
| `mute` | `pycaw` 或媒体键兜底 | `osascript -e 'set volume with output muted'` |
| `volume:<0-100>` | `pycaw SetMasterVolumeLevelScalar` | `osascript -e 'set volume output volume <n>'` |
| `notify:title:body` | `plyer.notification` | 继续用 `plyer`，或改 `osascript display notification` |
| `open:notepad[:text]` | 写临时文本后 `notepad.exe` 打开 | 写临时文本后 `open -a TextEdit <file>` |
| `open:<app>` | `cmd /c start` | `open -a "<AppName>"` |
| `url:https://...` | `webbrowser.open(url)` | 可保持不变（`webbrowser` 跨平台） |
| `media:play` | `pyautogui.press("playpause")` | 优先 AppleScript 发送媒体播放/暂停，`pyautogui` 作为兜底 |

---

## 3. 迁移策略（推荐分两步）

### 第一步：最小可用（优先）

目标：先让核心远控可用，不追求所有细节最优。

- 复用现有轮询/回执逻辑（`poll_once`、`/api/pc_command`、`/done`）
- 在执行层增加 macOS 分支（`sys.platform == "darwin"`）
- 先支持高频命令：`lock`、`sleep`、`mute`、`volume`、`url`、`notify`、`open`
- `shutdown/restart` 先保守处理：
  - 未授予 sudo 权限时返回失败并打印提示
  - 避免脚本卡在交互密码输入

### 第二步：体验增强（后续）

- 将 `open:<app>` 做“别名映射”：
  - `notepad` -> `TextEdit`
  - `wechat` -> `WeChat`
- `media:play` 优化为稳定的 AppleScript 方案
- 针对 macOS 增加更清晰日志，便于 Telegram 侧定位失败原因

---

## 4. 依赖与环境变量建议

当前 `scripts/requirements_pc_agent.txt` 含 Windows 专属依赖：

- `pycaw`
- `comtypes`

建议改造后拆分依赖：

- 通用依赖：`requests`、`python-dotenv`、`plyer`、`pyautogui`
- Windows 依赖：`pycaw`、`comtypes`
- macOS 依赖：优先系统命令 + AppleScript，尽量不引入新三方库

环境变量建议保持兼容：

- `GATEWAY_URL`
- `PC_COMMAND_TOKEN`
- `PC_POLL_SECONDS`

---

## 5. macOS 权限清单（迁移后必须做）

- 系统设置 -> 隐私与安全性 -> 辅助功能：允许运行脚本的终端/解释器
- 系统设置 -> 隐私与安全性 -> 自动化：允许控制 `System Events`
- 如用通知/截屏能力，按需开启通知与屏幕录制权限

---

## 6. 迁移后测试清单（手工）

按顺序执行以下 PCMD 并观察回执与本机行为：

1. `[PCMD:notify:渡:mac端接管成功]`
2. `[PCMD:url:https://www.apple.com]`
3. `[PCMD:volume:30]`
4. `[PCMD:mute]`
5. `[PCMD:open:notepad:这是迁移测试]`（期望打开 TextEdit 并带文本）
6. `[PCMD:sleep]`
7. `[PCMD:lock]`

可选高风险项（仅在本地确认后测试）：

- `[PCMD:shutdown:120]`
- `[PCMD:restart:120]`

---

## 7. 风险与注意事项

- `shutdown/restart` 在 macOS 通常需要 sudo 权限，不建议默认开启无保护执行。
- 不同语言系统下应用名可能不同，`open -a` 需做别名兜底。
- 如果未来要兼容 Windows 与 macOS，建议将 `execute_command` 拆成平台实现文件，统一由一个调度入口调用。

