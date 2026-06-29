# 在桌面生成指向 start_components.bat 的快捷方式（.lnk）。
$ErrorActionPreference = 'Stop'

$root   = $PSScriptRoot
$target = Join-Path $root 'start_components.bat'
$name   = 'EstimBCI 患者端'

# 优先用项目里的 logo.ico；找不到再回退到 PsychoPy 自带图标。
$icon = Join-Path $root 'logo.ico'
if (-not (Test-Path $icon)) {
    $icon = Join-Path $root '.venv\Lib\site-packages\psychopy\app\Resources\builder.ico'
}

if (-not (Test-Path $target)) {
    Write-Error "找不到目标脚本: $target"
    exit 1
}

$desktop  = [Environment]::GetFolderPath('Desktop')
$lnkPath  = Join-Path $desktop "$name.lnk"

$ws  = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut($lnkPath)
$lnk.TargetPath       = $target
$lnk.WorkingDirectory = $root
$lnk.Description       = 'EstimBCI 启动 LSL-UART 桥接与患者端'
if (Test-Path $icon) { $lnk.IconLocation = $icon }
$lnk.Save()

Write-Host "已创建快捷方式: $lnkPath"

