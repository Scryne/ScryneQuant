# ScryneQuant - evren kosusu icin zamanlanmis gorevleri kurar. (Faz 14)
#
# Hostta, bir kez calistirilir (idempotent: varsa gorevi yeniden yazar):
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\evren-gorev-kur.ps1
#
# 1. ScryneQuant-Evren       : acilista, oturumsuz (S4U), cokerse 1 dk arayla yeniden baslar.
# 2. ScryneQuant-EvrenTablo  : her gun 03:15 UTC (06:15 TR) tablo yenileme denemesi.
# 3. ScryneQuant-EvrenSapma  : her gun 03:45 UTC (06:45 TR) canli-backtest sapma olcumu.
# 4. ScryneQuant-Izleme      : 15 dakikada bir alarm kontrolu (docs\Runbook.md).
#
# Kosu tablosu yoksa arastirma tablosundan kopyalanir (bir kez). Sonrasi yalnizca yenileme.

param(
    [string]$KosuAdi = "evren-kiyas",
    [string]$ArastirmaTablosu = "data\evren\_evren\27b7a16ed0ed"
)

$ErrorActionPreference = "Stop"
$Kok = Split-Path -Parent $PSScriptRoot
Set-Location $Kok

$Dizin = Join-Path $Kok "runs\paper"
New-Item -ItemType Directory -Force $Dizin | Out-Null
$Hedef = Join-Path $Dizin ($KosuAdi + ".evren")
if (-not (Test-Path ($Hedef + ".parquet"))) {
    Copy-Item ($ArastirmaTablosu + ".parquet") ($Hedef + ".parquet")
    Copy-Item ($ArastirmaTablosu + ".json") ($Hedef + ".json")
    Write-Output ("tablo kopyalandi: " + $Hedef + ".parquet")
}

$Kullanici = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Principal = New-ScheduledTaskPrincipal -UserId $Kullanici -LogonType S4U -RunLevel Limited
$Ayar = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -MultipleInstances IgnoreNew `
    -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

$Kosu = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $Kok `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $Kok "tools\evren-kosu.ps1") + '" -KosuAdi ' + $KosuAdi)
Register-ScheduledTask -TaskName "ScryneQuant-Evren" -Action $Kosu -Principal $Principal `
    -Settings $Ayar -Trigger (New-ScheduledTaskTrigger -AtStartup) -Force | Out-Null

$AyarTablo = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$Yenile = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $Kok `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $Kok "tools\evren-tablo-yenile.ps1") + '" -KosuAdi ' + $KosuAdi)
$Saat = [DateTime]::SpecifyKind([DateTime]::UtcNow.Date.AddHours(3).AddMinutes(15), "Utc").ToLocalTime()
Register-ScheduledTask -TaskName "ScryneQuant-EvrenTablo" -Action $Yenile -Principal $Principal `
    -Settings $AyarTablo -Trigger (New-ScheduledTaskTrigger -Daily -At $Saat) -Force | Out-Null

$Sapma = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $Kok `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $Kok "tools\evren-sapma.ps1") + '" -KosuAdi ' + $KosuAdi)
$SaatSapma = [DateTime]::SpecifyKind([DateTime]::UtcNow.Date.AddHours(3).AddMinutes(45), "Utc").ToLocalTime()
Register-ScheduledTask -TaskName "ScryneQuant-EvrenSapma" -Action $Sapma -Principal $Principal `
    -Settings $AyarTablo -Trigger (New-ScheduledTaskTrigger -Daily -At $SaatSapma) -Force | Out-Null

$Izleme = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $Kok `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $Kok "tools\izleme.ps1") + '"')
$AyarIzleme = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$Tetik = New-ScheduledTaskTrigger -Once -At (Get-Date).Date `
    -RepetitionInterval (New-TimeSpan -Minutes 15)
Register-ScheduledTask -TaskName "ScryneQuant-Izleme" -Action $Izleme -Principal $Principal `
    -Settings $AyarIzleme -Trigger $Tetik -Force | Out-Null

Get-ScheduledTask ScryneQuant-* | Select-Object TaskName, State
