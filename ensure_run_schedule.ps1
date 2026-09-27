# 确保“定时运行”计划任务存在（被 start_local_stack.ps1 调用，也可单独执行）
# 策略: A股交易日(周一~周五)收盘后 AUTORUN_HHMM(默认 15:35) 自动跑一轮分析,
# 由 run_crew_scheduled.vbs -> run_crew_then_release.py 执行, 跑完自动 ollama stop 卸载模型。
$ErrorActionPreference = 'Continue'
$Repo = "D:\aishare\repo\stock-crewai-master"
$TaskName = "stock-crewai-daily-run"
$LogDir = Join-Path $Repo "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir ("schedule-{0:yyyyMMdd-HHmmss}.log" -f (Get-Date))
function Log($m) {
    Add-Content -Path $Log -Value ("{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m) -Encoding UTF8
}
$hhmm = if ([string]::IsNullOrEmpty($env:AUTORUN_HHMM)) { "15:35" } else { $env:AUTORUN_HHMM }
$vbs = Join-Path $Repo "run_crew_scheduled.vbs"
Log ("task=" + $TaskName + " weekly Mon-Fri at " + $hhmm + " via " + $vbs)
$existing = schtasks /query /tn $TaskName 2>$null
if ($LASTEXITCODE -eq 0) { Log 'task exists, refreshing definition' } else { Log 'task missing, creating' }
$tr = "wscript.exe " + $vbs
$out = schtasks /create /tn $TaskName /tr $tr /sc weekly /d MON,TUE,WED,THU,FRI /st $hhmm /rl LIMITED /it /f 2>&1
Log ("schtasks: " + ($out -join " "))
if ($LASTEXITCODE -ne 0) { Log 'FATAL: register task failed'; exit 1 }
# 错过触发时间(睡眠/关机)后开机补跑
$t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($t) {
    $t.Settings.StartWhenAvailable = $true
    $t.Settings.ExecutionTimeLimit = "PT2H"
    Set-ScheduledTask -TaskName $TaskName -Settings $t.Settings | Out-Null
    Log "settings: StartWhenAvailable=true, ExecutionTimeLimit=2h"
}
Log "done"

