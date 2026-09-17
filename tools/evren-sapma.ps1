# ScryneQuant - evren kosusunun gunluk canli-backtest sapma olcumu. (Faz 14, tasarim 6/2)
#
# Kosu dosyasina dokunmaz (SQLite yedegi uzerinde olcer). Her olcum bir JSON satiri olarak
# runs\paper\<kosu>.sapma.jsonl dosyasina eklenir.

param([string]$KosuAdi = "evren-kiyas,evren-funding-basis")

$ErrorActionPreference = "Stop"
$Kok = Split-Path -Parent $PSScriptRoot
Set-Location $Kok
$env:PYTHONIOENCODING = "utf-8"

$Python = Join-Path $Kok ".venv\Scripts\python.exe"
$Dizin = Join-Path $Kok "runs\paper"
$Cikis = 0
foreach ($Kosu in ($KosuAdi -split ",")) {
    if (-not (Test-Path (Join-Path $Dizin ($Kosu + ".sqlite")))) { continue }
    $Rapor = Join-Path $Dizin ($Kosu + ".sapma.jsonl")
    $Gunluk = Join-Path $Dizin ($Kosu + ".sapma.log")
    & $Python -m scryne_quant.cli.main paper evren-sapma $Kosu --rapor $Rapor *>> $Gunluk
    if ($LASTEXITCODE -gt $Cikis) { $Cikis = $LASTEXITCODE }
}
exit $Cikis
