#requires -Version 7.0
<#
    Proje durumu bağlam enjektörü. proje-baslat skill'i ile kurulan her proje
    klasöründe çalışır. docs/ altındaki dosyaları ve .claude/state.json'u okuyup
    "şu an neredeyiz" bağlamını Claude'a enjekte eder. Bu dosya kendi başına
    çalışır, ScryneOS vault'undaki lib.ps1'e bağımlı değildir -- proje klasörü
    vault'un dışında, bağımsız bir yerde yaşar.
#>

Set-StrictMode -Version Latest
try { [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false) } catch { }

$projectDir = if (-not [string]::IsNullOrWhiteSpace($env:CLAUDE_PROJECT_DIR)) {
    $env:CLAUDE_PROJECT_DIR
}
else {
    (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
}

$statePath = Join-Path $projectDir '.claude\state.json'
$docsDir = Join-Path $projectDir 'docs'

function Write-HookContext {
    param([Parameter(Mandatory)][string]$Text)
    if ([string]::IsNullOrEmpty($Text)) { return }
    @{
        hookSpecificOutput = @{
            hookEventName     = 'SessionStart'
            additionalContext = $Text
        }
    } | ConvertTo-Json -Compress -Depth 5
}

if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
    Write-HookContext -Text "[Proje Sistemi] Bu klasörde .claude/state.json yok. Proje henüz proje-baslat skill'i ile başlatılmamış olabilir, ya da state dosyası silinmiş. Devam etmeden önce durumu kullanıcıya sor, gerekiyorsa proje-baslat skill'ini çalıştır."
    exit 0
}

try {
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
}
catch {
    Write-HookContext -Text "[Proje Sistemi] .claude/state.json okunamadı (bozuk JSON). Elle kontrol et."
    exit 0
}

$asama = "$($state.asama)"
$projeAdi = "$($state.proje_adi)"

$asamaAciklamalari = @{
    'fikir'        = 'Fikir dokümanı geliştiriliyor (docs/Proje-Fikri.md). Sıradaki adım: dokümanı netleştir, sonra denetime geç.'
    'denetim'      = 'Fikir dokümanı denetleniyor. Sıradaki adım: riskli/bilinmeyen teknoloji kararları varsa küçük bir spike ile doğrula, sonra finalizasyona geç.'
    'finalizasyon' = 'Final doküman hazırlanıyor (docs/Final-Dokuman.md) -- teknoloji stack ve mimari kararları netleşiyor. Sıradaki adım: roadmap.'
    'roadmap'      = 'Roadmap hazırlanıyor (docs/Roadmap.md) -- faz faz, her faz için bitti kriteri tanımlanıyor. Sıradaki adım: uygulamaya başla.'
    'uygulama'     = 'Roadmap takip edilerek uygulanıyor.'
    'tamamlandi'   = 'Proje tamamlandı.'
}

$aciklama = if ($asamaAciklamalari.ContainsKey($asama)) { $asamaAciklamalari[$asama] } else { "Bilinmeyen aşama: $asama" }

$lines = [System.Collections.Generic.List[string]]::new()
$lines.Add("[Proje Sistemi] Proje: $projeAdi")
$lines.Add("Aşama: $asama -- $aciklama")

if ($asama -eq 'uygulama') {
    $roadmapPath = Join-Path $docsDir 'Roadmap.md'
    if (Test-Path -LiteralPath $roadmapPath -PathType Leaf) {
        $rows = @(Get-Content -LiteralPath $roadmapPath | Where-Object { $_ -match '^\|\s*\d+\s*\|' })
        $total = $rows.Count
        $current = $rows | Where-Object { $_ -notmatch '✅' } | Select-Object -First 1
        if ($current) {
            $lines.Add("Roadmap: $total faz, aktif satır -> $current")
        }
        elseif ($total -gt 0) {
            $lines.Add("Roadmap: $total fazın hepsi tamamlandı görünüyor -- state.json'da asama'yı 'tamamlandi' yapmayı düşün.")
        }
    }
}

$designPath = Join-Path $projectDir 'DESIGN.md'
$legacyDesignPath = Join-Path $docsDir 'Design.md'
if (Test-Path -LiteralPath $legacyDesignPath -PathType Leaf) {
    $lines.Add("Not: eski docs/Design.md duruyor. Frontend işine dönüldüğünde create-design-md ile köke DESIGN.md olarak taşı, ikisini birden canlı tutma.")
}
if ((-not (Test-Path -LiteralPath $designPath -PathType Leaf)) -and (-not (Test-Path -LiteralPath $legacyDesignPath -PathType Leaf)) -and $asama -in @('finalizasyon', 'roadmap', 'uygulama')) {
    $lines.Add("Not: DESIGN.md henüz yok. Frontend işine başlamadan önce create-design-md + ui-ux-pro-max ile oluştur (bkz. global CLAUDE.md).")
}
elseif (Test-Path -LiteralPath $designPath -PathType Leaf) {
    $designContent = ''
    try { $designContent = Get-Content -LiteralPath $designPath -Raw -ErrorAction Stop } catch { }
    if ($designContent -match '<[A-ZÇĞİÖŞÜ_]+>') {
        $lines.Add("Not: DESIGN.md var ama hâlâ yer tutucu içeriyor gibi görünüyor, doldurulmamış olabilir.")
    }
}

Write-HookContext -Text ($lines -join "`n")
exit 0
