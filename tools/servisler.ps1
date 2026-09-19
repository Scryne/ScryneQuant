# ScryneQuant - butun servisleri tek komutla yonet: kur | baslat | durdur | durum. (Faz 14, K-074)
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\servisler.ps1 kur      # gorevleri (yeniden) yazar
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\servisler.ps1 baslat   # acilis gorevlerini baslatir
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\servisler.ps1 durum    # tek tablo: gorev, surec, son bar
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\servisler.ps1 durdur   # kosulari DUZGUN durdurur (K-043)
#
# Ne yapar: mevcut gorev betiklerini (evren-gorev-kur.ps1 = evren kosulari + izleme + yedek;
# paper, pano) tek noktadan cagirir ve Jev golge gorevini ekler. Yeni bir mekanizma yok:
# her sey zaten var olan zamanlanmis gorevler. Hicbir gorev gercek emir gondermez.
#
# `durdur` sert kill DEGILDIR: kosulara durdurma bayragi birakir (kesinti sayilmaz) ve
# gorevleri Disable eder ki yeniden baslatmasin. `baslat` gorevleri Enable edip Start eder.
# Pano ve izleme bayrak tanimaz; onlar Stop-ScheduledTask ile durur (salt okunur, kayip yok).
#
# ASCII-only: pwsh 7 ve Windows PowerShell 5.1 ayni okusun (bkz. paper-kosu.ps1).

param(
    [Parameter(Position = 0)][ValidateSet("kur", "baslat", "durdur", "durum")][string]$Islem = "durum",
    [string]$JevKosu = "golge-1",
    [string]$PaperKosu = "host-1",
    [string]$Evren = "evren-kiyas,evren-funding-basis,evren-makro-nfci",
    [int]$PanoPort = 8788
)

$ErrorActionPreference = "Stop"
$Kok = Split-Path -Parent $PSScriptRoot
Set-Location $Kok
$env:PYTHONIOENCODING = "utf-8"
$Python = Join-Path $Kok ".venv\Scripts\python.exe"

# Gorev adi -> (tur, kosu adi/dosya). Kosu dosyasi olanlar bayrakla durdurulur.
$Gorevler = [ordered]@{
    "ScryneQuant-Paper"     = @{ tur = "paper"; kosu = $PaperKosu }
    "ScryneQuant-Evren"     = @{ tur = "evren"; kosu = ($Evren -split ",")[0] }
    "ScryneQuant-EvrenFB"   = @{ tur = "evren"; kosu = ($Evren -split ",")[1] }
    "ScryneQuant-EvrenNFCI" = @{ tur = "evren"; kosu = ($Evren -split ",")[2] }
    "ScryneQuant-Jev"       = @{ tur = "jev";   kosu = $JevKosu }
    "ScryneQuant-Pano"      = @{ tur = "pano";  kosu = "" }
    "ScryneQuant-Izleme"    = @{ tur = "izleme"; kosu = "" }
    "ScryneQuant-Yedek"     = @{ tur = "gunluk"; kosu = "" }
    "ScryneQuant-EvrenTablo"= @{ tur = "gunluk"; kosu = "" }
    "ScryneQuant-EvrenSapma"= @{ tur = "gunluk"; kosu = "" }
    "ScryneQuant-Ozet"      = @{ tur = "gunluk"; kosu = "" }
}

function Gorev-Var([string]$Ad) { return $null -ne (Get-ScheduledTask -TaskName $Ad -ErrorAction SilentlyContinue) }

function Pid-Yasiyor([string]$Yol) {
    if (-not (Test-Path $Yol)) { return $null }
    try {
        $p = (Get-Content $Yol -Raw | ConvertFrom-Json).pid
        return $null -ne (Get-Process -Id $p -ErrorAction SilentlyContinue)
    } catch { return $null }
}

function Kur {
    # Evren kosulari + izleme (+ pano/paper zaten kuruluysa dokunmaz) - mevcut betik.
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Kok "tools\evren-gorev-kur.ps1")

    $Kullanici = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $Principal = New-ScheduledTaskPrincipal -UserId $Kullanici -LogonType S4U -RunLevel Limited
    $Ayar = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -MultipleInstances IgnoreNew `
        -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

    # Jev golge (K-074): ayri gorev, ayri surec, ayri defter.
    $Jev = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $Kok `
        -Argument ('-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $Kok "tools\jev-kosu.ps1") + '" -KosuAdi ' + $JevKosu)
    Register-ScheduledTask -TaskName "ScryneQuant-Jev" -Action $Jev -Principal $Principal `
        -Settings $Ayar -Trigger (New-ScheduledTaskTrigger -AtStartup) -Force | Out-Null
    Write-Output "ScryneQuant-Jev kuruldu (kosu: $JevKosu)"

    # Pano (salt okunur): kurulu degilse kur.
    if (-not (Gorev-Var "ScryneQuant-Pano")) {
        $Web = Join-Path $Kok "apps\web\dist"
        $Pano = New-ScheduledTaskAction -Execute $Python -WorkingDirectory $Kok `
            -Argument ('"' + (Join-Path $Kok "tools\pano.py") + '" --port ' + $PanoPort + ' --web "' + $Web + '"')
        Register-ScheduledTask -TaskName "ScryneQuant-Pano" -Action $Pano -Principal $Principal `
            -Settings $Ayar -Trigger (New-ScheduledTaskTrigger -AtStartup) -Force | Out-Null
        Write-Output "ScryneQuant-Pano kuruldu (port $PanoPort)"
    }
    if (-not (Test-Path (Join-Path $Kok "apps\web\dist\pano.html"))) {
        Write-Output "UYARI: apps\web\dist yok - pano yalnizca /api verir. Ana makinede `npm run build` yapip dist'i kopyala."
    }
}

function Baslat {
    foreach ($Ad in $Gorevler.Keys) {
        if (-not (Gorev-Var $Ad)) { continue }
        Enable-ScheduledTask -TaskName $Ad | Out-Null
        $g = $Gorevler[$Ad]
        if ($g.tur -in @("paper", "evren", "jev", "pano")) {
            Start-ScheduledTask -TaskName $Ad
            Write-Output ("baslatildi: " + $Ad)
        }
    }
}

function Durdur {
    foreach ($Ad in $Gorevler.Keys) {
        if (-not (Gorev-Var $Ad)) { continue }
        $g = $Gorevler[$Ad]
        Disable-ScheduledTask -TaskName $Ad | Out-Null   # yeniden baslatmasin
        switch ($g.tur) {
            "paper" { & $Python -m scryne_quant.cli.main paper durdur $g.kosu --sebep "servisler.ps1 durdur" }
            "evren" { & $Python -m scryne_quant.cli.main paper durdur $g.kosu --sebep "servisler.ps1 durdur" }
            "jev"   { & $Python -m scryne_quant.cli.main jev durdur --kosu $g.kosu --sebep "servisler.ps1 durdur" }
            default { Stop-ScheduledTask -TaskName $Ad -ErrorAction SilentlyContinue }
        }
        Write-Output ("durduruluyor: " + $Ad)
    }
    Write-Output "Kosular bayrakla duzgun kapaniyor (<=30 s). Gercek emir yoktu; iptal edilecek emir yok."
}

function Durum {
    $Satirlar = @()
    foreach ($Ad in $Gorevler.Keys) {
        $g = $Gorevler[$Ad]
        $t = Get-ScheduledTask -TaskName $Ad -ErrorAction SilentlyContinue
        $Bilgi = if ($t) { Get-ScheduledTaskInfo -TaskName $Ad } else { $null }
        $Yasiyor = $null
        $Son = ""
        if ($g.kosu) {
            $Dizin = if ($g.tur -eq "jev") { "runs\jev" } else { "runs\paper" }
            $Yasiyor = Pid-Yasiyor (Join-Path $Kok ($Dizin + "\" + $g.kosu + ".sqlite.pid"))
            $DurumJson = Join-Path $Kok ($Dizin + "\" + $g.kosu + ".sqlite.durum.json")
            if (Test-Path $DurumJson) {
                try {
                    $d = Get-Content $DurumJson -Raw | ConvertFrom-Json
                    if ($d.son_bar_utc) { $Son = $d.son_bar_utc }
                    elseif ($d.son_bar_ms) { $Son = [DateTimeOffset]::FromUnixTimeMilliseconds($d.son_bar_ms).UtcDateTime.ToString("yyyy-MM-dd HH:mm") + " UTC" }
                } catch {}
            }
        }
        $Satirlar += [pscustomobject]@{
            Gorev  = $Ad
            Tur    = $g.tur
            Kosu   = $g.kosu
            Gorev_Durumu = if ($t) { [string]$t.State } else { "KURULU DEGIL" }
            Surec  = if ($null -eq $Yasiyor) { "-" } elseif ($Yasiyor) { "yasiyor" } else { "OLMUS" }
            Son_Bar = $Son
            Son_Calisma = if ($Bilgi) { $Bilgi.LastRunTime } else { "" }
        }
    }
    $Satirlar | Format-Table -AutoSize
    Write-Output ("pano: http://127.0.0.1:" + $PanoPort + "  (salt okunur; SSH tuneli: -L " + $PanoPort + ":127.0.0.1:" + $PanoPort + ")")
    Write-Output "gercek emir: YOK (butun kosular gozlem/golge)"
}

switch ($Islem) {
    "kur"    { Kur }
    "baslat" { Baslat }
    "durdur" { Durdur }
    "durum"  { Durum }
}
