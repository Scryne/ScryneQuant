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
    [string]$FbKosuAdi = "evren-funding-basis",
    [string]$NfciKosuAdi = "evren-makro-nfci",
    [string]$ArastirmaTablosu = "data\evren\_evren\27b7a16ed0ed"
)

$ErrorActionPreference = "Stop"
$Kok = Split-Path -Parent $PSScriptRoot
Set-Location $Kok

$Dizin = Join-Path $Kok "runs\paper"
New-Item -ItemType Directory -Force $Dizin | Out-Null
foreach ($Kosu in @($KosuAdi, $FbKosuAdi, $NfciKosuAdi)) {
    $Hedef = Join-Path $Dizin ($Kosu + ".evren")
    if (-not (Test-Path ($Hedef + ".parquet"))) {
        Copy-Item ($ArastirmaTablosu + ".parquet") ($Hedef + ".parquet")
        Copy-Item ($ArastirmaTablosu + ".json") ($Hedef + ".json")
        Write-Output ("tablo kopyalandi: " + $Hedef + ".parquet")
    }
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

# Faz 12 #46'nin secilen noktasi (runsaz12	urev_funding_basis.json detay/secim/secilen).
$Fb = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $Kok `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $Kok "tools\evren-kosu.ps1") + '" -KosuAdi ' + $FbKosuAdi + ' -Strateji evren_funding_basis -Turev -Parametre yeniden_dengele_bar=168,azami_enstruman=10,hedef_brut=0.2,dislama_orani=0.2,pencere=720')
Register-ScheduledTask -TaskName "ScryneQuant-EvrenFB" -Action $Fb -Principal $Principal `
    -Settings $Ayar -Trigger (New-ScheduledTaskTrigger -AtStartup) -Force | Out-Null

# Faz 12 #48'in secilen noktasi (runsaz12\makro_nfci.json detay/secim/secilen).
# FRED_API_KEY hostun .env dosyasinda olmali (2026-09-17 Scryne onayi).
$Nfci = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $Kok `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $Kok "tools\evren-kosu.ps1") + '" -KosuAdi ' + $NfciKosuAdi + ' -Strateji evren_makro_nfci -Makro nfci -Parametre pencere_gun=365,esik=0.7,azami_enstruman=10,yeniden_dengele_bar=168,hedef_brut=0.2')
Register-ScheduledTask -TaskName "ScryneQuant-EvrenNFCI" -Action $Nfci -Principal $Principal `
    -Settings $Ayar -Trigger (New-ScheduledTaskTrigger -AtStartup) -Force | Out-Null

$AyarTablo = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$Yenile = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $Kok `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $Kok "tools\evren-tablo-yenile.ps1") + '"')
$Saat = [DateTime]::SpecifyKind([DateTime]::UtcNow.Date.AddHours(3).AddMinutes(15), "Utc").ToLocalTime()
Register-ScheduledTask -TaskName "ScryneQuant-EvrenTablo" -Action $Yenile -Principal $Principal `
    -Settings $AyarTablo -Trigger (New-ScheduledTaskTrigger -Daily -At $Saat) -Force | Out-Null

$Sapma = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $Kok `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $Kok "tools\evren-sapma.ps1") + '"')
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
