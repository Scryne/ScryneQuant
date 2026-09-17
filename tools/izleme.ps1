# ScryneQuant - izleme kontrolu (15 dakikada bir). (Faz 14)
#
# Etkin alarmlar runs\izleme\durum.json, degisimler runs\izleme\alarmlar.jsonl.
# Her kodun mudahalesi docs\Runbook.md. Cikis 2 = kritik alarm var (gorev gecmisinde gorunur).

param([string]$Evren = "evren-kiyas,evren-funding-basis,evren-makro-nfci", [string]$Tek = "host-1")

$ErrorActionPreference = "Stop"
$Kok = Split-Path -Parent $PSScriptRoot
Set-Location $Kok
$env:PYTHONIOENCODING = "utf-8"
$Python = Join-Path $Kok ".venv\Scripts\python.exe"
New-Item -ItemType Directory -Force (Join-Path $Kok "runs\izleme") | Out-Null
$Gunluk = Join-Path $Kok "runs\izleme\kontrol.log"
$Arg = @()
foreach ($e in ($Evren -split ",")) {
    if (Test-Path (Join-Path $Kok ("runs\paper\" + $e + ".sqlite"))) { $Arg += @("--evren", $e) }
}
foreach ($t in ($Tek -split ",")) { $Arg += @("--tek", $t) }
& $Python -m scryne_quant.cli.main izle kontrol @Arg *>> $Gunluk
exit $LASTEXITCODE
