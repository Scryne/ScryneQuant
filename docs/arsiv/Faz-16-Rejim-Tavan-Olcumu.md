---
proje: ScryneQuant
faz: 16
tur: tavan ölçümü (çekiliş değil, Jev yok, backtest yok)
tarih: 2026-09-20
type: rapor
durum: kapandı — K-077
---
# Faz 16 — Rejim × alpha ailesi oracle tavanı

**Sonuç: rejim-koşullu kusursuz seçici bile kapıları geçemiyor.** Her rejimde OOS'ta en iyi
aileyi sonucu görerek seçen ve geçiş maliyeti ödemeyen bir oracle'ın birleşik OOS Sharpe'ı en
iyi grupta **0,60** (eşik 1,04), en kötü rejim Sharpe'ı en iyi grupta **0,52** (eşik 0,685).
Kayıt: **"mevcut alpha evreni üzerinde selector/filter için yeterli headroom yok."** Bu Jev'in
başarısızlığı değil; seçilecek şeyin yokluğu.

Soru (Jev Strategy Discovery denetiminin Faz 0'ı): *"Jev kusursuz bir seçici olsaydı bile
mevcut alpha evreninde yeterli edge var mıydı?"*

## 1. Kurulum

| | |
| --- | --- |
| Girdi | Faz 11: 38 tek-sembol çekilişi, `runs/deneyler/kapilar_v2/301e3750d764-530ecf2a72f1.json` (2026-09-16); Faz 12/16: 14 evren çekilişi, `runs/faz12/*.json` (evren `b06857c0`, OOS bar 55.594–79.420) |
| Rejim | `research/rejim.py`: 30 günlük (720/180/30 bar) kıyas getirisinin işareti, nedensel, parametresiz → `yukselen`/`dusen`. **Yeni rejim tanımı yapılmadı.** |
| Oracle | Her rejimde OOS Sharpe'ı en yüksek aile (**hindsight**), geçiş maliyeti **sıfır**, sermaye tek. "+no-trade": rejimde pozitif aile yoksa flat (E deneyinin üst sınırı). |
| Birleştirme | `rejim.olc`'un tersi: rejim başına ortalama = log1p(getiri)/bar, σ = ortalama·√A/Sharpe; havuz momentleri → birleşik Sharpe. Kayıtlı toplam OOS Sharpe'a karşı 14 evren çekilişinde doğrulandı: sapma ort. 0,07, azami 0,16. |
| Betik | `tools/faz16_rejim_tavan.py` → `runs/faz16/rejim_tavan.json` |
| Yapılmayan | backtest, yeniden üretim, Jev çağrısı, yeni rejim, yeni çekiliş; defter 52'de |

## 2. Rejim × aile (OOS, net, yıllık Sharpe)

| Grup (çekiliş) | Rejim | En iyi üç | Pozitif |
| --- | --- | --- | ---: |
| BTC 1h (17) | dusen | funding_egilim **−0,02** · funding_ters −0,29 · funding_filtre −0,31 | **0/17** |
| | yukselen | funding_egilim +0,83 · momentum/plato +0,78 · ema_kesisim/plato +0,55 | 10/17 |
| BTC 4h (14) | dusen | sma_kesisim +0,11 · rsi_donus +0,07 | 4/14 |
| | yukselen | donchian +0,87 · cok_faktor/plato +0,87 | 11/14 |
| BTC 1d (5) | dusen | momentum +0,52 | 1/5 |
| | yukselen | donchian +0,55 · al_tut +0,48 | 4/5 |
| Evren 1h (14) | dusen | kurma_oynaklik +0,55 · turev_funding_basis +0,47 · turev_basis +0,45 | 9/14 |
| | yukselen | makro_vix +0,38 · kurma_oynaklik +0,22 · kurma_turnover +0,21 | 8/14 |

1d'de `sma_kesisim`/`ema_kesisim` rejim ölçülemedi (Faz 11 §4, geçerli aday yok).

## 3. Oracle — TAVAN, promotion kanıtı değil

| Grup | Oracle Sharpe | Oracle + no-trade | En kötü rejim | `oos_sharpe ≥ 1,04` | `rejim_kararliligi ≥ 0,685` |
| --- | ---: | ---: | ---: | :-: | :-: |
| BTC 1h | +0,11 | **+0,59** | −0,02 (flat 0,00) | ✗ | ✗ |
| BTC 4h | **+0,60** | +0,60 | +0,11 | ✗ | ✗ |
| BTC 1d | +0,50 | +0,50 | +0,52 | ✗ | ✗ |
| Evren 1h | +0,46 | +0,46 | +0,38 | ✗ | ✗ |

**Yaklaşımdan bağımsız üst sınır:** herhangi bir grupta herhangi bir rejimde gözlenen en
yüksek tekil Sharpe **0,87** (BTC 4h yukselen). Kapı 1,04. Hiçbir karışım bileşenlerinin en
iyisini anlamlı biçimde aşmaz; boşluk yaklaşım hatasıyla (≤0,16) kapanmaz.

**Hesaplanamayan kapılar:** WF katman başarısı, asgari işlem, max DD, stres, PBO,
pertürbasyon, evren dayanıklılığı — birleşik oracle serisi için bar düzeyi getiri gerekir;
kayıtlarda yok, yeniden üretim koşusu ister. İki belirleyici kapı düştüğü için sonuç
değişmez; istenirse defterdeki sabit parametrelerle tek yeniden üretimle tamamlanır.

**Alternatif rejim (`jev/durum.py` etiketleri):** hesaplanmadı — bar düzeyi etiket × getiri
gerekir ve bu yeni bir rejim tanımıdır (K-051/4: çekiliş, deftere yazılır).

## 4. K-045 ile karşılaştırma

| | K-045 (Faz 4 dönüş 5) | Bu ölçüm |
| --- | --- | --- |
| Serbestlik | tek strateji, tek sembol, **maliyet sıfır** | maliyet dahil, **rejime göre aile değiştirme + hindsight**, geçiş maliyeti sıfır |
| Sonuç | geçen yok | geçen yok |
| Duvar | sinyal OOS'ta çöküyor (`oos_is_orani` 6/6 negatif) | BTC 1h düşen rejimde 17 aileden **sıfırı** pozitif; yükselende en iyisi bile tek başına eşik altı |

Rejim-koşullu kusursuz seçimin en iyi standalone çekilişe eklediği pay ≈ +0,15–0,20 Sharpe
(4h: 0,60 vs Faz 4 en iyisi 0,46); kapıya kalan mesafe 0,44. Seçim katmanının **teorik azami**
katkısı kapı boşluğunun yarısından az — K-068'in "seçim genelleşmiyor" bulgusunun tavan
tarafı: seçim hindsight'la bile yetmiyor. İki tavan aynı duvarı iki açıdan doğruluyor:
**sorun seçicide değil, seçilecek ailelerde.**

## 5. Sonuçlar

- Jev **B** (rejim seçimi), **C** (aile seçimi), **D** (B+C): açılmaz — oracle 1,04'ün altında,
  Jev'in yakalayabileceği alan sıfır.
- Jev **E** (no-trade filtresi): açılmaz — üst sınırı oracle+no-trade 0,59.
- Jev strategy discovery hattı kapalı; gölge `golge-1` yalnız ileriye dönük doğrulama olarak
  açık (K-076).
- Tek pozitif işaret zaten bilinen: `kurma_oynaklik` iki rejimde de pozitif (0,22 / 0,55) —
  kurma katmanı (K-068) genelleşen tek şey, o da 0,36'da.
- Bir sonraki soru seçici değil, kaynak: gate seviyesine ulaşabilecek yeni edge nereden?
  (`docs/arsiv/Alpha-Discovery-Gap-Audit.md`)
