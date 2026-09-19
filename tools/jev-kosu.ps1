# ScryneQuant - Jev golge kosusu baslaticisi. (K-074)
#
# Zamanlanmis gorev cagirir; mantik `sq jev golge` icinde ve testli. Ayri surec: paper/live
# motoruna dokunmaz, emir gondermez, olurse onlar etkilenmez. Ayni ad ikinci kez baslatilinca
# defter kaldigi yerden devam eder (append-only, zincir hash).
#
# TYPESAFE_API_KEY hostun kullanici ortam degiskeninde olmali (kodda, .env'de, logda degil).
# ASCII-only: pwsh 7 ve Windows PowerShell 5.1 ayni okusun (bkz. paper-kosu.ps1).
#
# Duzgun durdurmak: sq jev durdur --kosu <kosu> --sebep "..."

param([string]$KosuAdi = "golge-1")

$ErrorActionPreference = "Stop"
$Kok = Split-Path -Parent $PSScriptRoot
Set-Location $Kok
$env:PYTHONIOENCODING = "utf-8"

$Python = Join-Path $Kok ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw ("sanal ortam bulunamadi: " + $Python) }
if (-not $env:TYPESAFE_API_KEY) { throw "TYPESAFE_API_KEY ortam degiskeni yok; golge baslatilmadi (fail-closed)" }

$Dizin = Join-Path $Kok "runs\jev"
New-Item -ItemType Directory -Force $Dizin | Out-Null
$Gunluk = Join-Path $Dizin ($KosuAdi + ".log")

# `cli.jev` dogrudan cagrilir (`cli.main` degil): Jev alt komutu `main.py`ye kayitli olmayan
# bir hostta da calissin; ayni Typer uygulamasi, ayni komut.
& $Python -m scryne_quant.cli.jev golge --kosu $KosuAdi *>> $Gunluk
exit $LASTEXITCODE
