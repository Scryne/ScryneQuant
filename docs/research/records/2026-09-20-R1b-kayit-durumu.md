# R1(b) — Kayıtlı deneylerin durumu ve yenileme (2026-09-20)

**Girdi:** `runs/deneyler/` altındaki 22 kayıt (18 `TEKRAR_EDILEBILIR` + 3 `coklu_test` + 2
`kapilar_v2`) · **Araç:** `tools/r1b_kayit_durumu.py` → `runs/deneyler/tekrar-durumu.json`
(git dışı; bu tablo o dosyanın kopyası) · **Depo:** ana depoya dokunulmadı; her kayıt geçici bir
kopyada, gerekiyorsa K-080 geri sarımıyla (`e3adb02c…` → 2026-09-09 09:00) koşuldu ·
**Kod:** K-080 + `sq lab dogrula` sınıflandırması + `sq lab yenile` (bu commit).

## Sonuç

| Sınıf | Adet | Ne demek | Ne yapıldı |
| --- | ---: | --- | --- |
| `ayni` | 2 | Geri sarımla **birebir** yeniden üretildi (`monte_carlo`, `stres`) | — (K-080 tek başına yetti) |
| `yalniz_sonuc_hash` | 3 | Ekonomik alanlar birebir; yalnız `sonuc_hash` alanları farklı (K-057/6) | `sq lab yenile` ile **yenilendi**: aynı girdi, bugünkü hash; yeni kayıtlar `dogrula`dan geçiyor; eskiler duruyor |
| `semantik` | 10 | Alan düzeyinde fark: `degerlendirme`de `esikler[*]/gerekce` ve eşikler (0,5→1,02→1,04, K-044/064/071), `karsilastirma`da kıyas metrikleri (`azami_maruziyet`, `gecerli_aday`) ve kayıtta olmayan `cvar_95` | **Tarihsel** etiketi; bugünkü kodla yeniden üretilemez, kayıt commit'leri DIRTY; sayıları raporlarda (Faz 4, dönüşler) |
| `veri_geri_getirilemedi` | 3 | `c32b5bd0…` (2026-09-11) hiçbir başlangıç/bitiş kırpmasıyla bugünkü depodan türetilemedi (72 pencere tarandı) — içerik farkı, uzunluk değil | Tarihsel; adres yok. K-080 öncesi olduğu için `veri_son_ms` de yok |
| `tekrar_edilemez` | 5 | Girdisi bar verisi değil (defter / kapı tablosu) — tasarım gereği | — |

**R1(b) kriteri** ("16/16 ya da her uyuşmazlık etiketiyle yenilenmiş"): 18 tekrar-edilebilir
kaydın tamamı sınıflandırıldı ve etiketlendi; yenilenebilir olan 3'ü yenilendi; 2'si zaten
üretiliyor; 13'ü **adıyla** tarihsel (10 semantik + 3 veri). Bundan sonraki her kayıt
`veri_son_ms` taşıdığı için "depo uzadı" sınıfı bir daha oluşmaz; "kod değişti" sınıfı ise
`dogrula`nın çıktısında adıyla görünür (sessiz değil).

## Yenilenen kayıtlar

| Eski | Yeni | Strateji | tf | Fark (yalnız `sonuc_hash`) |
| --- | --- | --- | --- | ---: |
| `4353f031df00-58bceaed0fe1` | `4353f031df00-7de6f1d23437` | donchian | 1h | 13 |
| `895715401b5b-87dd71bee16b` | `895715401b5b-eec26ee77833` | rsi_donus | 1h | 37 |
| `dc8a5bb9c54e-9e30cb6824a9` | `dc8a5bb9c54e-595b067c7852` | sma_kesisim | 4h | 16 |

Girdi hash'i (kimliğin ilk yarısı) değişmedi → yeni çekiliş değil (K-039); defter sayısı 52.

## Kayıt tablosu

| Kayıt | Tip | tf | Veri | Tarih | Ağaç | Durum | Fark | İlk fark |
| --- | --- | --- | --- | --- | --- | --- | ---: | --- |
| `1a1f444ae057-04b8f2fc0127` | coklu_test | 1h | `49cb00e1` | 2026-09-11 | dirty | **tekrar_edilemez** |  | `` |
| `91d0d4b0ff73-67b1eacf6ad5` | coklu_test | 1h | `49cb00e1` | 2026-09-11 | dirty | **tekrar_edilemez** |  | `` |
| `b6378ff98465-06b686dfdd86` | coklu_test | 1h | `49cb00e1` | 2026-09-11 | dirty | **tekrar_edilemez** |  | `` |
| `058f6de87165-34065b334590` | degerlendirme | 1h | `c32b5bd0` | 2026-09-11 | dirty | **veri_geri_getirilemedi** |  | `` |
| `058f6de87165-b0fd228f2e1d` | degerlendirme | 1h | `c32b5bd0` | 2026-09-11 | clean | **veri_geri_getirilemedi** |  | `` |
| `379ada5f5439-233847018b31` | degerlendirme | 4h | `c4ed6bcb` | 2026-09-11 | dirty | **semantik** | 51 | `/esikler[0]/gerekce` |
| `51c7651025bb-1d08f48c3790` | degerlendirme | 1h | `e3adb02c` | 2026-09-09 | dirty | **semantik** | 9 | `/esikler[0]/gerekce` |
| `859167154162-7d89241e3c5a` | degerlendirme | 1h | `e3adb02c` | 2026-09-11 | dirty | **semantik** | 89 | `/esikler[0]/gerekce` |
| `c8cbb92bf037-1d08f48c3790` | degerlendirme | 1h | `e3adb02c` | 2026-09-11 | dirty | **semantik** | 9 | `/esikler[0]/gerekce` |
| `eaee87aa275a-1857153416f4` | degerlendirme | 4h | `c4ed6bcb` | 2026-09-11 | dirty | **semantik** | 9 | `/esikler[0]/gerekce` |
| `301e3750d764-530ecf2a72f1` | kapilar_v2 | 1h | `d01cc97b` | 2026-09-16 | dirty | **tekrar_edilemez** |  | `` |
| `301e3750d764-8a4c5807b67e` | kapilar_v2 | 1h | `d01cc97b` | 2026-09-16 | dirty | **tekrar_edilemez** |  | `` |
| `5746a0b6a975-2a4c9fa4ed85` | karsilastirma | 4h | `c4ed6bcb` | 2026-09-11 | dirty | **semantik** | 96 | `/kiyas/in_sample/cvar_95 (yalnız yenide)` |
| `7a7d259afabe-5931303d7568` | karsilastirma | 1d | `fa957f26` | 2026-09-11 | dirty | **semantik** | 63 | `/kiyas/in_sample/cvar_95 (yalnız yenide)` |
| `96889713358a-2e4779e46858` | karsilastirma | 1h | `e3adb02c` | 2026-09-09 | dirty | **semantik** | 158 | `/kiyas/in_sample/azami_maruziyet` |
| `96889713358a-5a31c2ac9746` | karsilastirma | 1h | `e3adb02c` | 2026-09-09 | dirty | **semantik** | 84 | `/kiyas/gecerli_aday` |
| `96889713358a-5e62e0b9b6cf` | karsilastirma | 1h | `e3adb02c` | 2026-09-09 | dirty | **semantik** | 96 | `/kiyas/in_sample/cvar_95 (yalnız yenide)` |
| `53c71be5cc56-9314ed8ee8fd` | monte_carlo | 1h | `e3adb02c` | 2026-09-09 | dirty | **ayni** |  | `` |
| `e8270eb6d6e4-249d47f444dd` | stres | 1h | `e3adb02c` | 2026-09-09 | dirty | **ayni** |  | `` |
| `4353f031df00-58bceaed0fe1` | tarama | 1h | `e3adb02c` | 2026-09-09 | dirty | **yalniz_sonuc_hash** | 13 | `/adaylar[0]/sonuc_hash` |
| `802362abdc52-229714edcb35` | tarama | 1h | `c32b5bd0` | 2026-09-11 | dirty | **veri_geri_getirilemedi** |  | `` |
| `895715401b5b-87dd71bee16b` | tarama | 1h | `e3adb02c` | 2026-09-11 | dirty | **yalniz_sonuc_hash** | 37 | `/adaylar[0]/sonuc_hash` |
| `dc8a5bb9c54e-9e30cb6824a9` | tarama | 4h | `c4ed6bcb` | 2026-09-11 | dirty | **yalniz_sonuc_hash** | 16 | `/adaylar[0]/sonuc_hash` |

## Sınır

- `semantik` sınıfı **kod sürümü** sorunudur; K-080 bunu çözmez ve çözmeyi vaat etmez. Tam
  çözüm kaydın commit'inde (temiz ağaçta) koşmaktır; bu kayıtların commit'i DIRTY olduğu için
  o da mümkün değil. Ders: deney kaydı kirli ağaçta **üretilmemeli** (W8 D15) — R1'in kalan
  kalemi olarak not.
- Bu tablo `runs/` (git dışı) verisinden; kanıt bu dokümandır.
