# Регистрирует задачу планировщика Windows: запуск монитора каждый час.
# Запуск: powershell -ExecutionPolicy Bypass -File scripts\register-task.ps1
# Удалить: Unregister-ScheduledTask -TaskName "hh-vacancy-monitor" -Confirm:$false

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

$action = New-ScheduledTaskAction -Execute $python -Argument "-m hhmon run" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Hours 1)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 20)

Register-ScheduledTask -TaskName "hh-vacancy-monitor" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Host "Задача hh-vacancy-monitor создана: каждый час, рабочая папка $root"
