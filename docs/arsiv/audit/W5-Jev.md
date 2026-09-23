# W5 — Jev Audit

**Tarih:** 2026-09-20 · **Baseline:** `1e1a05b` · **Kod değişikliği:** yok
**Okunan:** `src/scryne_quant/jev/*` (9 modül), `config/jev.json`, `cli/jev.py` (yüzeysel),
`tests/unit/test_jev_{izolasyon,durum,karar,defter,golge,tekrar,sonuc}.py`, `docs/arsiv/Jev-Denetim.md`
(Conflicts C1-C11), `docs/arsiv/Jev-Golge-Raporu.md`, `docs/arsiv/spikes/07-jev-durum.md`, K-049/061/067/
074/075/076/077, `runs/jev/golge-3.sqlite` (salt okunur sayım), `runs/jev/golge-3.log`.

Jev burada brief §9'un dediği gibi ele alındı: bir **araştırma bileşeni**, alfa üreteci değil.

---

## 0. Özet

Jev katmanı **tasarım niyeti ile kod arasında fark olmayan** nadir parçalardan biri: yalnız
gölgede, ayrı süreçte, işlem katmanına ulaşamayan (AST testli, CI'da adıyla), fail-closed,
zincir hash'li defterli, sonuç tanımları koşudan önce dondurulmuş. **Deterministik güvenlik
kontrollerini atlayamaz — VERIFIED** (§3). Açık noktalar bilgi değeri (K-076 ile yön ekseni
kapandı) ve kesim tarihinin UNKNOWN kalması (replay kanıtı geçersiz, yalnız ileriye dönük
pencere sayılır).

| # | Bulgu | Sınıf |
| --- | --- | --- |
| J1 | Jev → risk/execution/oms/imzali/emir_adaptoru import yolu yok; işlem katmanı jev/typesafe import edemez; `Sinyal` üreten fonksiyon yok; tek tüketici pano (dosya okur, import etmez) | VERIFIED |
| J2 | Eğitim kesim tarihi `null` → **her** geriye dönük replay `leak_riski=true`; tek geçerli kanıt sınıfı yayın sonrası (2026-09-10T18:38Z) pencere | VERIFIED (dürüst) — bilgi sınırı |
| J3 | Yön ekseni bilgi kaynağı değil: 1.099 yönlü karar, isabet %49,0 (CI 0,46-0,52), net −0,38 %/işlem, küme-etkin n=183'te %51 | VERIFIED (K-076) |
| J4 | Gölge koşusunda çekimserlik ≈ 1,0 (`P(flat)` 0,88-0,90 sabit) → "yön isabeti" BTC'de ölçülemiyor; rapor bunu öngörmüş | PARTIAL — ölçüm sınırı |
| J5 | Model pini `jev-1.13.0`; `/v1/models` bu sürümü listelemiyor (takma adlar), çözülen≠istenen → GECERSIZ | VERIFIED — TypeSafe sürüm yaşam döngüsüne bağımlılık RISK |
| J6 | Determinizm: aynı durum → cevap ±0,01-0,03 sapıyor (bit-deterministik değil); sapma ölçülüp kaydediliyor | VERIFIED (konvansiyon) |
| J7 | Jev çıktısı için brief §19 "experiment contract" yerine K-074 kalıbı: gölge ölçümü çekiliş değil, soru/marj/durum değişimi = yeni çekiliş | VERIFIED (kural) |

## 1. Mimari (kod ile doğrulandı)

```
 exchange/akis.py BinanceBarAkisi (paper'la aynı akış + kalite bayrakları)
        │  kapanmış ok 1h bar
        ▼
 jev/golge.py  GolgeKosturucu (ayrı süreç: `sq jev golge`; kendi kilidi; `.dur` bayrağı)
        │  live/pencere.py BarPenceresi (1200 bar)
        ▼
 jev/durum.py  kanonik_durum(i) — betimleyici etiketler ("EMA20 üstünde", "funding p90"),
               4h kovaları 1h'den, kapanmış ⇔ b+4h ≤ veri_kesimi; funding kendi kesimi;
               duvar saati yok, rastgelelik yok, yalnız [i-1199..i]  → durum_hash
        ▼
 jev/sorular.py  4 donmuş soru (yon Choice · rejim · kurulum Score · cekimser Noul), SORU_SHA256 testli
        ▼
 jev/istemci.py  tek TypeSafeClient; system_one(state, questions, model=pin); timeout 20 s,
                 2 deneme; hata sınıfı; 6 sır adının değeri metinlerden temizlenir
        ▼
 jev/karar.py    karar_kur → JevKarari (frozen, extra=forbid); yön = olasılık vektörü + marj 0,20;
                 model_cozulen ≠ istenen → GECERSIZ; bayat (>2h) → BAYAT_DURUM; hata → HATA
                 alanlar: miktar/fiyat/kaldıraç/stop **yok**
        ▼
 jev/defter.py   runs/jev/<kosu>.sqlite — kosu/karar/olay; onceki_hash zinciri;
                 UPDATE/DELETE tetikleyicileri; durum bytes + ham yanıt saklanır
        ▼
 jev/sonuc.py    open[t+1] giriş; ufuk 1/4/24; MAE/MFE; gidiş-dönüş maliyet; Wilson CI;
                 al_tut kıyası; güven kovaları, Brier, ECE; rejim başına — config'te önceden sabit
 jev/tekrar.py   tarihsel replay → data/semantik/jev/<turetim_id>/ (Parquet+manifest, leak_riski)
                 backtest bunu **çağırmaz**; okuyan yok (K-049/5 dondurma kalıbı hazır, tüketici yok)
```

Tüketiciler: `live/evren_pano.py` `runs/jev/*.sqlite` dosyalarını **okur** (import etmez,
`evren_pano.py:590` yorumu + izolasyon testi); `research/gizli_tekrar.py` TypeSafe'i **ayrı**
amaçla (hipotez metni benzerliği, K-061) kullanır — izolasyon testi bunu tek istisna olarak
adlandırıyor.

## 2. Denetim maddeleri (brief §9)

| Madde | Durum | Kanıt |
| --- | --- | --- |
| Importlar / bağımlılıklar | VERIFIED | W1 grafiği: `jev` → common, data.depo, exchange.akis, features, live.akis/pencere. `test_jev_izolasyon.py`: YASAKLI = {risk, execution, oms, exchange.imzali, exchange.emir_adaptoru}, geçişli; işlem katmanı (strategy, backtest, features, risk, …) `jev`/`typesafe` import edemez; `typesafe` yalnız `jev/istemci.py` (+gizli_tekrar); testin kendisi negatif kontrollü (`test_gecisli_yasak_yakalaniyor`) |
| Veri erişimi | VERIFIED | Aynı `BinanceBarAkisi` ve `ParquetDepo`; ham dizi Jev'e **gitmez**, etiket gider (C5; Jev aritmetikte güvenilmez — Spike 7 ölçtü) |
| Zaman damgaları / kesim | VERIFIED | `veri_kesimi_ms = karar_ms + 1h`; 4h kovaları kapanmış olmalı; funding `available_time`; `test_jev_durum.py`: gelecek bozulunca/silinince JSON **byte-identical** (10 tekrar), negatif kontrol (sızdıran kurucu yakalanıyor); CI'da adıyla |
| Eğitim sınırı | UNKNOWN (kayıtlı) | `config/jev.json egitim_kesim_utc: null, kaynak: "dogrulanmadi"`; yayın 2026-09-10T18:38Z `/v1/models`ten; K-075: yayından sonra açılan bar için replay kesimden bağımsız |
| Çıkarım sınırı / gölge | VERIFIED | `sq jev golge` ayrı süreç; `PaperMotoru`/`RiskMotoru` ile bağ yok; emir yok; K-074/5 fail-closed (2 deneme → karar yok) |
| Çıktılar | VERIFIED | `JevKarari` tipli; yön etiketi ölçüm için (SHORT dahil, C6), sinyal eşlemesi yok |
| Kalıcılık | VERIFIED | SQLite zincir hash (risk/audit kalıbı), silinemez; replay Parquet + manifest, `turetim_id` = içerik hash'i |
| Model/sürüm takibi | VERIFIED / RISK | `model_istenen`, `model_cozulen`, `soru_sha256`, `durum_surumu`, `durum_hash`, `yanit_hash`, token sayıları her kararda. RISK: eski sürümler API'den kalkıyor (global CLAUDE.md notu); `jev-1.13.0` `/v1/models`te listelenmiyor, pinleyince kabul ediliyor — bir gün reddedilirse gölge **fail-closed durur** (doğru davranış) ama pencere kesilir |
| Sızıntı riski | VERIFIED (mekanizma) | `leak_riski` her kayıtta; kesim `null` iken yayın öncesi tüm replay `true`; `sonuc.py` `kanit: false` yazar |
| Strateji etkileşimi | **yok** | `grep` sonucu: `strategy/`, `research/` (gizli_tekrar hariç) `jev`i bilmiyor; `Deney.TIPLER`e `jev_golge/jev_tekrar` eklendi (kayıt için) |
| Risk etkileşimi | **yok** | import yok; K-037 "kapı yalnız eler" tasarımı (C7) **kodlanmadı** — çünkü eleyecek bir bağlantı da yok |
| Execution etkileşimi | **yok** | import yok; `exchange.imzali` ve `emir_adaptoru` yasaklı listede |

## 3. "Jev deterministik güvenlik kontrollerini atlayabilir mi?" — Hayır (VERIFIED)

Beş bağımsız katman, her biri tek başına yeterli:

1. **Statik:** `jev/` → {risk, execution, oms, imzali, emir_adaptoru} geçişli import yok (AST
   testi, CI adımı).
2. **Ters yön:** işlem katmanı `jev`/`typesafe` import edemez; `Sinyal` üreten fonksiyon yok
   (K-067). Jev çıktısını strateji girdisine çeviren tek yol K-067/3 "dondurulmuş alan"
   kalıbıdır ve **henüz hiçbir strateji bunu okumuyor**.
3. **Tip:** `JevKarari`'de miktar/fiyat/kaldıraç/stop alanı yok; `OnayliNiyet` yalnız
   `RiskMotoru` mühürleyebilir (W2 §1) — Jev'in üreteceği hiçbir nesne execution kapısından
   geçemez.
4. **Süreç:** ayrı süreç, ayrı SQLite, ayrı kilit; paper sürecinin belleğine erişimi yok.
5. **Kural:** K-049/1 semantic AI yetkisiz; K-074/1 "yön bir ölçümdür"; K-076 yön ekseni
   kapalı; K-077 B/C/D/E açılmaz; değişiklik yeni K + yeni çekiliş ister.

Kalan tek teorik yol: bir insanın pano/rapordan okuyup elle işlem yapması — bu yazılım sınırı
değil, K-050'nin (izni artıran yön elle onay) kapsamı.

## 4. Kanıt durumu (Jev "ne biliyor?")

| Soru | Cevap | Kaynak |
| --- | --- | --- |
| Yön (long/short/flat) bilgi taşıyor mu? | **Hayır** (50 sembol × 197 bar yayın sonrası, %49,0, net negatif, kalibrasyon yok, saat-küme düzeltmeli) | K-076, Faz-16-Jev-Evren-Replay |
| Rejim/seçici olarak? | Oracle tavanı 0,60 < 1,04 → **headroom yok** | K-077 |
| BTC gölge (golge-1 host 09-17→, golge-3 yerel 09-20→) | Çekimserlik ≈1,0; 16 karar yerelde, hepsi `flat` P≈0,9 → yön isabeti ölçülemez; boru hattı sağlıklı (gecikme 0,7-1,0 s) | `runs/jev/golge-3.log`, Golge-Raporu §2/§4 |
| Tutarlılık | ±0,01-0,03 (24 kararda bir yeniden sorma) | Spike 7, golge tutarlılık olayı |
| Maliyet | token sayıları kayıtta; Spike 7 gecikme medyanı 0,31-0,36 s | config not |
| Replay isabeti (yayın öncesi) | **kanıt değil** (`leak_riski=true`, `kanit: false`) | K-049/4, K-075 |

**Örneklem notu (bu denetimin eklediği):** K-076'nın penceresi yayın sonrası ≈8 gün (197 bar).
Karar, kümeleme düzeltmesiyle (etkin n=183) verilmiş ve Wilson CI 0,46-0,52 yazı-turayı
kapsıyor; "bilgi yok" sonucu **bu pencere ve bu soru seti için** sağlam. Farklı bir soru/durum
yeni çekiliştir (K-076/4) — bu doğru. Ama tek rejimlik 8 günün "Jev hiçbir zaman bilgi
taşımaz"a genellenmesi kanıtın ötesidir; K-076 bunu iddia etmiyor, gölge açık kalıyor.

## 5. Brief §17 "Jev Research Assistant" (R10) için mevcut durumun anlamı

- Yön/rejim/seçim eksenleri kapalı; yeniden açma koşulu K-074 "geri dönüş koşulları" +
  K-076/4 (yeni soru = yeni çekiliş + program bütçesi).
- Kodun **kullanılmayan** ama hazır kısımları: replay → dondurma → `leak_riski`'li Parquet
  (K-049/5 kalıbı), `Deney.TIPLER` jev tipleri, gizli tekrar dedektörü (hipotez metni
  benzerliği — **çalışan** ve araştırma yönetişimine gerçekten katkı veren tek Jev kullanımı).
- Brief'in "hypothesis generation, analysis" rolü için repo'da **hiçbir kod yok** ve K-049/1
  (semantic AI yetkisiz) bunu araştırma yönetişimi dışında tutuyor. Jev'in bir sonraki
  makul rolü sinyal değil **yönetişim**: gizli tekrar, gerekçe/rapor tutarlılığı, deney
  sözleşmesi doğrulama (W3 R7) — hepsi TypeSafe'in "tipli yargı" kullanım alanına giriyor
  ve K-049'u ihlal etmiyor. Bu bir öneri, karar değil → ROADMAP-RESET R10.

## 6. Açık kalemler

| # | Kalem | Sınıf |
| --- | --- | --- |
| J2 | Kesim tarihi: TypeSafe'e resmi beyan soruldu, cevap yok | UNKNOWN — dışsal |
| J5 | `jev-1.13.0` pininin API ömrü | RISK — izleme: gölge GECERSIZ üretmeye başlarsa pencere kapanır, sonuç yazılır |
| J4 | BTC'de çekimserlik 1,0 → yön ölçülemez; soru **değiştirilmez** (rapor §4/1) | ölçüm sınırı |
| — | `TYPESAFE_API_KEY` hostta kullanıcı ortamında, `.env`de değil; yerelde de ortamda (değer okunmadı) | VERIFIED (ad) |
| — | Jev ölçüm betikleri `tools/faz16_jev_*` per-file-ignore ile donmuş | W8 |

**Sonraki dalga:** W6 — Test / CI / Determinizm.
