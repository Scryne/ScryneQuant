# ScryneQuant - gunluk saglik ozeti bildirimi (09:00 TR). (Faz 14)
#
# Bu bildirim gelmediyse host, gorev zamanlayici ya da ag ayakta degil demektir: alarm sistemi
# kendi olumunu haber veremez, sessizligin kendisi sinyal.

param([string]$Evren = "evren-kiyas,evren-funding-basis,evren-makro-nfci")

$ErrorActionPreference = "Stop"
$Kok = Split-Path -Parent $PSScriptRoot
Set-Location $Kok
$env:PYTHONIOENCODING = "utf-8"
$Python = Join-Path $Kok ".venv\Scripts\python.exe"
New-Item -ItemType Directory -Force (Join-Path $Kok "runs\izleme") | Out-Null
$Gunluk = Join-Path $Kok "runs\izleme\ozet.log"
$Arg = @()
foreach ($e in ($Evren -split ",")) { $Arg += @("--evren", $e) }
& $Python -m scryne_quant.cli.main izle ozet @Arg --bildir *>> $Gunluk
exit $LASTEXITCODE
