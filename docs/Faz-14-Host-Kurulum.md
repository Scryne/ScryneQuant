---
proje: ScryneQuant
faz: 14
tarih: 2026-09-17
type: runbook
durum: host ayakta, host-1 koşuyor
---
# Faz 14 — Sürekli açık host kurulumu (K-063)

Host Scryne'ın **ikinci bilgisayarı**: Windows 11 (build 26200), i5-12400F, 16 GB RAM,
kablolu ağ, ev ağında `192.168.1.4`, kullanıcı `Scryne\scryn`. Ana makine (`192.168.1.5`)
araştırmayı taşır; host yalnızca canlı paper/gözlem koşusunu taşır.

## 1. Erişim: SSH, yalnızca anahtar, yalnızca ev ağı

Scryne'ın hostta elle yaptığı tek adım yönetici PowerShell'de OpenSSH sunucusunu açmaktı.
Sonrası ana makineden SSH ile yapıldı.

| Ayar | Değer | Doğrulama |
| --- | --- | --- |
| Anahtar | `~/.ssh/scrynequant_vps` (ed25519, yalnızca bu host) | `administrators_authorized_keys` |
| `PasswordAuthentication` | `no` | `sshd -T`; parolayla deneme → `Permission denied (publickey)` |
| `KbdInteractiveAuthentication` | `no` | aynı |
| Güvenlik duvarı | `OpenSSH-Server` kuralı `RemoteAddress = LocalSubnet`, profil Private | `Get-NetFirewallAddressFilter` |
| Uyku / hazırda bekleme (AC) | hiçbir zaman (`0`) | `powercfg /query` |
| Windows Update etkin saatler | 09:00-03:00 | kayıt defteri |

Bağlanmak: `ssh -i ~/.ssh/scrynequant_vps scryn@192.168.1.4`

**Öğrenilen iki tuzak:**

1. `sshd_config`in sonuna eklenen satır Windows varsayılan dosyasındaki `Match Group
   administrators` bloğunun **içine** düşer ve yalnızca o grupta geçerli olur. Global ayar
   dosyanın **başına** yazılmalı; `sshd -T` ile doğrulanmalı.
2. SSH oturumu içinden `Restart-Service sshd` oturumu koparır. Oturum içinden başlatılan
   arka plan işi (`Start-Job`) ise oturumla birlikte ölür ve servis hiç yeniden başlamaz.
   Güvenli yol: SYSTEM hesabıyla 20 sn sonrasına tek seferlik zamanlanmış görev, sonra silinir.

## 2. Ortam

- `uv` 0.12.15 (`%USERPROFILE%\.local\bin\uv.exe`), CPython 3.12.14, `uv sync --frozen`.
- Kod: `%USERPROFILE%\Documents\Projeler\ScryneQuant`. Depo private; hosta GitHub kimlik
  bilgisi **konmadı**. Kod ana makineden `git bundle` ile gider.
- Test paketi hostta: **1.529 geçti, 2 atlandı** (funding verisi yok; bilinçli TA-Lib sapması).
- Veri: `sq data indir BTCUSDT 1h --yil 1` → 8.766 bar, kalite %100, 3,4 sn. Binance REST
  hosttan erişilebilir.

## 3. Koşu: `host-1`

| | |
| --- | --- |
| Görev | `ScryneQuant-Paper`: açılışta, oturum açmadan (S4U), çökerse 1 dk arayla yeniden başlar, süre sınırı yok |
| Komut | `tools\paper-kosu.ps1 -KosuAdi host-1 -Strateji ema_kesisim -Mod gozlem -Port 8787` |
| Başladı | 2026-09-17 14:29:39 UTC, temiz başlangıç |
| Mod | **gözlem** — promotion kanıtı üretmez (K-035); ölçülen şey hostun dayanıklılığı (K-055) |
| Kayıt | `runs\paper\host-1.sqlite` (koşunun tamamı), `runs\paper\host-1.log` |
| Dashboard | `http://127.0.0.1:8787` (yalnızca host içinden; ağa açılmadı) |

Neden tek sembollü ve gözlem: paper motoru bugün tek sembollü. Çok enstrümanlı paper motoru
Faz 14'ün işi; hazır olana kadar 30 günlük dayanıklılık sayacı bu koşuyla işler.

## 4. Operasyon

**Durum:**
```
ssh -i ~/.ssh/scrynequant_vps scryn@192.168.1.4 "cd %USERPROFILE%\Documents\Projeler\ScryneQuant && .venv\Scripts\python.exe -m scryne_quant.cli.main paper durum host-1"
```

**Kod güncelleme (planlı durdurma kesinti sayılmaz, K-043):**
1. Ana makinede: `git bundle create scrynequant.bundle master` → `scp` hosta.
2. Hostta: `sq paper durdur host-1 --sebep "kod guncellemesi"`.
3. Hostta: `git pull <bundle> master`, `uv sync --frozen`, testler.
4. `Start-ScheduledTask ScryneQuant-Paper`.

**Görevi kaldırmak:** `Unregister-ScheduledTask -TaskName ScryneQuant-Paper -Confirm:$false`

## 5. Açık kalemler

1. **Yeniden başlatma tatbikatı:** host kapatılıp açıldığında görevin oturum açmadan başladığı
   ve koşunun toparlandığı henüz **ölçülmedi**.
2. Süreç dışı kill switch, alarmlar/runbook, çok enstrümanlı paper motoru (Faz 14 bitti kriteri).
3. Dashboard'a ana makineden erişim (ağa açmak ayrı bir karar: şu an yalnızca host içi).
