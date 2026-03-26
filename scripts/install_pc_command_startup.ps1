param(
  [string]$TaskName = "DuPcCommandAgent"
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runner = Join-Path $repoRoot "scripts\run_pc_command_agent.bat"

if (-not (Test-Path $runner)) {
  throw "未找到启动脚本: $runner"
}

# 说明：使用当前用户开机登录时触发，不需要管理员权限
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$runner`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

try {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
} catch {}

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "Du PC command agent autostart"
Write-Host "已创建开机自启任务: $TaskName"
Write-Host "可手动启动测试: Start-ScheduledTask -TaskName $TaskName"
