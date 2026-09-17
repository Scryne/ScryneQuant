# ScryneQuant - evren kosusu tablosunun gunluk yenileme denemesi. (Faz 14)
#
# Her gun calisir; ay icinde tablo gunceldir ve hicbir sey yapmaz (idempotent). Ay donunce
# M-1 verisi tamamsa (arsivin son gun dosyasi ertesi gun yayimlanir) tabloyu yeni aya uzatir;
# degilse arsivden indirir, hala eksikse cikis 3 verir ve ertesi gun yeniden dener. Kosu
# dosyanin degistigini kendisi gorur (`evren_tablosu_yenilendi` olayi).

param([string]$KosuAdi = "evren-kiyas,evren-funding-basis")

$ErrorActionPreference = "Stop"
$Kok = Split-Path -Parent $PSScriptRoot
Set-Location $Kok
$env:PYTHONIOENCODING = "utf-8"

$Python = Join-Path $Kok ".venv\Scripts\python.exe"
$Dizin = Join-Path $Kok "runs\paper"
$Cikis = 0
foreach ($Kosu in ($KosuAdi -split ",")) {
    $Tablo = Join-Path $Dizin ($Kosu + ".evren.parquet")
    if (-not (Test-Path $Tablo)) { continue }
    $Gunluk = Join-Path $Dizin ($Kosu + ".yenileme.log")
    & $Python -m scryne_quant.cli.main paper evren-tablo-yenile $Tablo --indir *>> $Gunluk
    if ($LASTEXITCODE -gt $Cikis) { $Cikis = $LASTEXITCODE }
}
exit $Cikis
