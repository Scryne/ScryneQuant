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

# K-138: host'ta pano ev ağına açılır (`-PanoHost 0.0.0.0`; güvenlik duvarı yalnız LocalSubnet).
param([string]$PanoHost = "127.0.0.1")

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

# K-134: eski BTC gösterim koşuları (gosterim-testnet, gosterim-shadow, urun-testnet) Scryne'ın
# isteğiyle kaldırıldı ("yeniler olsun sadece"); gerçek para pilotu yok. Liste bilerek boş.
# (urun-testnet ayrıca gosterim-testnet ile aynı testnet hesabını paylaşıyordu.)
$Kosular = @()

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
$Aktif = @("kripto-trend", "kripto-kirilim", "kripto-donus", "mt5-demo", "mt5-gece", "mt5-aydonumu", "kripto-carry", "vadeli-bollinger-3x", "vadeli-donchian-2x")
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

# K-134: takip ekranı (http://127.0.0.1:8790, salt okunur). Çalışmıyorsa başlatılır.
if (-not ($Calisan | Where-Object { $_ -match "execution pano" })) {
    $env:PYTHONIOENCODING = "utf-8"
    Start-Process -FilePath $Sq -ArgumentList "execution pano --host $PanoHost" -WorkingDirectory $Kok -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $Kok "runs\pano-8790.log") `
        -RedirectStandardError (Join-Path $Kok "runs\pano-8790.err") | Out-Null
    Yaz "başlatıldı: pano 8790"
}
