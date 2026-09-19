# Runbook — alarmlar ve müdahale (Faz 14)

`sq izle kontrol` (`live/izleme.py`) hostta 15 dakikada bir koşar (`ScryneQuant-Izleme`).
Etkin alarmlar `runs\izleme\durum.json`, açılan/kapanan değişimler `runs\izleme\alarmlar.jsonl`.
Alarm **yalnızca gözlem**: koşuyu durdurmaz, limit değiştirmez (K-050). Durdurmak gerekiyorsa
elle: `sq paper durdur <kosu> --sebep ...` (planlı, kesinti sayılmaz) ya da `sq kill calistir`.

Eşikler tek yerde: `izleme.ESIKLER`. Her kodun bu tabloda satırı olmak zorunda (testle korunur).

Hosta bağlanmak: `ssh -i ~/.ssh/scrynequant_vps scryn@192.168.1.4`, kod dizini
`%USERPROFILE%\Documents\Projeler\ScryneQuant`. Kayıtlar UTC; TR = UTC+3.

**Bildirim (K-066):** açılan/kapanan alarm ve 09:00 TR günlük özet telefona ntfy.sh ile gelir
(konu hostun `.env`inde, `SQ_NTFY_KONU`). **Özet gelmediyse** host, görev zamanlayıcı ya da ağ
ayakta değildir: önce hostun açık ve ağa bağlı olduğunu kontrol et.

**İki panel var, ikisi de yalnız host içinden açılır.** Ana makineden ağa açmadan görmek için
SSH tüneli (`-f -N` arka plana alır):

| Port | Ne gösterir | Servis eden | Tünel |
| ---: | --- | --- | --- |
| 8787 | **Yalnız `host-1`** (tek sembollü koşu): portföy, fill, risk, İzleme bölümü | koşunun **kendi süreci** (`ScryneQuant-Paper`) | `ssh -f -N -i ~/.ssh/scrynequant_vps -L 8787:127.0.0.1:8787 scryn@192.168.1.4` |
| 8788 | **Bütün koşular**: liste, özkaynak eğrisi, açık pozisyonlar, **işlem defteri**, olaylar, evren üyeliği | ayrı salt okunur süreç (`ScryneQuant-Pano`) | `ssh -f -N -i ~/.ssh/scrynequant_vps -L 8788:127.0.0.1:8788 scryn@192.168.1.4` |

İşlemleri görmek için **8788**'e bakılır: evren koşularının işlemleri 8787'de görünmez, o pano
kendi koşusundan başkasını tanımaz.

**Pano (8788) salt okunurdur** (`live/evren_pano.py`, `tools/pano.py`): koşu dosyalarını anlık
kopyadan okur, yalnızca `GET` uçları vardır ve hiçbir koşuyu değiştiremez — bu yüzden ölçüm
penceresi açıkken de çalıştırılabilir. Pozisyon ve işlem defteri koşunun kaydından **yeniden
üretilir**; iş arka planda koşar, ekranda "Hesaplanıyor" görünür. Süre adım sayısıyla O(N²)
büyüyor (797 adımda ≈8 sn). Pano ölürse koşular etkilenmez: `Start-ScheduledTask ScryneQuant-Pano`.
Kaldırmak: `Unregister-ScheduledTask -TaskName ScryneQuant-Pano -Confirm:$false`.

**Yedek ve geri yükleme:** her gün 05:30 TR `runs\yedek\` (koşu başına son 7). Tatbikat /
gerçek geri yükleme: `sq paper evren-tatbikat <kosu>` en son yedeği boş dizinde yeniden üretir
ve canlıyla karşılaştırır. Gerçek kayıpta: koşuyu durdur, yedeği `runs\paper\<kosu>.sqlite`
olarak kopyala, görevi başlat — açılışta bütün adımlar yeniden üretilir, aradaki saatler REST'ten
tamamlanır.

| Kod | Boyut | Seviye | Anlamı | İlk bakılacak | Müdahale |
| --- | --- | --- | --- | --- | --- |
| `SUREC_YOK` | sistem | kritik | Koşunun pid dosyası yok ya da süreç ölü | `Get-ScheduledTask ScryneQuant-*`; `runs\paper\<kosu>.log` sonu; `sq paper evren-durum <kosu>` olaylarında `hata` | Çökmede görev 1 dk'da yeniden başlatır; başlatmadıysa `Start-ScheduledTask`. Planlı durdurmadan sonra unutulduysa aynı (düzgün kapanan koşuyu görev yeniden başlatmaz). Aynı hata tekrar ediyorsa **başlatma**, sebebi bul (K-038: tahmin yok) |
| `DISK_AZ` | sistem | uyarı <10 GB, kritik <2 GB | Host diski doluyor | `runs\` ve `data\` boyutları; Windows Update önbelleği | Eski `runs\faz*` çıktıları ana makineye taşınır; koşu dosyaları **silinmez** (kanıt) |
| `BELLEK_AZ` | sistem | uyarı | Boş fiziksel bellek <1 GB | Görev Yöneticisi; python süreçleri (evren koşusu ≈200 MB) | Hostta başka yük varsa kapatılır; koşu süreci büyüyorsa ölçülüp not düşülür |
| `SON_BAR_GECIKTI` | veri | kritik | İşlenen son bar, kapanmış son bardan ≥2 saat geride | Süreç yaşıyor mu; log'da `kopma`/`yeniden_baglandi`; internet; Binance durumu | Süreç yaşıyor ama ilerlemiyorsa planlı durdur + başlat: başlangıçta boşluk REST'ten tamamlanır. Tekrarlıyorsa akış kodunda sebep aranır |
| `EKSIK_ADIM` | veri | uyarı | 24 saatte >3 adım eksik sembolle işlendi | `evren-durum` olayları: hangi semboller; `gec_bar` sayısı | Tek sembolse (delist/bakım) not düş. Yaygınsa bekleme süresi ya da akış incelenir; bekleme değişikliği yeni koşu adı ister |
| `KOPMA` | veri | uyarı | 24 saatte >5 WebSocket kopması | Log; host ağ bağlantısı | Koşu kendi yeniden bağlanır; sürekli ise kablo/modem |
| `UYELIK_GECIKMESI` | veri | uyarı | Ayın 3. gününden sonra hâlâ yeni ayın evren listesi yok | `runs\paper\<kosu>.yenileme.log`; `ScryneQuant-EvrenTablo` son sonucu (çıkış 3 = M−1 verisi eksik) | Elle: `tools\evren-tablo-yenile.ps1`. Arşiv gecikmişse beklenir; bu günler sapma raporunda görünür |
| `TABLO_YENILEME_HATASI` | veri | kritik | Yenileme **yazmayı reddetti** (geçmiş ay değişti / kural uyuşmuyor) | Yenileme log'undaki mesaj | **Tablo elle düzeltilmez.** Ana makinede aynı tablo üretilip hash karşılaştırılır; sebep bulunana kadar koşu önceki ayla devam eder |
| `SAFE_MODE` | trading | kritik | Koşu SAFE_MODE'da (kill ya da risk) | `sq kill durum <kosu>`; risk audit'i | Sebep anlaşılmadan kaldırılmaz: `sq kill kaldir` (K-050: izni artıran elle) |
| `DUSUS` | trading | uyarı ≥%5, kritik ≥%10 | Özkaynak zirvesinden düşüş | Pozisyonlar, piyasa; aynı dönemin backtest beklentisi | Gözlem koşusunda müdahale yok, kayda geçer. Gerçek sermayede risk limitleri devrede (Faz 8) |
| `BRUT_ASIMI` | trading | uyarı | Brüt maruziyet hedefin 1,5 katını aştı | `evren-durum` pozisyonlar; fiyat hareketi | Yeniden dengelemeye kadar kayma normal olabilir; kalıcıysa kurma kodunda hata aranır |
| `KOSU_HATASI` | trading | kritik | Son 24 saatte koşu `hata` olayı yazdı | Olay ayrıntısı; `EvrenToparlanmaAyrismasi` ise toparlanma kayıtla uyuşmadı | Ayrışmada koşu **durur, tahmin yürütülmez** (K-038): dosya ana makineye kopyalanıp yeniden üretilir, ayrışan adım incelenir |
| `SAPMA` | model | uyarı | Canlı-referans özkaynak farkı >50 bps (sebebi kayıtlı) | `runs\paper\<kosu>.sapma.jsonl` son satır: geç bar / eksik adım / üyelik gecikmesi | Olaylarla açıklanıyorsa not düş; büyüyorsa bekleme süresi/akış incelenir |
| `SEBEPSIZ_SAPMA` | model | kritik | Canlı referanstan ayrıştı ama geç bar, eksik adım, üyelik gecikmesi, geç türev girdisi, makro revizyonu **yok** | Sapma raporu `ilk_ayrisan_utc`; o adımın girdileri | Tek kod yolu (K-001) bozulmuş olabilir: dosya ana makinede `sq paper evren-sapma` ile yeniden ölçülür, ayrışan adım bar bar karşılaştırılır. Bulunana kadar koşunun sonuçları kanıt sayılmaz |
| `SAPMA_OLCUMU_YOK` | model | uyarı | Son sapma ölçümü 36 saatten eski | `ScryneQuant-EvrenSapma` son çalışma; `runs\paper\<kosu>.sapma.log` | Elle: `tools\evren-sapma.ps1` |

## Jev gölge koşusu (K-074) — ayrı süreç, emir yok

`sq jev golge --kosu golge-<tarih>` kapanmış her `ok` 1h barda kanonik durum kurar, Jev'e sorar,
`runs\jev\<kosu>.sqlite`'a yazar (zincir hash'li, append-only). Paper/live süreçlerine
dokunmaz; ölürse onlar etkilenmez, tersi de. Kilit dosyası aynı koşuya ikinci süreci engeller.

| İş | Komut |
| --- | --- |
| Kurulumu ağa çıkarak doğrula, koşma | `sq jev golge --kosu <kosu> --kuru` |
| Başlat (arka plan) | `Start-Process uv -ArgumentList "run sq jev golge --kosu <kosu>" -RedirectStandardOutput runs\jev\<kosu>.log` |
| Düzgün durdur (≤30 s içinde durur) | `sq jev durdur --kosu <kosu> --sebep "..."` |
| Durum: sayım, zincir, son kararlar/olaylar | `sq jev durum --kosu <kosu>` |
| Değerlendirme (ileri sonuç, isabet, kalibrasyon) | `sq jev degerlendir --kosu <kosu> --rest` |
| Tarihsel replay (kanıt değil, `leak_riski`) | `sq jev tekrar --kosu tekrar-<ad> --son-n-bar N [--kuru]` |
| Dondur (Parquet + manifest) | `sq jev dondur --kosu <kosu>` |

**Hata = karar yok.** Timeout, API/kimlik hatası, şema hatası, model uyuşmazlığı, bayat üretim
defterde `durum_kodu ≠ gecerli` satırı olarak görünür; yön alanı boştur, önceki karar
taşınmaz. `sq jev durum` çıktısındaki `sayim`de `gecerli` dışı bir kod artıyorsa: önce
`TYPESAFE_API_KEY` ortamda mı (`kimlik_hatasi`), sonra `runs\jev\<kosu>.log`. `model_uyumsuz`
ise TypeSafe sürümü değişmiştir: koşu **yeni koşu** olarak açılır, eski defter kapanır
(K-074/6). `zincir_gecerli: false` ise dosya kurcalanmıştır; koşu durdurulur, dosya incelenir.

Anahtar yalnızca ortam değişkeninde; defterde, logda, durumda sır aranır ve bulunursa istek
gönderilmez (`istemci.sir_var_mi`).
