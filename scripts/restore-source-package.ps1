$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$transferDir = Join-Path $repoRoot '.source-package'
$expectedSha256 = 'bdbeda15e54539a0fa56e3686a7c91c6f507e95fb5d9929afe709d5540b4a308'
$builder = [System.Text.StringBuilder]::new()

for ($i = 0; $i -le 18; $i++) {
    $part = $i.ToString('000')
    $repairs = @(Get-ChildItem -LiteralPath (Join-Path $transferDir 'repair') -Filter "part-$part-*.b64" -ErrorAction SilentlyContinue | Sort-Object Name)
    if ($repairs.Count -gt 0) {
        foreach ($file in $repairs) {
            [void]$builder.Append((Get-Content -LiteralPath $file.FullName -Raw).Trim())
        }
    } else {
        $file = Join-Path $transferDir "part-$part.b64"
        if (-not (Test-Path -LiteralPath $file)) { throw "Missing archive segment: $file" }
        [void]$builder.Append((Get-Content -LiteralPath $file -Raw).Trim())
    }
}
$zipPath = Join-Path $repoRoot 'SALOON-DREEM-1.1.0-source.zip'
[IO.File]::WriteAllBytes($zipPath, [Convert]::FromBase64String($builder.ToString()))
$actualSha256 = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualSha256 -ne $expectedSha256) {
    Remove-Item -LiteralPath $zipPath -Force
    throw "Archive SHA-256 mismatch. Expected $expectedSha256; actual $actualSha256. Do not extract this package."
}
Write-Host "Verified source package: $zipPath" -ForegroundColor Green
