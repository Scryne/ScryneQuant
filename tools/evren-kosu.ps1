# ScryneQuant - cok enstrumanli evren gozlem kosusu baslaticisi. (Faz 14)
#
# Zamanlanmis gorev cagirir; mantik `sq paper evren-baslat` icinde ve testli. Ayni ad
# ikinci kez baslatilinca depodaki girdilerden butun adimlar yeniden uretilir (K-038) ve
# kapali kalinan saatler REST'ten tamamlanir.
#
# Evren tablosu kosunun KENDI kopyasidir (runs\paper\<kosu>.evren.parquet): aylik yenileme
# (tools\evren-tablo-yenile.ps1) bu dosyayi uzatir, arastirma tablosuna dokunmaz.
#
# ASCII-only: pwsh 7 ve Windows PowerShell 5.1 ayni okusun (bkz. paper-kosu.ps1).
#
# Duzgun durdurmak (K-043):  sq paper durdur <kosu> --sebep "..."  -- kesinti sayilmaz.

param(
    [string]$KosuAdi  = "evren-kiyas",
    [string]$Strateji = "evren_esit_agirlik",
    [string[]]$Parametre = @("yeniden_dengele_bar=168", "azami_enstruman=10",
                             "azami_agirlik=0.02", "hedef_brut=0.2"),
    [switch]$Turev,
    [string]$Makro = ""
)

$ErrorActionPreference = "Stop"
$Kok = Split-Path -Parent $PSScriptRoot
Set-Location $Kok
$env:PYTHONIOENCODING = "utf-8"

$Python = Join-Path $Kok ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw ("sanal ortam bulunamadi: " + $Python) }

$Dizin = Join-Path $Kok "runs\paper"
New-Item -ItemType Directory -Force $Dizin | Out-Null
$Tablo = Join-Path $Dizin ($KosuAdi + ".evren.parquet")
if (-not (Test-Path $Tablo)) { throw ("evren tablosu yok: " + $Tablo) }
$Gunluk = Join-Path $Dizin ($KosuAdi + ".log")

$PArg = @()
foreach ($p in (($Parametre -join ",") -split ",")) { $PArg += @("-p", $p) }
if ($Turev) { $PArg += @("--turev") }
if ($Makro) { foreach ($m in ($Makro -split ",")) { $PArg += @("--makro", $m) } }

& $Python -m scryne_quant.cli.main paper evren-baslat $KosuAdi `
    --evren-tablo $Tablo --strateji $Strateji @PArg *>> $Gunluk

# Cikis kodu gorev zamanlayicisina gecsin (cokmede yeniden baslatma icin).
exit $LASTEXITCODE
