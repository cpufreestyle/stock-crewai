# 虚拟盘自动交易 - 定时任务安装脚本
# 管理员权限运行

$TaskName = "StockCrewAI_VirtualTrading"
$ScriptPath = "D:\qclaw-workspace\stock-crewai\launch_virtual.bat"
$WorkDir = "D:\qclaw-workspace\stock-crewai"

# 检查是否已存在
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "任务已存在，先删除..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# 创建触发器：每个交易日（周一至周五）9:00启动
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "09:00"

# 创建动作
$action = New-ScheduledTaskAction -Execute $ScriptPath -WorkingDirectory $WorkDir

# 设置账户（SYSTEM账户，无需登录）
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

# 设置任务选项
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

# 注册任务
Register-ScheduledTask `
    -TaskName $TaskName `
    -Trigger $trigger `
    -Action $action `
    -Principal $principal `
    -Settings $settings `
    -Description "StockCrewAI 虚拟盘自动交易（交易时段内循环运行）"

Write-Host "✅ 定时任务创建成功！" -ForegroundColor Green
Write-Host "任务名称: $TaskName" -ForegroundColor Cyan
Write-Host "运行时间: 每个交易日 09:00" -ForegroundColor Cyan
Write-Host ""
Write-Host "手动控制命令:" -ForegroundColor Yellow
Write-Host "  启动: Start-ScheduledTask -TaskName $TaskName" -ForegroundColor Gray
Write-Host "  停止: Stop-ScheduledTask -TaskName $TaskName" -ForegroundColor Gray
Write-Host "  删除: Unregister-ScheduledTask -TaskName $TaskName" -ForegroundColor Gray
Write-Host "  查看: Get-ScheduledTask -TaskName $TaskName" -ForegroundColor Gray
