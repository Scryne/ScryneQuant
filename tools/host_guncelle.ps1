# K-138: host'ta kod güncellemesi. Ana makinede:
#   git bundle create sq.bundle master; (apps/web) tar --force-local -czf dist.tgz dist
#   scp sq.bundle dist.tgz scryn@192.168.1.4:Documents/Projeler/ScryneQuant/
#   ssh ... "powershell -NoProfile -ExecutionPolicy Bypass -File %USERPROFILE%\Documents\Projeler\ScryneQuant\tools\host_guncelle.ps1"
#
# Yaptığı: bundle'dan hızlı ileri alma (yalnız ff), bağımlılık senkronu, pano derlemesini açma,
# panoyu yeniden başlatma (yeni API kodu yüklensin), gözetmeni tetikleme. Botları durdurmaz:
# çalışan botlar yeni kodu bir sonraki yeniden başlatmada alır (`-BotlariYenile` ile hemen).
param([switch]$BotlariYenile)

$ErrorActionPreference = "Continue"
# Betik tools/ içinden ya da (ilk kez, bundle'dan önce) proje kökünden çalışabilir.
$Kok = if (Test-Path (Join-Path $PSScriptRoot "config/aktif.json")) { $PSScriptRoot } else { Split-Path -Parent $PSScriptRoot }
Set-Location $Kok

"== kod"
git fetch -q sq.bundle master
git merge --ff-only -q FETCH_HEAD
git log --oneline -1

"== ortam"
& "$env:USERPROFILE\.local\bin\uv.exe" sync --frozen --extra mt5 --group dev 2>&1 | Select-Object -Last 1

if (Test-Path dist.tgz) {
    "== pano derlemesi"
    Push-Location (Join-Path $Kok "apps\web")
    tar -xzf ..\..\dist.tgz
    Pop-Location
    Remove-Item dist.tgz
}

$surec = Get-CimInstance Win32_Process -Filter "name='sq.exe'"
"== pano yeniden"
$surec | Where-Object { $_.CommandLine -match "execution pano" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

if ($BotlariYenile) {
    "== botlar yeniden (planlı durdurma)"
    $hesaplar = (Get-Content (Join-Path $Kok "config\aktif.json") -Raw | ConvertFrom-Json).hesaplar.PSObject.Properties.Name
    foreach ($h in $hesaplar) {
        $d = Join-Path $Kok "runs\aktif\$h"
        if (Test-Path $d) { New-Item -ItemType File -Force (Join-Path $d "dur") | Out-Null }
    }
    $t = 0
    while ((Get-CimInstance Win32_Process -Filter "name='sq.exe'" | Where-Object { $_.CommandLine -match "aktif calistir" }) -and $t -lt 90) { Start-Sleep 1; $t++ }
    "  durdu ($t sn)"
    foreach ($h in $hesaplar) { Remove-Item (Join-Path $Kok "runs\aktif\$h\dur") -ErrorAction SilentlyContinue }
}

Start-ScheduledTask -TaskName ScryneQuant-Aktif
Start-Sleep 30
"== süreçler"
Get-CimInstance Win32_Process -Filter "name='sq.exe'" | ForEach-Object { ($_.CommandLine -replace '^.*sq\.exe.?\s*', '') }
