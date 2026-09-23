"""Risk Yönetimli Promotion Protokolü (RYPP): düşüşü anlamlı azaltırken getiriyi koruyor mu? (K-125)

Yeni hedefin (K-125) promotion ölçütü. Alfa yolunun 12 kapısının (K-119) yerini **almaz**, yanına
ayrı bir yol olarak eklenir; alfa yolu aynen durur. Soru: *önceden tanımlanmış bir kıyasa göre
azami düşüşü anlamlı azaltıp kabul edilebilir getiriyi koruyan bir strateji, bunu şansla değil
zamanlamayla mı yapıyor ve sonuç tek bir olaya, başlangıç tarihine ya da maliyet varsayımına bağlı
mı?*

## Neden ayrı bir protokol

"Düşüş %50 azaldı" tek başına kanıt değildir: ortalama maruziyeti yarıya indiren **her** strateji
düşüşü kabaca yarıya indirir, getiriyi de yarıya indirir. Üstelik kripto evreninin OOS penceresine
18 çekiliş baktı ve penceredeki 2025-26 düşüşü biliniyor (K-125/B-3): "düşüşte nakde geç" diye
tasarlanan her şey o pencerede kendiliğinden iyi görünür. Bu yüzden asıl kapı **plasebo**dur:
stratejinin kendi maruziyet takvimi zamanda dairesel kaydırılır — işlem sayısı, tutma süreleri,
ortalama maruziyet, maliyet yapısı, evren ve dönem aynen kalır, yalnız zamanlama rastgeleleşir.
Strateji, plasebonun (1 − α/k) persentilini getiri/düşüş verimliliğinde (MAR) geçmek zorundadır.

## Karar mantığı (sıra önemlidir)

1. **Veri yeterliliği** (hiçbiri yoksa INCONCLUSIVE): OOS ≥ `ASGARI_OOS_YIL`; kıyasta en az
   `ASGARI_EPIZOT` ayrı düşüş epizodu (derinlik ≥ `epizot_esigi`); ≥ `ASGARI_PLASEBO` plasebo; stres
   (2x maliyet) koşusu verilmiş.
2. **Nokta koşulları** (biri kalırsa FAIL): P1 düşüş azaltımı, P2 getiri korunumu ve verimlilik,
   P3 plasebo, S1 maliyet stresi, R1 başlangıç tarihi duyarlılığı, R2 alt dönemler, R3 tek olay.
3. **Belirsizlik** (nokta koşulları geçti ama blok bootstrap güven aralığı karara yetmiyorsa
   INCONCLUSIVE): düşüş azaltımının %90 GA alt sınırı > 0 ve
   P(MAR_S > MAR_K) ≥ `ASGARI_BOOTSTRAP_P`.
4. Hepsi → PASS.

INCONCLUSIVE'de eşik gevşetilmez: daha fazla veri gerekir.

## Eşiklerin statüsü

Hepsi **tasarım kararı** (K-125, sonuca bakılmadan yazıldı), ölçülmüş değil; `ESIKLER` her birinin
gerekçesini taşır. Plasebo persentili ölçüm değil kalibrasyondur: yanlış pozitif oranını tanım
gereği α/k'ye bağlar (aile içi Bonferroni; K-039 küresel sayım ayrıca sürer).

## Ne ölçmez

Canlı uygulanabilirliği (K-122 ayrı), kapasiteyi, vergi etkisini. Nakit getirisi 0 sayılır (motorla
aynı; tutucu yön: nakitte bekleyen strateji aleyhine).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final

import numpy as np

# ------------------------------------------------------------------ eşikler (tasarım kararları)

#: OOS en az 2 yıl: tek bir boğa/ayı döngüsünün yarısından kısa pencerede düşüş azaltımı ölçülemez.
ASGARI_OOS_YIL: Final = 2.0
#: Kıyasta en az iki ayrı düşüş epizodu: tek epizotla "risk yönetimi" ile "bir kez şanslı çıkış"
#: ayırt edilemez.
ASGARI_EPIZOT: Final = 2
#: P1: kıyasın azami düşüşünün en az dörtte biri önlenmeli ("anlamlı" tanımı).
ASGARI_DD_AZALTIM: Final = 0.25
#: P2a: kıyas pozitif getirdiyse stratejinin yıllık getirisi en az yarısı kadar olmalı.
ASGARI_GETIRI_KORUMA: Final = 0.5
#: P3: plasebo persentili 1 − α/k; α aile başına %5 (K-044 ile aynı hedef).
ALFA: Final = 0.05
ASGARI_PLASEBO: Final = 100
#: R1: başlangıç tarihlerinin en az %70'inde P1 ve P2b tutmalı.
ASGARI_BASLANGIC_ORANI: Final = 0.70
#: R3: epizot başına iyileşme: stratejinin epizot içi düşüşü kıyasınkinin ≤ %90'ı; en az iki
#: epizotta sağlanmalı (tek olay baskınlığı).
EPIZOT_IYILESME: Final = 0.90
#: Bootstrap: düşüş azaltımının %90 GA alt sınırı > 0 ve MAR üstünlüğü olasılığı ≥ 0,80.
ASGARI_BOOTSTRAP_P: Final = 0.80
BOOTSTRAP_ORNEK: Final = 1_000

ESIKLER: Final[dict[str, dict[str, Any]]] = {
    "asgari_oos_yil": {"deger": ASGARI_OOS_YIL, "kaynak": "tasarim",
                       "gerekce": "düşüş azaltımı yarım döngüden kısa pencerede ölçülemez"},
    "asgari_epizot": {"deger": ASGARI_EPIZOT, "kaynak": "tasarim",
                      "gerekce": "tek epizot: şanslı tek çıkış ile risk yönetimi ayırt edilemez"},
    "asgari_dd_azaltim": {"deger": ASGARI_DD_AZALTIM, "kaynak": "tasarim",
                          "gerekce": "anlamlı = kıyas düşüşünün en az dörtte biri önlenir"},
    "asgari_getiri_koruma": {"deger": ASGARI_GETIRI_KORUMA, "kaynak": "tasarim",
                             "gerekce": "kıyas getirisinin en az yarısı korunur"},
    "alfa": {"deger": ALFA, "kaynak": "kalibrasyon",
             "gerekce": "plasebo persentili yanlış pozitifi tanım gereği α/k'ye bağlar"},
    "asgari_baslangic_orani": {"deger": ASGARI_BASLANGIC_ORANI, "kaynak": "tasarim",
                               "gerekce": "sonuç başlangıç tarihine bağlı olmamalı"},
    "epizot_iyilesme": {"deger": EPIZOT_IYILESME, "kaynak": "tasarim",
                        "gerekce": "en az iki ayrı epizotta düşüş kıyasınkinin ≤ %90'ı"},
    "asgari_bootstrap_p": {"deger": ASGARI_BOOTSTRAP_P, "kaynak": "tasarim",
                           "gerekce": "MAR üstünlüğü blok bootstrap'ta ≥ %80 olasılıkla"},
}


class Durum(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


class ProtokolHatasi(ValueError):
    """Girdi sözleşmesi ihlali (hizasız seriler, NaN) — sessiz düzeltme yok."""


# ------------------------------------------------------------------ ölçüler


@dataclass(frozen=True, slots=True)
class SeriOlcumu:
    toplam_getiri: float
    cagr: float
    mdd: float
    mar: float
    """CAGR / azami düşüş (düşüş 0 ise ve CAGR > 0 ise +inf yerine büyük sayı değil: `nan`)."""
    sharpe: float
    sortino: float
    """**Standart** Sortino: aşağı yönlü sapma tüm gözlemler üzerinden (Sortino & Price).
    `backtest.metrikler.Metrikler.sortino` yalnız negatif gözlemlerle bölüyor (K-125/B-1)."""
    yillik_vol: float
    en_uzun_dusus_bar: int

    def sozluk(self) -> dict[str, float]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def _getiriler(ozkaynak: np.ndarray) -> np.ndarray:
    return np.diff(ozkaynak) / ozkaynak[:-1]


def azami_dusus(ozkaynak: np.ndarray) -> tuple[float, int]:
    """Azami düşüş (kesir) ve zirveden yeni zirveye en uzun süre (bar)."""
    zirve = np.maximum.accumulate(ozkaynak)
    dd = 1.0 - ozkaynak / zirve
    en_uzun = suren = 0
    for i in range(ozkaynak.size):
        suren = 0 if ozkaynak[i] >= zirve[i] else suren + 1
        en_uzun = max(en_uzun, suren)
    return float(dd.max()), int(en_uzun)


def sortino_standart(getiriler: np.ndarray, yil_bar: float) -> float:
    """Aşağı yönlü sapma = √(ortalama(min(r, 0)²)) **tüm** gözlemler üzerinden."""
    asagi = math.sqrt(float(np.mean(np.minimum(getiriler, 0.0) ** 2)))
    return float(np.mean(getiriler)) / asagi * math.sqrt(yil_bar) if asagi > 0 else float("nan")


def olc(ozkaynak: np.ndarray, yil_bar: float) -> SeriOlcumu:
    oz = _dogrula_seri(ozkaynak, "ozkaynak")
    g = _getiriler(oz)
    yil = g.size / yil_bar
    son = oz[-1] / oz[0]
    cagr = son ** (1.0 / yil) - 1.0 if son > 0 and yil > 0 else -1.0
    mdd, uzun = azami_dusus(oz)
    sd = float(np.std(g, ddof=1)) if g.size > 1 else 0.0
    return SeriOlcumu(
        toplam_getiri=float(son - 1.0), cagr=float(cagr), mdd=mdd,
        mar=float(cagr / mdd) if mdd > 0 else float("nan"),
        sharpe=float(np.mean(g) / sd * math.sqrt(yil_bar)) if sd > 0 else float("nan"),
        sortino=sortino_standart(g, yil_bar), yillik_vol=sd * math.sqrt(yil_bar),
        en_uzun_dusus_bar=uzun,
    )


def dusus_epizotlari(ozkaynak: np.ndarray, esik: float) -> list[tuple[int, int, int, float]]:
    """Derinliği ≥ `esik` olan ayrı düşüş epizotları: `(zirve, dip, bitiş, derinlik)`.

    Epizot zirveden başlar, yeni zirvede (ya da seri sonunda) biter; derinlik epizot içindeki
    azami düşüştür.
    """
    oz = _dogrula_seri(ozkaynak, "ozkaynak")
    out: list[tuple[int, int, int, float]] = []
    zirve_i = 0
    dip_i = 0
    derin = 0.0
    for i in range(1, oz.size):
        if oz[i] >= oz[zirve_i]:
            if derin >= esik:
                out.append((zirve_i, dip_i, i, derin))
            zirve_i, dip_i, derin = i, i, 0.0
        else:
            d = 1.0 - oz[i] / oz[zirve_i]
            if d > derin:
                derin, dip_i = d, i
    if derin >= esik:
        out.append((zirve_i, dip_i, oz.size - 1, derin))
    return out


def _dogrula_seri(x: Any, ad: str) -> np.ndarray:
    a = np.asarray(x, dtype=np.float64)
    if a.ndim != 1 or a.size < 3:
        raise ProtokolHatasi(f"{ad}: en az 3 elemanlı tek boyutlu dizi olmalı")
    if not np.all(np.isfinite(a)) or np.any(a <= 0):
        raise ProtokolHatasi(f"{ad}: NaN/inf/sıfır-altı değer var; eksik veri sessizce doldurulmaz")
    return a


# ------------------------------------------------------------------ plasebo


def plasebo_mar(
    varlik_getiri: np.ndarray,
    agirlik: np.ndarray,
    *,
    maliyet_orani: float,
    yil_bar: float,
    ornek: int = 500,
    tohum: int = 0,
    asgari_kaydirma_orani: float = 0.05,
) -> tuple[float, np.ndarray]:
    """Stratejinin ağırlık takvimi ve dairesel kaydırılmış kopyalarının MAR'ı (aynı doğrusal model).

    `varlik_getiri` T×N (ya da T) bar getirisi, `agirlik[t]` t barında **tutulan** ağırlık
    (T×N ya da T; karar → dolum gecikmesi çağıranın sorumluluğunda). Kaydırma tüm
    enstrümanlara **aynı** k ile uygulanır (kesit yapısı korunur, K-044 kalıbı); işlem sayısı,
    tutma süreleri, ortalama maruziyet ve maliyet aynen kalır, yalnız fiyatla hizalanma bozulur.
    k, `[asgari, T − asgari]` aralığından düzgün çekilir: çok küçük k gerçek takvimin neredeyse
    kopyasıdır.

    Döner: `(gerçek takvimin MAR'ı, plasebo MAR dizisi)` — ikisi de **aynı** modelle, karşılaştırma
    elma-elma. Motorun gerçek özkaynağı P1/P2 için kullanılır, P3 için bu.
    """
    r = np.asarray(varlik_getiri, dtype=np.float64)
    w = np.asarray(agirlik, dtype=np.float64)
    if r.shape != w.shape:
        raise ProtokolHatasi(f"getiri {r.shape} ve ağırlık {w.shape} aynı biçimde olmalı")
    if not (np.all(np.isfinite(r)) and np.all(np.isfinite(w))):
        raise ProtokolHatasi("plasebo girdisinde NaN/inf var")
    if r.ndim == 1:
        r, w = r[:, None], w[:, None]
    t = r.shape[0]
    asgari = max(1, int(t * asgari_kaydirma_orani))
    if t - 2 * asgari < 1:
        raise ProtokolHatasi("plasebo için seri çok kısa")

    def mar(ag: np.ndarray) -> float:
        devir = np.abs(np.diff(ag, axis=0, prepend=np.zeros((1, ag.shape[1])))).sum(axis=1)
        g = (ag * r).sum(axis=1) - devir * maliyet_orani
        oz = np.concatenate([[1.0], np.cumprod(1.0 + g)])
        if np.any(oz <= 0):
            return -1.0
        yil = g.size / yil_bar
        cagr = oz[-1] ** (1 / yil) - 1
        mdd, _ = azami_dusus(oz)
        return cagr / mdd if mdd > 0 else float("nan")

    rng = np.random.default_rng(tohum)
    kaydirmalar = rng.integers(asgari, t - asgari + 1, size=ornek)
    return mar(w), np.array([mar(np.roll(w, int(k), axis=0)) for k in kaydirmalar])


# ------------------------------------------------------------------ bootstrap


def blok_bootstrap(
    g_s: np.ndarray, g_k: np.ndarray, *, yil_bar: float, ortalama_blok: int,
    ornek: int = BOOTSTRAP_ORNEK, tohum: int = 0,
) -> dict[str, float]:
    """Durağan blok bootstrap (Politis-Romano), **eşleşik**: strateji ve kıyas aynı blokları çeker.

    Döner: düşüş azaltımı `1 − MDD_S/MDD_K` için %5/%50 persentil ve `P(MAR_S > MAR_K)`.
    """
    if g_s.shape != g_k.shape:
        raise ProtokolHatasi("bootstrap: strateji ve kıyas getirileri hizasız")
    t = g_s.size
    rng = np.random.default_rng(tohum)
    p = 1.0 / max(1, ortalama_blok)

    def mdd_mar(g: np.ndarray) -> tuple[float, float]:
        oz = np.concatenate([[1.0], np.cumprod(1 + g)])
        mdd = float((1 - oz / np.maximum.accumulate(oz)).max())
        cagr = oz[-1] ** (yil_bar / g.size) - 1 if oz[-1] > 0 else -1.0
        return mdd, (cagr / mdd if mdd > 0 else float("nan"))

    azaltim, ustun = [], 0
    ar = np.arange(t)
    for _ in range(ornek):
        # Blok başlangıçları: her bar p olasılıkla yeni blok açar; blok içinde ardışık ilerler.
        yeni = rng.random(t) < p
        yeni[0] = True
        blok = np.cumsum(yeni) - 1
        baslar = rng.integers(t, size=int(yeni.sum()))
        ofset = ar - np.flatnonzero(yeni)[blok]
        idx = (baslar[blok] + ofset) % t
        (m_s, r_s), (m_k, r_k) = mdd_mar(g_s[idx]), mdd_mar(g_k[idx])
        azaltim.append(1 - m_s / m_k if m_k > 0 else 0.0)
        ustun += int(np.nan_to_num(r_s, nan=-np.inf) > np.nan_to_num(r_k, nan=-np.inf))
    a = np.array(azaltim)
    return {"azaltim_p05": float(np.percentile(a, 5)), "azaltim_p50": float(np.percentile(a, 50)),
            "mar_ustunluk_olasiligi": ustun / ornek}


# ------------------------------------------------------------------ değerlendirme


@dataclass(frozen=True)
class RyppGirdisi:
    """Donmuş stratejinin **OOS** koşusu ve aynı pencerede kıyas. Seriler bar hizalı özkaynaktır."""

    strateji: np.ndarray
    kiyas: np.ndarray
    strateji_2x_maliyet: np.ndarray | None
    yil_bar: float
    epizot_esigi: float
    """Kıyas düşüş epizodu eşiği; varlık sınıfının oynaklığına göre **önceden** seçilir
    (kripto 0,20, hisse endeksi 0,10 — K-125 tasarım kararı)."""
    plasebo: tuple[float, np.ndarray] | None
    """`plasebo_mar` çıktısı; yoksa P3 ölçülemez → INCONCLUSIVE."""
    aile_sayisi: int
    """P3'ün Bonferroni k'sı (K-128): adayın RYPP araştırma programının **açılışta** yazılan
    bütçesi (`azami_cekilis`). Önceden sabit; sonuca göre seçilmez, "başarılı aile" sayısı
    değildir; varsayılanı yok (eksik k dolu görünmesin). `int` ≥ 1; `bool`/`float`/`str` hata."""
    aile_program: str | None = None
    """k'nın kaynağı olan RYPP programının adı (K-128). Promotion bütçeyi program defterinden
    okuyup k ile karşılaştırır; yoksa RYPP kanıtı promotion'da kabul edilmez."""
    tohum: int = 0


@dataclass
class RyppSonucu:
    durum: Durum
    kosullar: list[dict[str, Any]] = field(default_factory=list)
    strateji: SeriOlcumu | None = None
    kiyas: SeriOlcumu | None = None
    bootstrap: dict[str, float] | None = None
    aile: dict[str, Any] | None = None
    """P3'ün çoklu test bağlamı (K-128): `sayi` (k), `program`, `persentil` (1 − α/k)."""

    def sozluk(self) -> dict[str, Any]:
        return {
            "durum": str(self.durum),
            "aile": self.aile,
            "kosullar": self.kosullar,
            "strateji": self.strateji.sozluk() if self.strateji else None,
            "kiyas": self.kiyas.sozluk() if self.kiyas else None,
            "bootstrap": self.bootstrap,
            "esikler": ESIKLER,
        }


def _dogrula_aile(sayi: Any, program: Any) -> dict[str, Any]:
    """k sözleşmesi (K-127/K-128). Eskiden `max(1, k)` k=0'ı sessizce 1 yapıyordu: yanlış k,
    eşiği gevşeten bir düzeltme olmadan reddedilir."""
    if type(sayi) is not int or sayi < 1:
        raise ProtokolHatasi(f"aile_sayisi (k) ≥ 1 tam sayı olmalı, verilen: {sayi!r}")
    if program is not None and (not isinstance(program, str) or not program):
        raise ProtokolHatasi(f"aile_program boş olmayan bir ad olmalı, verilen: {program!r}")
    return {"sayi": sayi, "program": program, "persentil": 1 - ALFA / sayi}


def _p1_p2(s: SeriOlcumu, k: SeriOlcumu) -> tuple[bool, bool, bool]:
    p1 = k.mdd > 0 and (1 - s.mdd / k.mdd) >= ASGARI_DD_AZALTIM
    p2a = s.cagr >= (ASGARI_GETIRI_KORUMA * k.cagr if k.cagr > 0 else k.cagr)
    p2b = (not math.isnan(s.mar)) and (math.isnan(k.mar) or s.mar >= k.mar)
    return p1, p2a, p2b


def degerlendir(g: RyppGirdisi) -> RyppSonucu:
    s_oz = _dogrula_seri(g.strateji, "strateji")
    k_oz = _dogrula_seri(g.kiyas, "kiyas")
    if s_oz.size != k_oz.size:
        raise ProtokolHatasi("strateji ve kıyas özkaynağı aynı barlarda olmalı (hizasız)")
    aile = _dogrula_aile(g.aile_sayisi, g.aile_program)
    s, k = olc(s_oz, g.yil_bar), olc(k_oz, g.yil_bar)
    sonuc = RyppSonucu(Durum.INCONCLUSIVE, strateji=s, kiyas=k, aile=aile)

    def kosul(ad: str, gecti: bool | None, deger: Any, esik: Any, aciklama: str,
              **ek: Any) -> None:
        sonuc.kosullar.append({"ad": ad, "gecti": gecti, "deger": deger, "esik": esik,
                               "aciklama": aciklama, **ek})

    # 1) Veri yeterliliği
    yil = (s_oz.size - 1) / g.yil_bar
    epizot = dusus_epizotlari(k_oz, g.epizot_esigi)
    yeterli = True
    for ad, ok, deger, esik, ac in (
        ("oos_suresi", yil >= ASGARI_OOS_YIL, round(yil, 3), ASGARI_OOS_YIL, "yıl"),
        ("kiyas_epizot", len(epizot) >= ASGARI_EPIZOT, len(epizot), ASGARI_EPIZOT,
         f"kıyasta ≥ {g.epizot_esigi:.0%} düşüş epizodu"),
        ("plasebo_var", g.plasebo is not None and g.plasebo[1].size >= ASGARI_PLASEBO,
         0 if g.plasebo is None else int(g.plasebo[1].size), ASGARI_PLASEBO, "plasebo örneği"),
        ("stres_var", g.strateji_2x_maliyet is not None, g.strateji_2x_maliyet is not None, True,
         "2x maliyet koşusu"),
    ):
        kosul(ad, ok, deger, esik, ac)
        yeterli &= ok
    if not yeterli:
        return sonuc  # INCONCLUSIVE: kanıt karar vermeye yetmiyor

    # 2) Nokta koşulları
    p1, p2a, p2b = _p1_p2(s, k)
    kosul("P1_dusus_azaltimi", p1, round(1 - s.mdd / k.mdd, 4) if k.mdd > 0 else None,
          ASGARI_DD_AZALTIM, "1 − MDD_S/MDD_K")
    kosul("P2a_getiri_korunumu", p2a, round(s.cagr, 4),
          round(ASGARI_GETIRI_KORUMA * k.cagr if k.cagr > 0 else k.cagr, 4), "CAGR_S")
    kosul("P2b_verimlilik", p2b, s.mar, k.mar, "MAR_S ≥ MAR_K")
    gercek_mar, plas = g.plasebo  # type: ignore[misc]
    q = aile["persentil"]
    esik_p3 = float(np.nanquantile(plas, q))
    kosul("P3_plasebo", bool(gercek_mar > esik_p3), gercek_mar, esik_p3,
          f"kaydırılmış takvim MAR persentili {q:.4f} (aile k={g.aile_sayisi})", persentil=q)
    s2 = olc(_dogrula_seri(g.strateji_2x_maliyet, "strateji_2x_maliyet"), g.yil_bar)
    kosul("S1_maliyet_stresi", (not math.isnan(s2.mar)) and (math.isnan(k.mar) or s2.mar >= k.mar),
          s2.mar, k.mar, "2x maliyette MAR_S ≥ MAR_K")
    # R1: başlangıç tarihi duyarlılığı — ilk yarıdan eşit aralıklı 8 başlangıç
    yarim = s_oz.size // 2
    tut = 0
    baslar = np.linspace(0, yarim, 8, dtype=int)
    for b in baslar:
        ss, kk = olc(s_oz[b:], g.yil_bar), olc(k_oz[b:], g.yil_bar)
        x1, _, x2b = _p1_p2(ss, kk)
        tut += int(x1 and x2b)
    oran = tut / len(baslar)
    kosul("R1_baslangic", oran >= ASGARI_BASLANGIC_ORANI, oran, ASGARI_BASLANGIC_ORANI,
          "P1 ve P2b'nin tuttuğu başlangıç payı")
    # R2: alt dönemler — iki yarıda da strateji kıyastan derin düşmemeli
    r2 = all(olc(s_oz[a:b], g.yil_bar).mdd <= olc(k_oz[a:b], g.yil_bar).mdd
             for a, b in ((0, yarim + 1), (yarim, s_oz.size)))
    kosul("R2_alt_donem", r2, r2, True, "her yarıda MDD_S ≤ MDD_K")
    # R3: tek olay baskınlığı — epizot içinde iyileşme en az iki epizotta
    iyi = 0
    for z, _dip, bit, derin in epizot:
        s_ep, _ = azami_dusus(s_oz[z:bit + 1])
        iyi += int(s_ep <= EPIZOT_IYILESME * derin)
    kosul("R3_tek_olay", iyi >= ASGARI_EPIZOT, iyi, ASGARI_EPIZOT,
          f"epizot içi düşüş ≤ %{EPIZOT_IYILESME * 100:.0f} × kıyas olan epizot sayısı")

    if not all(c["gecti"] for c in sonuc.kosullar):
        sonuc.durum = Durum.FAIL
        return sonuc

    # 3) Belirsizlik — nokta geçti; güven aralığı karara yetiyor mu?
    bs = blok_bootstrap(_getiriler(s_oz), _getiriler(k_oz), yil_bar=g.yil_bar,
                        ortalama_blok=max(1, int(g.yil_bar / 12)), tohum=g.tohum)
    sonuc.bootstrap = bs
    ok = bs["azaltim_p05"] > 0 and bs["mar_ustunluk_olasiligi"] >= ASGARI_BOOTSTRAP_P
    kosul("B_bootstrap", ok, bs, {"azaltim_p05": ">0", "mar_ustunluk": ASGARI_BOOTSTRAP_P},
          "eşleşik durağan blok bootstrap (ortalama blok ≈ 1 ay)")
    sonuc.durum = Durum.PASS if ok else Durum.INCONCLUSIVE
    return sonuc


__all__ = [
    "ALFA",
    "ESIKLER",
    "Durum",
    "ProtokolHatasi",
    "RyppGirdisi",
    "RyppSonucu",
    "SeriOlcumu",
    "azami_dusus",
    "blok_bootstrap",
    "degerlendir",
    "dusus_epizotlari",
    "olc",
    "plasebo_mar",
    "sortino_standart",
]
