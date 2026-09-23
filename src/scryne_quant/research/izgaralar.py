"""Strateji başına varsayılan tarama ızgaraları. (Faz 4)

Izgaralar **stratejilerin içinde değil burada** duruyor: `strategy/` paketi araştırma
katmanını tanımaz (K-003'ün ruhu), ve bir ızgara stratejinin tanımı değil, ona sorulan
sorunun tanımıdır.

**Izgaralar bilerek küçük.** 1.000 kombinasyon denemek, gürültünün en şanslı örneğini
"en iyi parametre" diye sunmanın en kestirme yolu. Her ızgara 24-48 nokta: parametre
duyarlılığını (plato mu tepe mi) görmeye yetecek kadar geniş, bulunanı ciddiye almayı
zorlaştıracak kadar dar. §16.2'nin overfitting uyarısı tam olarak bunu söylüyor.

**Maruziyet ızgaraya girmiyor.** Pozisyon büyüklüğü risk motorunun kararıdır (Faz 5);
burada sabit tutulmazsa tarama, "daha çok risk al" cevabını her zaman bulur — çünkü
yükselen bir varlıkta maruziyeti artırmak Sharpe'ı değil ama getiriyi her koşulda büyütür.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

#: Tüm ızgaralarda sabit tutulan hedef maruziyet. Bkz. modül docstring'i.
SABIT_MARUZIYET: Final = 0.2

IZGARALAR: Final[dict[str, dict[str, Sequence[Any]]]] = {
    # Kıyas ölçütünün ızgarası tek noktalı: al-tut'ta optimize edilecek bir şey yok,
    # ve olmaması gerekiyor — kıyas sabit bir çizgi olmalı, ayarlanan bir rakip değil.
    "al_tut": {"maruziyet": (SABIT_MARUZIYET,)},
    "sma_kesisim": {
        "hizli": (10, 20, 30, 50),
        "yavas": (50, 100, 150, 200),
        "maruziyet": (SABIT_MARUZIYET,),
    },
    "ema_kesisim": {
        "hizli": (10, 20, 30, 50),
        "yavas": (50, 100, 150, 200),
        "maruziyet": (SABIT_MARUZIYET,),
    },
    "rsi_donus": {
        "pencere": (7, 14, 21),
        "alt": (20.0, 25.0, 30.0, 35.0),
        "ust": (60.0, 70.0, 80.0),
        "maruziyet": (SABIT_MARUZIYET,),
    },
    "donchian": {
        "giris": (20, 40, 55, 80),
        "cikis": (10, 20, 40),
        "maruziyet": (SABIT_MARUZIYET,),
    },
    "momentum": {
        "pencere": (12, 24, 48, 96),
        "giris_esigi": (1.0, 2.0, 4.0),
        "cikis_esigi": (-1.0, -2.0, -4.0),
        "maruziyet": (SABIT_MARUZIYET,),
    },
    # --- Faz 4'e dönüş 3: kalabalıklaşma ailesi (K-042) ---------------------
    # Eşikler **persentil**, mutlak değil: funding'in medyanı kalıcı pozitif, mutlak bir
    # eşik neredeyse hep doğru olur ve hiçbir şey ayırt etmez (K-042/3).
    # Pencereler 1h barda: 120 = 5 gün, 240 = 10 gün, 480 = 20 gün.
    "funding_ters": {
        "pencere": (120, 240, 480),
        "giris_p": (0.05, 0.10, 0.20),
        "cikis_p": (0.80, 0.90, 0.95),
        "maruziyet": (SABIT_MARUZIYET,),
    },
    # Kanal parametreleri `donchian`ın ızgarasından **daraltıldı** (55/20 ve 40/20):
    # ölçülen fark tek bir şeye — funding filtresine — atfedilebilmeli. Kanalı da
    # taramak, iki değişkeni aynı anda oynatmak ve hangisinin işe yaradığını
    # bilememek olurdu.
    "funding_filtre": {
        "giris": (40, 55),
        "cikis": (20,),
        "funding_pencere": (120, 240, 480),
        "azami_p": (0.60, 0.70, 0.80, 0.90),
        "maruziyet": (SABIT_MARUZIYET,),
    },
    "funding_egilim": {
        "birikim": (24, 72, 168),
        "pencere": (240, 480),
        "giris_p": (0.10, 0.20),
        "cikis_p": (0.80, 0.90),
        "maruziyet": (SABIT_MARUZIYET,),
    },
    "cok_faktor": {
        "trend_pencere": (50, 100, 200),
        "roc_pencere": (12, 24, 48),
        "hacim_pencere": (20,),
        "giris_oyu": (2, 3),
        "cikis_oyu": (1, 2),
        "maruziyet": (SABIT_MARUZIYET,),
    },
}


class IzgaraYok(KeyError):
    """Bu strateji için tanımlı ızgara yok."""


def izgara(strateji_adi: str) -> Mapping[str, Sequence[Any]]:
    """Bir stratejinin varsayılan ızgarası."""
    try:
        return IZGARALAR[strateji_adi]
    except KeyError:
        raise IzgaraYok(
            f"{strateji_adi!r} için ızgara tanımlı değil; tanımlı: {', '.join(sorted(IZGARALAR))}"
        ) from None


def boyut(strateji_adi: str) -> int:
    """Izgaradaki ham kombinasyon sayısı (stratejinin reddedecekleri dahil)."""
    n = 1
    for degerler in izgara(strateji_adi).values():
        n *= len(degerler)
    return n


# --------------------------------------------------------------------- Faz 12: evren

#: Çok enstrümanlı çekilişler: çekiliş adı → (strateji adı, ızgara). (Faz 12, K-051)
#:
#: Tek sembollü `IZGARALAR` strateji adıyla anahtarlanıyor çünkü orada strateji başına tek
#: ızgara vardı. Programlarda aynı aile birden çok çekiliş veriyor (haftalık / aylık
#: yeniden dengeleme); her biri ayrı bir ızgara, dolayısıyla ayrı bir hipotez kimliği.
#:
#: **Hepsi 12 noktalı** (4 pencere × 3 yoğunluk): K-058'in sıkı `pbo` eşiği 12 noktalı
#: donchian ızgarasında ölçüldü; aynı boyutta kalmak "yeni ızgara biçimi" farkını
#: küçültür ama kapatmaz — çok enstrümanlı null ölçülmedi (Faz 12 raporu, açık kalem).
#: `yeniden_dengele_bar` ve `hedef_brut` tek değerli: ekseni değil, çekilişin kimliği.
#: Pencereler 1h barda: 24 = 1 gün, 168 = 1 hafta, 720 = 30 gün, 1440 = 60 gün.
_YOGUNLUK: Final = (5, 10, 20)
_ORTA_VADE: Final = (168, 336, 720, 1440)
_KISA_VADE: Final = (24, 72, 168, 336)
HAFTALIK: Final = 168
AYLIK: Final = 720


def _evren(pencere: Sequence[int], dengeleme: int) -> dict[str, Sequence[Any]]:
    return {
        "pencere": tuple(pencere),
        "azami_enstruman": _YOGUNLUK,
        "yeniden_dengele_bar": (dengeleme,),
        "hedef_brut": (SABIT_MARUZIYET,),
    }


#: Sıra durma kuralının sırasıdır: ilk dört çekiliş ilk iki ailenin (güç, ters dönüş).
EVREN_CEKILISLERI: Final[dict[str, tuple[str, dict[str, Sequence[Any]]]]] = {
    "kesitsel_guc_haftalik": ("kesitsel_guc", _evren(_ORTA_VADE, HAFTALIK)),
    "kesitsel_guc_aylik": ("kesitsel_guc", _evren(_ORTA_VADE, AYLIK)),
    "kesitsel_ters_haftalik": ("kesitsel_ters", _evren(_KISA_VADE, HAFTALIK)),
    "kesitsel_ters_aylik": ("kesitsel_ters", _evren(_KISA_VADE, AYLIK)),
    "kesitsel_dusuk_oynaklik_haftalik": ("kesitsel_dusuk_oynaklik", _evren(_ORTA_VADE, HAFTALIK)),
    "kesitsel_dusuk_oynaklik_aylik": ("kesitsel_dusuk_oynaklik", _evren(_ORTA_VADE, AYLIK)),
}


_TUREV_PENCERELI: Final[dict[str, Sequence[Any]]] = {
    "pencere": (72, 168, 336, 720),
    "dislama_orani": (0.1, 0.2, 0.3),
    "azami_enstruman": (10,),
    "yeniden_dengele_bar": (HAFTALIK,),
    "hedef_brut": (SABIT_MARUZIYET,),
}

#: `turev_evren` programının çekilişleri (Faz 12). Sıra durma kuralının sırası: önce iki
#: funding çekilişi; ikisi de filtresiz kıyası geçmezse basis çekilişleri harcanmaz.
#: Dengeleme haftalık ve sabit: funding hızlı değişen bir bilgi, aylık dengelemede filtre
#: bayat veriyle karar verirdi. `hedef_brut` kesitsel programla aynı (0,2).
TUREV_CEKILISLERI: Final[dict[str, tuple[str, dict[str, Sequence[Any]]]]] = {
    # Son gerçekleşen oran (8 s eşdeğer): anlık kaldıraç baskısı. İkinci eksen yoğunluk;
    # kıyas seçilen yoğunlukla koşulur, fark yalnızca dışlamadan gelir.
    "turev_funding_kesit": ("evren_funding_kesit", {
        "dislama_orani": (0.1, 0.2, 0.3, 0.5),
        "azami_enstruman": _YOGUNLUK,
        "yeniden_dengele_bar": (HAFTALIK,),
        "hedef_brut": (SABIT_MARUZIYET,),
    }),
    # Son W saatte fiilen ödenen toplam: süregelen baskı (K-042/5'in zaman ölçeği farkı).
    # Yoğunluk kıyasın varsayılanında (10) sabit; eksen birikim penceresi.
    "turev_funding_birikim": ("evren_funding_birikim", _TUREV_PENCERELI),
    # Basis çekilişleri hipotez 43-44 görüldükten **sonra** kaydedildi; sonuca bakılarak
    # seçilmesin diye ızgaraları `turev_funding_birikim`in birebir aynası.
    "turev_basis": ("evren_basis", _TUREV_PENCERELI),
    "turev_funding_basis": ("evren_funding_basis", _TUREV_PENCERELI),
}

#: `makro_rejim` programının çekilişleri (Faz 12). Makro yalnızca **engelleyici** (K-037):
#: stres rejiminde yeni giriş/artış yok. Pencere kümesi `data/makro.PENCERELER_GUN` ile aynı
#: (yükleyicide önceden hesaplanıyor); eşik persentil. İskelet türev programıyla aynı.
#: Sıra durma kuralının sırası: VIX ve NFCI kıyası geçmezse rejim motoru harcanmaz.
_MAKRO: Final[dict[str, Sequence[Any]]] = {
    "pencere_gun": (30, 90, 180, 365),
    "esik": (0.7, 0.8, 0.9),
    "azami_enstruman": (10,),
    "yeniden_dengele_bar": (HAFTALIK,),
    "hedef_brut": (SABIT_MARUZIYET,),
}
MAKRO_CEKILISLERI: Final[dict[str, tuple[str, dict[str, Sequence[Any]]]]] = {
    "makro_vix": ("evren_makro_vix", _MAKRO),
    "makro_nfci": ("evren_makro_nfci", _MAKRO),
}

#: `konumlanma_evren` programının çekilişleri (Faz 16). İskelet türev programıyla birebir
#: aynı: kıyas + tek dışlama, haftalık dengeleme, sabit yoğunluk (10), eksen pencere ve
#: dışlama oranı. Pencere kümesi türev programının aynası — sonuca bakılarak seçilmedi.
#: Sıra durma kuralının sırası: açık pozisyon birikimi ve taker baskısı kıyası geçmezse
#: büyük hesap ve birleşim çekilişleri harcanmaz.
_KONUMLANMA: Final[dict[str, Sequence[Any]]] = {
    "pencere": (24, 72, 168, 720),
    "dislama_orani": (0.1, 0.2, 0.3),
    "azami_enstruman": (10,),
    "yeniden_dengele_bar": (HAFTALIK,),
    "hedef_brut": (SABIT_MARUZIYET,),
}
KONUMLANMA_CEKILISLERI: Final[dict[str, tuple[str, dict[str, Sequence[Any]]]]] = {
    "konumlanma_oi": ("evren_oi_birikim", _KONUMLANMA),
    "konumlanma_taker": ("evren_taker_baski", _KONUMLANMA),
    "konumlanma_buyuk_hesap": ("evren_buyuk_hesap", _KONUMLANMA),
    "konumlanma_oi_taker": ("evren_oi_taker", _KONUMLANMA),
}

#: `kurma_evren` programının çekilişleri (Faz 16, K-051/4). Dışlama yok: kıyasla aynı evren,
#: aynı sıralama, aynı dengeleme takvimi; değişen tek şey `KurmaAyarlari`.
#:
#: Izgaralar 12 noktalı — türev/konumlanma programlarıyla aynı biçim, K-058'in `pbo` eşiği
#: o biçimde kalibre edildi. `yeniden_dengele_bar` ve `hedef_brut` tek değerli olmak
#: **zorunda**: koşucu kıyası bu iki alandan kuruyor (`tools/faz12_evren_kos.py`, `tek`).
#:
#: **"Kapalı" konum ızgarada yok.** `azami_agirlik_carpani = 1` ve `turnover_bandi = 0`
#: kıyasın kendisidir (testle: bit düzeyinde aynı). Izgaraya konsaydı tarama en iyi nokta
#: olarak kıyası seçebilir, çekiliş de kendi kıyasını geçip geçmediğini soramaz olurdu.
#:
#: Sıra durma kuralının sırası: bu iki çekiliş kıyası geçmezse korelasyon budaması ve
#: tavan çekilişleri harcanmaz.
KURMA_CEKILISLERI: Final[dict[str, tuple[str, dict[str, Sequence[Any]]]]] = {
    # Çarpan = en büyük pozisyonun eşit paya oranı. 10,0 fiilen tavansız (1/σ payları
    # crypto kesitinde eşit payın ~2-3 katını geçmiyor); 1,25 sıkı bir kırpma.
    "kurma_oynaklik": ("evren_oynaklik_agirlik", {
        "azami_agirlik_carpani": (1.25, 1.5, 2.0, 10.0),
        "azami_enstruman": _YOGUNLUK,
        "yeniden_dengele_bar": (HAFTALIK,),
        "hedef_brut": (SABIT_MARUZIYET,),
    }),
    # Bant ağırlık birimindedir. 10 isimde eşit pay 0,02; 0,02'lik bant dengelemeyi fiilen
    # yalnızca giriş-çıkışlara indirger, 0,0025 eşit payın sekizde biri.
    "kurma_turnover": ("evren_turnover_bandi", {
        "turnover_bandi": (0.0025, 0.005, 0.01, 0.02),
        "azami_enstruman": _YOGUNLUK,
        "yeniden_dengele_bar": (HAFTALIK,),
        "hedef_brut": (SABIT_MARUZIYET,),
    }),
}

#: `portfoy_kurma` programının çekilişleri (R7, K-108). İskelet `kurma_evren` (Faz 16) ile birebir:
#: kıyasın seçimi/sıralaması/takvimi, 12 nokta (4 × yoğunluk 3), haftalık, brüt 0,2; **kapalı konum
#: ızgarada yok** (tavan 1,0 ve hedef ∞ kıyasın kendisi).
#:
#: - Korelasyon tavanı {0,5; 0,6; 0,7; 0,8}: 0,5 kripto kesitinde (BTC betası yüksek, çiftler arası
#:   ρ tipik 0,5-0,8) yoğun budama, 0,8 seyrek; pencere 720 sabit (kıyasın hacim ufku, eksen değil).
#: - Oynaklık hedefi {0,010; 0,0125; 0,015; 0,020} (1h `atr14/close`, evren medyanı): **ölçülen
#:   dağılımdan**, getiri okunmadan (`runs/faz12/portfoy-kaynak-olcumu.json`, IS haftalık: q10 0,0099,
#:   q25 0,0123, q50 0,0165, q75 0,0205, q90 0,0266) — 0,010 haftaların ~%90'ında düşürür, 0,020 ~%25.
#:   Hedef yalnız düşürür (K-050); 0,2 üstüne çıkaran nokta yok.
#: Sıra durma kuralının sırası: korelasyon budaması, sonra oynaklık hedefi.
PORTFOY_CEKILISLERI: Final[dict[str, tuple[str, dict[str, Sequence[Any]]]]] = {
    "portfoy_korelasyon": ("evren_korelasyon_budama", {
        "korelasyon_tavani": (0.5, 0.6, 0.7, 0.8),
        "pencere": (720,),
        "azami_enstruman": _YOGUNLUK,
        "yeniden_dengele_bar": (HAFTALIK,),
        "hedef_brut": (SABIT_MARUZIYET,),
    }),
    "portfoy_oynaklik_hedefi": ("evren_oynaklik_hedefi", {
        "hedef_oynaklik": (0.010, 0.0125, 0.015, 0.020),
        "azami_enstruman": _YOGUNLUK,
        "yeniden_dengele_bar": (HAFTALIK,),
        "hedef_brut": (SABIT_MARUZIYET,),
    }),
}

#: `kesit_oynaklik` programının çekilişleri (R7(2), K-109). Faz 12'nin `kesitsel_dusuk_oynaklik`
#: çekilişleri (`EVREN_CEKILISLERI`) hiç harcanmadı (program 4/4'te güç ve ters ile kapandı, K-068).
#: K-068 ek şartı ölçüldü (`tools/r7_sinyal_gucu.py`, yalnız IS): `−atr(p)/close` ↔ 168 bar ileri
#: getiri Spearman IC ≈ +0,14, t 6-7,6, IS'in iki yarısında aynı işaret — ölçülen 11 sinyalden K-068
#: ölçütünü (|t| ≥ 2 ∧ aynı işaret) yalnız bu sağladı. Izgara Faz 12 tanımının **aynısı** (pencere
#: {168,336,720,1440} × yoğunluk {5,10,20}); yeni eksen yok. Sıra: haftalık; aylık yalnız haftalık
#: OOS'ta kıyası geçerse (takvim tekrarı), aksi hâlde harcanmaz.
KESIT_OYNAKLIK_CEKILISLERI: Final[dict[str, tuple[str, dict[str, Sequence[Any]]]]] = {
    "r7_dusuk_oynaklik_haftalik": ("kesitsel_dusuk_oynaklik", _evren(_ORTA_VADE, HAFTALIK)),
    "r7_dusuk_oynaklik_aylik": ("kesitsel_dusuk_oynaklik", _evren(_ORTA_VADE, AYLIK)),
}

#: `kripto_zs_trend` programının çekilişleri (K-120): kripto PIT evreninde **zaman serisi**
#: (mutlak) trend — üye kendi `pencere` barlık getirisi pozitifse taşınır, yükselen yoksa portföy
#: nakde döner. Kesitsel momentumdan (h39-h42, sıralama) farkı piyasa zamanlaması. Pencereler
#: 14/30/60/90 gün (2160 = 90 gün, Liu-Tsyvinski'nin 1-4 haftalık + klasik 3 aylık TSMOM ufku);
#: yoğunluk Faz 12'nin (5, 10, 20). 12 nokta (4 × 3), K-119 kapılarının doğrulandığı biçim.
_ZS_PENCERE: Final = (336, 720, 1440, 2160)
ZS_TREND_CEKILISLERI: Final[dict[str, tuple[str, dict[str, Sequence[Any]]]]] = {
    "zs_trend_haftalik": ("zaman_serisi_trend", _evren(_ZS_PENCERE, HAFTALIK)),
    "zs_trend_aylik": ("zaman_serisi_trend", _evren(_ZS_PENCERE, AYLIK)),
}

#: `fx_fiyat` programının çekilişleri (R5, K-102): ilk FX alfa araştırması, üç aile, üç çekiliş.
#:
#: Pencereler **FX seans barında** (1h, 5x24 → 120 bar = 1 hafta, K-099): 24 = 1 gün, 48 = 2 gün,
#: 120 = 1 hafta, 240 = 2 hafta. Kripto ızgarasının 720/1440'ı burada **sığmaz**: K-101'in geçerli
#: finansman penceresi 2023-11-19..2024-02-29 (1.721 bar); 240 barlık ısınma zaten pencerenin
#: %14'ü. Yoğunluk (3, 5, 10) — evren 21 çift; kriptonun 20'si evrenin tamamı olur ve çekiliş
#: kendi kıyasına dönerdi. Biçim 12 nokta (4 × 3), K-058'in `pbo` eşiğinin ölçüldüğü biçim.
#: `yeniden_dengele_bar` 120 (FX kıyasının haftası, K-099) ve `hedef_brut` 0,2 tek değerli.
#: Sıra durma kuralının sırası: kesitsel güç, kesitsel ters, zaman serisi trend.
_FX_PENCERE: Final = (24, 48, 120, 240)
_FX_YOGUNLUK: Final = (3, 5, 10)
FX_HAFTALIK: Final = 120


def _fx(strateji: str) -> tuple[str, dict[str, Sequence[Any]]]:
    return (strateji, {
        "pencere": _FX_PENCERE,
        "azami_enstruman": _FX_YOGUNLUK,
        "yeniden_dengele_bar": (FX_HAFTALIK,),
        "hedef_brut": (SABIT_MARUZIYET,),
    })


FX_CEKILISLERI: Final[dict[str, tuple[str, dict[str, Sequence[Any]]]]] = {
    "fx_kesitsel_guc": _fx("kesitsel_guc"),
    "fx_kesitsel_ters": _fx("kesitsel_ters"),
    "fx_zaman_serisi_trend": _fx("zaman_serisi_trend"),
}

#: `fx_ortalama_donus` programının çekilişleri (R6, K-104): zaman serisi ortalama dönüş, eşikli.
#: 12 nokta: pencere (3) × eşik (2) × yoğunluk (2). Eşikler önceden sabit ve ikişer: z için 1 ve 2
#: ATR (klasik bant genişlikleri), RSI için 30 (klasik) ve 40 (gevşek; 1h FX'te 30 seyrek tetikler).
#: Yoğunluk {2, 5}: **sinyal setinin büyüklüğünden** (getiri okunmadan) seçildi — W1'de 13
#: dengeleme anında eşiği geçen çift sayısı ortalama 1,4-4,6, haftaların %23-85'i boş
#: (`runs/fx/donus-kaynak-olcumu.json`, program kaydında). 5/10 ekseni hiç bağlamaz ve ızgarada
#: iki özdeş sütun PBO'yu bozardı; 2 çoğu hafta bağlar. Dengeleme 120, brüt 0,2 (kıyas aynı).
FX_DONUS_CEKILISLERI: Final[dict[str, tuple[str, dict[str, Sequence[Any]]]]] = {
    "fx_zaman_serisi_sapma": ("zaman_serisi_sapma", {
        "pencere": (48, 120, 240),
        "esik": (1.0, 2.0),
        "azami_enstruman": (2, 5),
        "yeniden_dengele_bar": (FX_HAFTALIK,),
        "hedef_brut": (SABIT_MARUZIYET,),
    }),
    "fx_zaman_serisi_rsi": ("zaman_serisi_rsi", {
        "pencere": (14, 24, 48),
        "esik": (30.0, 40.0),
        "azami_enstruman": (2, 5),
        "yeniden_dengele_bar": (FX_HAFTALIK,),
        "hedef_brut": (SABIT_MARUZIYET,),
    }),
}

#: `fx_oynaklik` programının çekilişleri (R6, K-105): kıyasın üstüne oynaklık genişlemesi
#: filtresi, elenen pay nakitte. 12 nokta: taban penceresi (3) × eşik (4). Ölçü
#: `atr(14)/atr(pencere)`; ATR 14 eksen değil (kıyas/risk motoru ölçüsü). Pencereler kıyasın
#: haftasının katları: 48 = 2 gün, 120 = 1 hafta, 240 = 2 hafta (24 sığmaz: taban 14'ten uzun
#: olmalı ve ölçüm oranı 1'e çiviliyor). **Eşikler ölçülen dağılımdan** (getiri okunmadan,
#: `runs/fx/oynaklik-kaynak-olcumu.json`): oran üye-haftalarda q10 0,82-0,89, q50 ≈ 1,00, q90
#: 1,11-1,26; 1,25+ hiç ya da nadiren tetikliyor (K-104'teki rsi48<30 gibi ölü sütun olurdu),
#: 0,9-1,2 dağılımın gövdesi. 0,9 "yalnız sıkışmış oynaklık", 1,2 "yalnız belirgin genişleme".
#: Yoğunluk ekseni yok: evrenin tamamı (K-099, kıyas gibi).
#: Sıra durma kuralının sırası: çift başına, sonra evren geneli.
_FX_OYNAKLIK: Final[dict[str, Sequence[Any]]] = {
    "pencere": (48, 120, 240),
    "esik": (0.9, 1.0, 1.1, 1.2),
    "azami_enstruman": (21,),
    "yeniden_dengele_bar": (FX_HAFTALIK,),
    "hedef_brut": (SABIT_MARUZIYET,),
}
FX_OYNAKLIK_CEKILISLERI: Final[dict[str, tuple[str, dict[str, Sequence[Any]]]]] = {
    "fx_oynaklik_filtre_cift": ("fx_oynaklik_filtre_cift", _FX_OYNAKLIK),
    "fx_oynaklik_filtre_evren": ("fx_oynaklik_filtre_evren", _FX_OYNAKLIK),
}

#: Program → çekilişleri. Koşucu çekilişin programını buradan bulur.
PROGRAM_CEKILISLERI: Final[dict[str, tuple[str, ...]]] = {
    "kesitsel_fiyat": tuple(EVREN_CEKILISLERI),
    "turev_evren": tuple(TUREV_CEKILISLERI),
    "makro_rejim": tuple(MAKRO_CEKILISLERI),
    "konumlanma_evren": tuple(KONUMLANMA_CEKILISLERI),
    "kurma_evren": tuple(KURMA_CEKILISLERI),
    "portfoy_kurma": tuple(PORTFOY_CEKILISLERI),
    "kesit_oynaklik": tuple(KESIT_OYNAKLIK_CEKILISLERI),
    "kripto_zs_trend": tuple(ZS_TREND_CEKILISLERI),
    "fx_fiyat": tuple(FX_CEKILISLERI),
    "fx_ortalama_donus": tuple(FX_DONUS_CEKILISLERI),
    "fx_oynaklik": tuple(FX_OYNAKLIK_CEKILISLERI),
}


def _TUM_CEKILISLER() -> dict[str, tuple[str, dict[str, Sequence[Any]]]]:
    """Bütün evren çekilişleri tek sözlükte. Yeni bir program eklenince **tek yer**
    değişsin diye ayrı: iki ayrı birleştirme listesi sessizce ayrışabilirdi."""
    return {**EVREN_CEKILISLERI, **TUREV_CEKILISLERI, **MAKRO_CEKILISLERI,
            **KONUMLANMA_CEKILISLERI, **KURMA_CEKILISLERI, **PORTFOY_CEKILISLERI,
            **KESIT_OYNAKLIK_CEKILISLERI, **ZS_TREND_CEKILISLERI, **FX_CEKILISLERI,
            **FX_DONUS_CEKILISLERI, **FX_OYNAKLIK_CEKILISLERI}


def evren_cekilisi(ad: str) -> tuple[str, Mapping[str, Sequence[Any]]]:
    """Bir evren çekilişinin `(strateji adı, ızgara)` çifti."""
    hepsi = _TUM_CEKILISLER()
    try:
        return hepsi[ad]
    except KeyError:
        raise IzgaraYok(
            f"{ad!r} tanımlı bir evren çekilişi değil; tanımlı: {', '.join(hepsi)}"
        ) from None


def cekilis_programi(ad: str) -> str:
    """Çekilişin ait olduğu araştırma programı."""
    for program, adlar in PROGRAM_CEKILISLERI.items():
        if ad in adlar:
            return program
    raise IzgaraYok(f"{ad!r} hiçbir programın çekilişi değil")


def strateji_izgarasi(strateji_adi: str) -> Mapping[str, Sequence[Any]]:
    """Tek sembollü ya da **evren** stratejisinin ızgarası.

    `izgara` yalnızca tek sembollü defteri biliyor; evren çekilişlerinin ızgarası çekiliş
    adına bağlı (`EVREN_CEKILISLERI` ve kardeşleri). Gizli tekrar kontrolü (K-061) hipotez
    kaydından **önce** koştuğu için ızgarayı strateji adından bulabilmeli.
    """
    try:
        return izgara(strateji_adi)
    except IzgaraYok:
        pass
    hepsi = _TUM_CEKILISLER()
    for _, (ad, g) in hepsi.items():
        if ad == strateji_adi:
            return g
    raise IzgaraYok(
        f"{strateji_adi!r} için ızgara tanımlı değil (tek sembollü ve evren defterlerinde yok)"
    )
