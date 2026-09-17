# ScryneQuant - evren kosusu tablosunun gunluk yenileme denemesi. (Faz 14)
#
# Her gun calisir; ay icinde tablo gunceldir ve hicbir sey yapmaz (idempotent). Ay donunce
# M-1 verisi tamamsa (arsivin son gun dosyasi ertesi gun yayimlanir) tabloyu yeni aya uzatir;
# degilse arsivden indirir, hala eksikse cikis 3 verir ve ertesi gun yeniden dener. Kosu
# dosyanin degistigini kendisi gorur (`evren_tablosu_yenilendi` olayi).

param([string]$KosuAdi = "evren-kiyas")

$ErrorActionPreference = "Stop"
$Kok = Split-Path -Parent $PSScriptRoot
Set-Location $Kok
$env:PYTHONIOENCODING = "utf-8"

$Python = Join-Path $Kok ".venv\Scripts\python.exe"
$Dizin = Join-Path $Kok "runs\paper"
$Tablo = Join-Path $Dizin ($KosuAdi + ".evren.parquet")
$Gunluk = Join-Path $Dizin ($KosuAdi + ".yenileme.log")

& $Python -m scryne_quant.cli.main paper evren-tablo-yenile $Tablo --indir *>> $Gunluk
exit $LASTEXITCODE
