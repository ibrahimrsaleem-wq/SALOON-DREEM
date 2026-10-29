[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Find-Python {
    $Candidates = @(
        @{ Command = 'py'; Args = @('-3.13') },
        @{ Command = 'py'; Args = @('-3.12') },
        @{ Command = 'python'; Args = @() }
    )
    foreach ($Candidate in $Candidates) {
        $Cmd = Get-Command $Candidate.Command -ErrorAction SilentlyContinue
        if ($null -ne $Cmd) {
            try {
                $ProbeArgs = @($Candidate.Args) + @('-c', 'import sys; print(sys.version_info.major, sys.version_info.minor)')
                & $Cmd.Source @ProbeArgs *> $null
                if ($LASTEXITCODE -eq 0) { return @{ Command = $Cmd.Source; Args = $Candidate.Args } }
            } catch { }
        }
    }
    throw 'لم يتم العثور على Python. ثبّت Python 3.12 أو 3.13 ثم أعد تشغيل السكربت.'
}

$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $VenvPython)) {
    $Python = Find-Python
    Write-Host 'إنشاء بيئة Python معزولة للمشروع...' -ForegroundColor Cyan
    $VenvArgs = @($Python.Args) + @('-m', 'venv', (Join-Path $Root '.venv'))
    & $Python.Command @VenvArgs
    if ($LASTEXITCODE -ne 0) { throw 'تعذر إنشاء البيئة الافتراضية.' }
}

Write-Host 'تثبيت/تحديث متطلبات SALOON DREEM...' -ForegroundColor Cyan
& $VenvPython -m pip install --disable-pip-version-check -r (Join-Path $Root 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'فشل تثبيت المتطلبات. راجع اتصال الإنترنت ورسالة pip.' }

$env:HOST = '127.0.0.1'
$env:PORT = [string]$Port
$env:APP_TIMEZONE = 'Asia/Gaza'
$env:DATA_DIR = Join-Path $Root 'data'
$env:DATABASE_PATH = Join-Path $env:DATA_DIR 'saloon_dreem.db'
New-Item -ItemType Directory -Path $env:DATA_DIR -Force | Out-Null

$Existing = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($Existing) {
    try {
        $Health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 3
        if ($Health.app -eq 'SALOON DREEM') {
            Write-Host "التطبيق يعمل بالفعل على http://127.0.0.1:$Port" -ForegroundColor Green
            if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$Port" }
            exit 0
        }
    } catch { }
    throw "المنفذ $Port مستخدم من برنامج آخر. شغّل السكربت مع -Port 8001 مثلًا."
}

Write-Host "تشغيل SALOON DREEM على http://127.0.0.1:$Port" -ForegroundColor Green
$Server = Start-Process -FilePath $VenvPython -ArgumentList @('-m', 'backend.app.server_entry') -WorkingDirectory $Root -PassThru
$Deadline = (Get-Date).AddSeconds(40)
$Ready = $false
while ((Get-Date) -lt $Deadline) {
    if ($Server.HasExited) { throw "توقف خادم التطبيق مبكرًا (exit $($Server.ExitCode))." }
    try {
        $Health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 2
        if ($Health.status -eq 'ok') { $Ready = $true; break }
    } catch { Start-Sleep -Milliseconds 500 }
}
if (-not $Ready) {
    try { Stop-Process -Id $Server.Id -Force -ErrorAction SilentlyContinue } catch { }
    throw 'لم يستجب الخادم خلال 40 ثانية. جرّب تشغيل python -m backend.app.server_entry يدويًا لمشاهدة الخطأ.'
}
Write-Host "تم التشغيل. رقم عملية الخادم: $($Server.Id)" -ForegroundColor Green
Write-Host 'لإيقافه: أغلق نافذة الخادم التي فتحها النظام من إدارة المهام، أو أعد تشغيل الجهاز.' -ForegroundColor DarkGray
if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$Port" }
