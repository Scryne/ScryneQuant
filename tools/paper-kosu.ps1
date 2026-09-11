# ScryneQuant - paper/gozlem kosusu baslaticisi. (Faz 6)
#
# Bu betik bir zamanlanmis gorev tarafindan cagrilir ve tek is yapar: kosuyu dogru
# calisma dizininde, dogru yorumlayiciyla baslatmak. Mantik burada degil - mantigin
# tamami `sq paper baslat` icinde ve testli.
#
# Neden zamanlanmis gorev, neden basit bir arka plan sureci degil: Faz 6'nin kriteri
# 30 gun ve o surede yeniden baslatma (guncelleme, yeniden baslatma, elektrik)
# kacinilmaz. Oturum acildiginda kendiliginden geri gelen bir gorev kesintiyi
# sifirlamaz ama kisaltir - ve toparlanma yolu (K-038) kesintinin iz birakmadigini
# zaten kanitliyor.
#
# ASCII-only ve bilerek: bu dosya hem pwsh 7 hem Windows PowerShell 5.1 tarafindan
# okunabilmeli ve 5.1 BOM'suz UTF-8'i ANSI sanip Turkce karakterleri bozuyor. Betigin
# calismasi bir kodlama ayrintisina bagli olmamali.
#
# Gorevi kaldirmak:
#   Unregister-ScheduledTask -TaskName "ScryneQuant-Paper" -Confirm:$false

param(
    [string]$KosuAdi   = "gozlem-1",
    [string]$Strateji  = "ema_kesisim",
    [string]$Mod       = "gozlem",
    [int]   $Port      = 8787
)

$ErrorActionPreference = "Stop"
$Kok = Split-Path -Parent $PSScriptRoot
Set-Location $Kok

$Python = Join-Path $Kok ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw ("sanal ortam bulunamadi: " + $Python + " -- once 'uv sync' calistirin")
}

# Dashboard build'i varsa servis edilir; yoksa API yine calisir, yalnizca arayuz olmaz.
# Eksik bir build yuzunden kosuyu hic baslatmamak, olculen seyi arayuze baglamak olurdu.
$Web = Join-Path $Kok "apps\web\dist"
$WebArg = @()
if (Test-Path (Join-Path $Web "index.html")) { $WebArg = @("--web", $Web) }

$GunlukDizin = Join-Path $Kok "runs\paper"
New-Item -ItemType Directory -Force $GunlukDizin | Out-Null
$Gunluk = Join-Path $GunlukDizin ($KosuAdi + ".log")

# stdout/stderr dosyaya: kosu gunlugu (`sq paper olaylar`) olaylari tutuyor, bu dosya
# ise beklenmeyen bir yigin izinin dusecegi yer. Ikisi farkli sorulara cevap veriyor.
& $Python -m scryne_quant.cli.main paper baslat $KosuAdi `
    --strateji $Strateji --mod $Mod --port $Port @WebArg *>> $Gunluk
