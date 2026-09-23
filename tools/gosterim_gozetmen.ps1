# Gösterim dönemi gözetmeni (K-122): 14 günlük testnet + shadow koşularını Claude oturumundan
# bağımsız ayakta tutar. Windows zamanlanmış görevi (`ScryneQuant-Gosterim`) bunu oturum açılışında
# ve her 10 dakikada bir çağırır.
#
# Davranış:
#   - `runs/gosterim/DURDUR` varsa hiçbir şey başlatmaz (bilinçli duruş).
#   - Her koşu için: `--kosu <ad>` ile çalışan bir sq süreci yoksa ve koşu kalıcı kapatılmamışsa
#     başlatır. Çalışıyorsa dokunmaz. Durdurma bayrağı (`kosu.dur`) yürütücünün kendi işidir.
#   - Her başlatma `runs/gosterim/gozetmen.log`a yazılır. Yürütücü yeniden başlatmayı kendisi sayar
#     (`yurutucu.json` sayac.yeniden_baslatma / plansiz_kesinti) — gözetmen sayı uydurmaz.
#
# Gözetmen yalnızca **başlatır**; hiçbir koşuyu öldürmez, SAFE_MODE kaldırmaz, mod yükseltmez.

$ErrorActionPreference = "Stop"
$Kok = Split-Path -Parent $PSScriptRoot
$Sq = Join-Path $Kok ".venv\Scripts\sq.exe"
$Gosterim = Join-Path $Kok "runs\gosterim"
New-Item -ItemType Directory -Force -Path $Gosterim | Out-Null
$Log = Join-Path $Gosterim "gozetmen.log"

function Yaz([string]$m) {
    $z = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm:ss")
    Add-Content -Path $Log -Value "$z UTC  $m" -Encoding utf8
}

if (Test-Path (Join-Path $Gosterim "DURDUR")) { exit 0 }

$Kosular = @(
    @{ Ad = "gosterim-testnet"; Arg = "execution calistir --mod testnet --kosu gosterim-testnet --strateji sma_kesisim --timeframe 1h --sermaye 100 --bekleme 20" },
    @{ Ad = "gosterim-shadow";  Arg = "execution calistir --mod shadow --kosu gosterim-shadow --strateji sma_kesisim --timeframe 1h --sermaye 100 --bekleme 20" }
    # K-134: `urun-testnet` cikarildi — gosterim-testnet ile ayni testnet hesabini paylasiyordu;
    # 49,58 USDT'lik alimi gosterim-testnet'in mutabakatini "aciklanamayan fark"la durdurdu.
    # Bir testnet hesabinda tek kosu.
)

$Calisan = Get-CimInstance Win32_Process -Filter "name='python.exe' or name='sq.exe'" |
    ForEach-Object { $_.CommandLine } | Where-Object { $_ }

foreach ($k in $Kosular) {
    $ad = $k.Ad
    if ($Calisan | Where-Object { $_ -match "--kosu $ad( |$)" }) { continue }
    $dizin = Join-Path $Kok "runs\execution\$ad"
    if (Test-Path (Join-Path $dizin "kapatildi.json")) { continue }
    New-Item -ItemType Directory -Force -Path $dizin | Out-Null
    $env:PYTHONIOENCODING = "utf-8"
    Start-Process -FilePath $Sq -ArgumentList $k.Arg -WorkingDirectory $Kok -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $dizin "cikti.log") `
        -RedirectStandardError (Join-Path $dizin "hata.log") | Out-Null
    Yaz "başlatıldı: $ad"
}

# K-134: aktif çok varlıklı DEMO bot hesapları (config/aktif.json). Her hesap kendi dizininde,
# kendi simüle/demo hesabında; `sq aktif durdur` `kapali` bırakır ve gözetmen onu başlatmaz.
$Aktif = @("kripto-trend", "kripto-kirilim", "kripto-donus")
foreach ($ad in $Aktif) {
    if ($Calisan | Where-Object { $_ -match "aktif calistir --hesap $ad( |$)" }) { continue }
    $dizin = Join-Path $Kok "runs\aktif\$ad"
    if (Test-Path (Join-Path $dizin "kapali")) { continue }
    New-Item -ItemType Directory -Force -Path $dizin | Out-Null
    $env:PYTHONIOENCODING = "utf-8"
    Start-Process -FilePath $Sq -ArgumentList "aktif calistir --hesap $ad" -WorkingDirectory $Kok `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $dizin "cikti.log") `
        -RedirectStandardError (Join-Path $dizin "hata.log") | Out-Null
    Yaz "başlatıldı: aktif/$ad"
}
