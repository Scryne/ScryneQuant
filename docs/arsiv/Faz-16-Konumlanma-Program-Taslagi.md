---
durum: taslak
tarih: 2026-09-17
karar: Scryne onayı bekliyor
---

# Faz 16 — Program taslağı: konumlanma (`konumlanma_evren`)

Bu bir **program kaydı taslağıdır** (K-051/2). Onaylanırsa `sq lab program-kaydet` ile
deftere açılır; açılmadan hiçbir çekiliş koşmaz (K-039).

## 1. Soru

Kalabalığın **miktarı ve bileşimi**, evren kıyasının seçimini iyileştirir mi?

Faz 12 kalabalığın **fiyatını** ölçmüştü (funding: taşıma maliyeti) ve **vadeli talebi**
(basis: perp primi); dördü de kıyası geçemedi. Bu program aynı olguyu başka bir yerden ölçüyor:
kaç sözleşme açık (`sum_open_interest`), bu pozisyonların kimde olduğu
(`sum_toptrader_long_short_ratio`, `count_long_short_ratio`) ve agresif akışın yönü
(`sum_taker_long_short_vol_ratio`).

Mekanizma iddiası: **pozisyon yoğunlaşması tasfiyeye açıklıktır.** Fiyat hareketi olmadan da
kaldıraç birikebilir; funding bunu ancak taşıma maliyeti yükseldiğinde gösterir, açık pozisyon
doğrudan gösterir.

## 2. Kaynak farkı (K-045 istisnası — sayısal dayanak)

Kaynak: `data.binance.vision futures/um/daily/metrics`, 5 dakikalık ızgara, 2020-09'dan bugüne.
İndirilen: **258 sembol, 61,9 milyon satır, 3,3 GB** (`tools/faz16_metrics_indir.py`).
Ölçüm: `tools/faz16_kaynak_olcumu.py` → `runs/faz16/kaynak-olcumu-konumlanma.json`.

Ön ölçüm (164 sembol; kesin sayılar tam indirme sonrası güncellenecek), `1 − R²` = **mevcut
kaynakla açıklanamayan pay**:

| Ölçüm | Medyan | Yorum |
| --- | --- | --- |
| Açık pozisyon değişimi ↔ aynı gün getirisi | (ölçülüyor) | Sözleşme adedi üzerinden; USD değeri fiyatı mekanik içeriyordu |
| Açık pozisyon değişimi ↔ aynı gün funding | 0,974 | Funding'in yeniden ifadesi değil |
| Açık pozisyon değişimi ↔ BTC'nin açık pozisyonu | 0,880 | Kesitte kendi bilgisi var |
| Büyük hesap long/short ↔ getiri | 0,977 | Fiyattan bağımsız |
| Taker akışı ↔ getiri | 0,985 | Fiyattan bağımsız |

Kesit (eşzamanlı Spearman): açık pozisyon değişimi ↔ 7 günlük getiri sırası **0,139**; ↔ funding
sırası **0,045**; taker ↔ 7 günlük getiri **−0,016**; büyük hesap ↔ funding **0,341** (tek orta
düzey akrabalık, beklenen). Kesitin birinci temel bileşen payı **0,379**.

**Uyarı, kaydın parçası:** farklı olmak değerli olmak değildir. Bu tablo yalnızca K-045'in
istisna şartını karşılar.

## 3. Çekilişler (bütçe 4)

Hepsi kıyasın (`evren_esit_agirlik`, n=10, haftalık, hedef brüt 0,2) üstüne **tek bir dışlama**
ekler; seçim, ağırlık, dengeleme takvimi aynı. Dışlama oranı 0 iken sonuç kıyasla bit düzeyinde
aynı olmalı (testle).

| # | Ad | Skor | Soru |
| --- | --- | --- | --- |
| 1 | `evren_oi_birikim` | `pencere` saatte açık pozisyon artışı (sözleşme adedi, log) | Kaldıraç birikimi en yüksek dilim geride mi kalıyor |
| 2 | `evren_taker_baski` | `pencere` saatte taker long/short oranının ortalaması | Agresif alım baskısının en yüksek dilimi |
| 3 | `evren_buyuk_hesap` | Büyük hesapların long/short oranı | Kalabalığın **kim** olduğu ayırt ediyor mu |
| 4 | `evren_oi_taker` | 1 ve 2'nin kesit sırası ortalaması | İkisi birlikte |

Izgara (her çekiliş için aynı, 12 nokta): `pencere` ∈ {24, 72, 168, 720} saat, `dislama_orani`
∈ {0,1, 0,2, 0,3}; `azami_enstruman`=10, `yeniden_dengele_bar`=168, `hedef_brut`=0,2 sabit.

## 4. Durma kuralı

İlk **iki** çekiliş (`evren_oi_birikim`, `evren_taker_baski`) OOS'ta filtresiz kıyasın Sharpe'ını
geçmezse 3 ve 4 **harcanmaz**, program kapanır. Izgara, pencere kümesi ya da dışlama oranları
sonuçlara bakarak genişletilmez.

## 5. Eşik ve sayım

- Ölçülebilir çekiliş sayısı bugün **41** (defterde 48 kayıt, 7'sinin değerlendirme kaydı yok).
  `oos_sharpe` kapısı **1,04** (K-064; 2026-09-17'de yeniden ölçüldü, p95 = 1,0388 — bayat değil).
- Bu programın her çekilişi defteri büyütür; program bitince eşik **yeniden ölçülür** ve
  `research/kapilar.py` güncellenir (K-044). Yani dört çekiliş, geçme çıtasını da yükseltir.
- Her hipotez kaydından önce `sq lab tekrar-kontrol` (K-061) koşar: aynı mekanizmanın başka adla
  tekrarı mı?

## 6. Veri sözleşmesi (çekilişler bunu varsayar)

- Günlük konumlanma değeri = o günün **23:55** gözlemi; `available_time = create_time + 5 dk`.
- Bar görünümünde değer, ait olduğu saatten **sonraki** barda görünür (K-052/15).
- Açık pozisyon **sözleşme adedi** üzerinden; USD değeri kullanılmaz (fiyatı mekanik içerir).
- Verisi olmayan üye **dışlanmaz** (funding kuralıyla aynı): bilginin yokluğu, kalabalığın
  varlığı değildir.

## 7. Jev'in bu programdaki yeri (K-067)

Yok. Konumlanma sayısal bir kaynak; Jev metin yargısı verir. Jev'in işi ikinci hatta
(duyuru/haber) ve kayıt öncesi tekrar kontrolünde.
