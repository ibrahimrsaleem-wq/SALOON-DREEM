$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Exe = Get-ChildItem -LiteralPath $Root -Filter 'SALOON-DREEM-Portable-*.exe' -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -ne $Exe) {
    $Target = $Exe.FullName
    $WorkingDirectory = $Exe.DirectoryName
} else {
    $Target = Join-Path $Root 'RUN-SALOON-DREEM.bat'
    $WorkingDirectory = $Root
}
if (-not (Test-Path -LiteralPath $Target)) { throw "لم يتم العثور على ملف تشغيل SALOON DREEM: $Target" }
$Desktop = [Environment]::GetFolderPath('Desktop')
$ShortcutPath = Join-Path $Desktop 'SALOON DREEM.lnk'
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $Target
$Shortcut.WorkingDirectory = $WorkingDirectory
$Shortcut.IconLocation = "$Target,0"
$Shortcut.Description = 'تشغيل نظام إدارة صالون الحلاقة SALOON DREEM'
$Shortcut.Save()
Write-Host "تم إنشاء الاختصار: $ShortcutPath" -ForegroundColor Green
