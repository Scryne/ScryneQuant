# ScryneQuant - evren kosusunun gunluk canli-backtest sapma olcumu. (Faz 14, tasarim 6/2)
#
# Kosu dosyasina dokunmaz (SQLite yedegi uzerinde olcer). Her olcum bir JSON satiri olarak
# runs\paper\<kosu>.sapma.jsonl dosyasina eklenir.

param([string]$KosuAdi = "evren-kiyas")

$ErrorActionPreference = "Stop"
$Kok = Split-Path -Parent $PSScriptRoot
Set-Location $Kok
$env:PYTHONIOENCODING = "utf-8"

$Python = Join-Path $Kok ".venv\Scripts\python.exe"
$Dizin = Join-Path $Kok "runs\paper"
$Rapor = Join-Path $Dizin ($KosuAdi + ".sapma.jsonl")
$Gunluk = Join-Path $Dizin ($KosuAdi + ".sapma.log")

& $Python -m scryne_quant.cli.main paper evren-sapma $KosuAdi --rapor $Rapor *>> $Gunluk
exit $LASTEXITCODE
