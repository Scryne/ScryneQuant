# ScryneQuant - evren kosularinin gunluk yedegi (05:30 TR). (Faz 14)
#
# Calisan kosuya dokunmadan tutarli kopya (SQLite online backup), runs\yedek altinda kosu
# basina son 7 yedek. Geri yukleme tatbikati: sq paper evren-tatbikat <kosu>

param([string]$KosuAdi = "evren-kiyas,evren-funding-basis,evren-makro-nfci")

$ErrorActionPreference = "Stop"
$Kok = Split-Path -Parent $PSScriptRoot
Set-Location $Kok
$env:PYTHONIOENCODING = "utf-8"
$Python = Join-Path $Kok ".venv\Scripts\python.exe"
New-Item -ItemType Directory -Force (Join-Path $Kok "runs\yedek") | Out-Null
$Gunluk = Join-Path $Kok "runs\yedek\yedek.log"
& $Python -m scryne_quant.cli.main paper evren-yedek @($KosuAdi -split ",") *>> $Gunluk
exit $LASTEXITCODE
