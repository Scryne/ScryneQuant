# Runbook — alarmlar ve müdahale (Faz 14)

`sq izle kontrol` (`live/izleme.py`) hostta 15 dakikada bir koşar (`ScryneQuant-Izleme`).
Etkin alarmlar `runs\izleme\durum.json`, açılan/kapanan değişimler `runs\izleme\alarmlar.jsonl`.
Alarm **yalnızca gözlem**: koşuyu durdurmaz, limit değiştirmez (K-050). Durdurmak gerekiyorsa
elle: `sq paper durdur <kosu> --sebep ...` (planlı, kesinti sayılmaz) ya da `sq kill calistir`.

Eşikler tek yerde: `izleme.ESIKLER`. Her kodun bu tabloda satırı olmak zorunda (testle korunur).

Hosta bağlanmak: `ssh -i ~/.ssh/scrynequant_vps scryn@192.168.1.4`, kod dizini
`%USERPROFILE%\Documents\Projeler\ScryneQuant`. Kayıtlar UTC; TR = UTC+3.

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
| `SEBEPSIZ_SAPMA` | model | kritik | Canlı referanstan ayrıştı ama geç bar, eksik adım, üyelik gecikmesi **yok** | Sapma raporu `ilk_ayrisan_utc`; o adımın girdileri | Tek kod yolu (K-001) bozulmuş olabilir: dosya ana makinede `sq paper evren-sapma` ile yeniden ölçülür, ayrışan adım bar bar karşılaştırılır. Bulunana kadar koşunun sonuçları kanıt sayılmaz |
| `SAPMA_OLCUMU_YOK` | model | uyarı | Son sapma ölçümü 36 saatten eski | `ScryneQuant-EvrenSapma` son çalışma; `runs\paper\<kosu>.sapma.log` | Elle: `tools\evren-sapma.ps1` |
