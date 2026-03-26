@echo off
setlocal
cd /d "%~dp0.."

rem 启动前清理旧实例，避免重复消费命令队列
%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$targets = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -ieq 'python.exe' -and $_.CommandLine -like '*pc_command_agent.py*' }; foreach ($p in $targets) { try { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue } catch {} }" >nul 2>nul

set "_PY_CMD="

%SystemRoot%\System32\where.exe python >nul 2>nul
if %errorlevel%==0 (
  set "_PY_CMD=python"
)

if not defined _PY_CMD (
  %SystemRoot%\System32\where.exe py >nul 2>nul
  if %errorlevel%==0 (
    set "_PY_CMD=py -3"
  )
)

if not defined _PY_CMD (
  if exist "%SystemRoot%\py.exe" (
    set "_PY_CMD=%SystemRoot%\py.exe -3"
  )
)

if not defined _PY_CMD (
  if exist "%LocalAppData%\Programs\Python\Launcher\py.exe" (
    set "_PY_CMD=%LocalAppData%\Programs\Python\Launcher\py.exe -3"
  )
)

if defined _PY_CMD (
  %_PY_CMD% "scripts\pc_command_agent.py"
  goto :eof
)

echo [ERROR] 未找到 python 或 py 启动器，请先安装 Python 并勾选 PATH。
exit /b 1
