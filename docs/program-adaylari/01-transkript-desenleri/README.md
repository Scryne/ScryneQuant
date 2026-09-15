# Program adayı 01 — Transkript kaynaklı seans/fiyat desenleri

**Durum:** DONDURULMUŞ TASLAK · program kaydı **değil** · deftere yazılmadı · hiçbir şey
koşturulmadı · **Tarih:** 2026-09-15

Bu klasör bir araştırma programının **açılmış hâli değil**, açılabilecek bir programın
sonucu görülmeden dondurulmuş girdisidir. Defter sayısı (38) ve `oos_sharpe` eşiği (1,02) bu
klasörden etkilenmez.

## 1. Neden şimdi koşturulmuyor

| Engel | Kaynak | Sonuç |
| --- | --- | --- |
| Program kaydı komutu ve "kayıtsız program koşturulamaz" testi Faz 11'in işi | Roadmap Faz 11, Faz 12 ön koşulu | Program bugün kurala uygun biçimde açılamaz |
| `rejim_kararliligi`, `parametre_perturbasyonu`, `pbo` eşikleri açık; `evren_dayanikliligi` tek sembolde ölçülemez | K-054 | Hiçbir sonuç bugün promotion'a çevrilemez |
| Tek sembollü BTC yönlü arama kapalı; açmak ölçüyle "belirgin farklı bilgi kaynağı" ister | K-045, K-051/2 | Gerekçe ölçüsü (§4) önce gelir |
| Kurallar ve parametreler bir LLM tarafından önerildi (kesim Mayıs 2026) | K-049/4 | Kesim öncesi dönem için `leak_riski`; temiz pencere ileriye dönük (§3) |
| Global defter: her çekiliş Faz 12'nin programlarının eşiğini de yükseltir | K-044, K-051/1 | Bütçe Faz 12 programlarıyla birlikte düşünülmeli |

"Sadece bakıyorum" diye koşturmak da çekiliştir (Roadmap Faz 16).

## 2. Dosyalar ve dondurma kimliği (K-049/5)

| Dosya | SHA-256 (LF, git'teki blob) |
| --- | --- |
| `hipotez_adaylari.json` — 114 aday, 24 aile | `cd28ddf05ab03e990699f9d13647838c900803555c2eb90f670927d9fed3c5ec` |
| `grup_a_on_kayit_taslagi.json` — 10 aday, tek parametre seti, K-051 taslağı, bütçe tahmini | `0a4684b1c0dc1f57911c158b3ea6933723fc985ba1a01d684916864e68954fa3` |
| `grup_b_varlik_sinifi_karari_gerekli.json` — 104 aday, varlık sınıfı özeti | `faa430315c9afed7ab394069c27a5570ba0f52a26adf9ce5dc6957046d5a8fa4` |

- **Hash kanonu LF'dir.** Dosyalar Windows'ta CRLF ile üretildi ve `core.autocrlf=true` checkout'ta
  yine CRLF yazabilir; doğrulama `git show HEAD:<yol> | sha256sum` ile ya da `\r` silinerek
  yapılır. İlk commit'teki (05b6ebd) README CRLF hash'lerini yazmıştı (`1daa0779…`, `503bfb50…`,
  `28f8d9fa…`); içerik bayt olarak aynı, yalnızca satır sonu farklı — kural değişmediği için
  dondurma tarihi yeniden başlamaz.

- **Üreten model:** `claude-opus-5` · eğitim kesimi **2026-05** (önceden kaydediliyor, K-049/4).
- **Girdi:** 79 transkript (`.md`; DREYKO 22, Kaanermi 57), repoda değil. Ağaç hash'i (göreli
  yol + dosya SHA-256'sı, sıralı): `d5a4add810471b4b9f1d77c6fb939c3f2ffa20c1dd5e0e9e110e3f55bf3b6247`.
- **Değiştirilemez:** Bu dosyalarda sonradan yapılacak her değişiklik (parametre, kural, çıkış)
  yeni bir türetimdir ve dondurma tarihi yeniden başlar. Onayda yapılacak düzeltmeler de buna
  dahildir — düzeltme yapılacaksa **koşturmadan önce** yapılır ve yeni hash yazılır.

## 3. İleriye dönük değerlendirme penceresi

- **Pencere başlangıcı = commit `05b6ebd`, 2026-09-15T22:20:33+03:00 (19:20:33 UTC).**
  Değerlendirmeye yalnızca açılış zamanı bu andan sonra olan barlar girer.
- Bu tarihten sonraki BTCUSDT verisi ne LLM'in eğitiminde ne de kaynak videolarda olabilir; bu
  pencerede ölçülen sonuç `leak_riski` taşımaz.
- Binance arşivi geçmişi sakladığı için veri şimdiden biriktirilmek zorunda değil; program
  açıldığında indirilir ve sha256 ile dondurulur.
- **Pencere öncesi veri** yalnızca tanımlayıcı olarak raporlanabilir, `leak_riski` bayrağıyla;
  kapı kanıtı değildir.
- Asgari örnek: `asgari_islem` kapısı (30). 1d kuralları (DREYKO-PRS-02-h1, 02-h2, 07-h2,
  09-h3) bu pencerede yıllarca yeterli olay üretmeyebilir — bu, program kaydında bütçe ve
  durma kuralı yazılırken bilinmesi gereken bir sınır, sonradan gevşetilecek bir kural değil.

## 4. Gerekçe ölçüsü taslağı — M-1 "NY saati çapası" (koşturulmadı)

Grup A'daki Lunch ailesi (KAANERMI-LUNCH-01-h1, LUNCH-02-h1, LUNCH-11-h1) şu iddiaya dayanır:
BTC'de ABD seans saatine **(ET saati)** bağlı bir yapı var. Bu, fiyat geçmişinden bağımsız
bir bilgi eksenidir — ama olup olmadığı ölçülmedi. K-051/2'nin istediği ölçü budur.

**Bu ölçü de bir çekiliştir** ve program kaydından sonra, programın ilk çekilişi olarak koşar.

- **Veri:** BTCUSDT 1m, program kaydı anındaki sha256 ile dondurulmuş.
- **Olay (çapa saati a için):** Hafta içi ET günü. `R` = [a−60 dk, a) aralığındaki 1m
  barların low minimumu / high maksimumu. [a, a+30 dk) içinde ilk 1m bar `low < R_low` ve
  `close ≥ R_low` → alt süpürme olayı; `y = ln(close[+60 dk] / close[olay])`. Üst süpürme
  simetrik, `y` işaret çevrilmiş (ölçüm; işlem değil, long-only kısıtı uygulanmaz). Gün başına
  ilk olay.
- **İstatistik:** `S(a)` = ortalama `y` / standart hata.
- **Test 1 — saat plasebosu:** `S` 24 saatin tamamında 15 dk aralıkla (96 çapa) hesaplanır.
  `p = sıra(S(13:00 ET)) / 96`, tek taraflı.
- **Test 2 — yaz saati ayrımı:** Kış aylarında (ET = UTC−5) `S(13:00 ET = 18:00 UTC)` ile
  `S(17:00 UTC)` karşılaştırılır. Etki NY saatine bağlıysa ilk değer büyük olmalı; UTC saatine
  bağlıysa ikincisi.
- **Önceden yazılan karar kuralı:** Test 1'de `p ≤ 0,05` **ve** Test 2'de yön NY saatini
  destekliyorsa Lunch ailesi program kaydına gerekçe olarak girebilir. Değilse Lunch ailesi
  **çekiliş harcanmadan kapanır**; çapa saati, pencere uzunluğu veya ileri getiri ufku
  değiştirilerek tekrar ölçülmez.
- **Kapsam sınırı:** M-1 yalnızca Lunch ailesini gerekçelendirir. Grup A'nın diğer yedi adayı
  (fib, FVG, inside bar, günlük süpürme, OB, volatilite) saat eksenine dayanmaz; onlar için
  "belirgin farklı bilgi kaynağı" gerekçesi bu klasörde yok ve program kaydına ancak böyle bir
  gerekçeyle girebilirler.

## 5. Açık kararlar (Scryne)

1. `grup_a_on_kayit_taslagi.json` içindeki parametre önerilerinin onayı veya düzeltilmesi
   (düzeltme → yeni hash, §2).
2. Program Faz 12/16 kapsamında açılsın mı; açılırsa bütçesi Faz 12 programlarıyla nasıl
   paylaşılır (K-051/3 tahmini dosyada: 10 çekilişle DSR ≈ 0,97, Bonferroni ≈ 1,34).
3. Grup B için hiçbir varlık sınıfı bu adaylar gerekçesiyle açılmaz (K-053); liste bekler.
