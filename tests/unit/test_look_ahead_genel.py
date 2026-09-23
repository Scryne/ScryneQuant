"""Look-ahead: **her** kayıtlı gösterge ve **her** kütüphane stratejisi. (K-002, K-118)

`test_look_ahead.py` ve `test_indikator.py` nedenselliği elle seçilmiş bir alt kümede
ölçüyordu: `sma_kesisim`, üç funding stratejisi ve on bir gösterge. Göstergeler koşu başında
tüm seri üzerinde **önceden** hesaplanıyor (`features/motor.hesapla`), yani nedensel olmayan bir
gösterge `ctx`'in kesmesine rağmen geleceği sızdırır — ve listeye eklenmemişse hiçbir test
kırılmaz. Bu dosya listeyi elle değil, kayıttan (`motor.DEFTER`, `KUTUPHANE`, `KIYAS`) kurar:
yeni bir gösterge ya da strateji eklendiği anda otomatik olarak teste girer.
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from scryne_quant.features import motor
from scryne_quant.features.barlar import bar_dizileri
from scryne_quant.strategy.kosu import gorunum_kur, sinyalleri_uret
from scryne_quant.strategy.kutuphane import KIYAS, KUTUPHANE, YATIRIM
from tests.conftest import bar_uret

N = 1_500
KESME = 1_100

#: Gösterge parametreleri: sentetik serinin boyuna uygun küçük değerler.
PARAMETRE = {"pencere": 10, "birikim": 3, "katsayi": 2.0}


def _alanlar(tohum: int = 5) -> dict[str, np.ndarray]:
    """Fiyat alanları + defterin istediği her ek alan (funding, basis, makro, konumlanma)."""
    d = {k: np.asarray(v) for k, v in bar_dizileri(bar_uret(n=N, tohum=tohum)).items()}
    rng = np.random.default_rng(tohum)
    # BTC 1h oynaklığı (~%0,8): `bar_uret`in serisi eşikli stratejiler (momentum) için fazla
    # sakin, hiç sinyal üretmezler ve test boş kümeleri karşılaştırır.
    close = 30_000.0 * np.exp(np.cumsum(rng.normal(0.0, 0.008, N)))
    acilis = np.concatenate([[close[0]], close[:-1]])
    sapma = np.abs(rng.normal(0.0, 0.003, N))
    d["open"], d["close"] = acilis, close
    d["high"] = np.maximum(acilis, close) * (1 + sapma)
    d["low"] = np.minimum(acilis, close) * (1 - sapma)
    ekler = {a for k in motor.DEFTER.values() for a in k.girdiler} - set(d)
    for ad in sorted(ekler):
        d[ad] = rng.uniform(0.01, 2.0, N)
    return d


def _boz(d: dict[str, np.ndarray], t: int, deger: float | None) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(99)
    out = {k: np.array(v) for k, v in d.items()}
    for ad, dizi in out.items():
        if ad in ("open_time", "quality_status") or dizi.dtype.kind not in "fi":
            continue
        n = len(dizi) - (t + 1)
        if deger is None:
            dizi[t + 1:] = rng.uniform(1e-3, 9e4, n).astype(dizi.dtype)
        else:
            dizi[t + 1:] = np.asarray(deger).astype(dizi.dtype)
    return out


BOZMALAR = (("rastgele", None), ("yukari", 1e9), ("asagi", 1e-3))


# ------------------------------------------------------------------ göstergeler


@pytest.mark.parametrize("ad", sorted(motor.DEFTER))
@pytest.mark.parametrize(("bozma", "deger"), BOZMALAR)
def test_her_kayitli_gosterge_nedensel(ad: str, bozma: str, deger: float | None) -> None:
    kayit = motor.DEFTER[ad]
    parametreler = {p: PARAMETRE[p] for p in kayit.parametreler}
    temiz = _alanlar()
    bozuk = _boz(temiz, KESME, deger)

    def cagir(d):
        girdiler = [np.asarray(d[a], dtype=np.float64) for a in kayit.girdiler]
        sonuc = kayit.fonksiyon(*girdiler, **parametreler)
        return sonuc if len(kayit.cikti_ekleri) > 1 else (sonuc,)

    for a, b in zip(cagir(temiz), cagir(bozuk), strict=True):
        np.testing.assert_array_equal(
            np.asarray(a)[: KESME + 1], np.asarray(b)[: KESME + 1],
            err_msg=f"{ad}: {bozma} bozması t={KESME}'e kadarki çıktıyı değiştirdi",
        )


def test_gosterge_testi_anlamsiz_degil() -> None:
    """Negatif kontrol: bozma geleceği gerçekten değiştiriyor (yoksa test boş yere yeşil)."""
    temiz = _alanlar()
    bozuk = _boz(temiz, KESME, None)
    k = motor.DEFTER["sma"]
    a = k.fonksiyon(temiz["close"].astype(float), pencere=10)
    b = k.fonksiyon(bozuk["close"].astype(float), pencere=10)
    assert not np.array_equal(a[KESME + 1:], b[KESME + 1:])


# ------------------------------------------------------------------ stratejiler


def _tek_sembollu() -> list[str]:
    return sorted({**KUTUPHANE, **KIYAS, **YATIRIM})


def _kur(ad: str):
    """Varsayılan parametreler; sentetik serinin boyunu aşan pencereler küçültülür."""
    sinif = {**KUTUPHANE, **KIYAS, **YATIRIM}[ad]
    imza = inspect.signature(sinif.__init__)
    kucuk = {}
    for p, v in imza.parameters.items():
        if isinstance(v.default, int) and not isinstance(v.default, bool) and v.default > 300:
            kucuk[p] = 300
    return sinif(**kucuk)


def _sinyaller(strateji, d, t):
    g = gorunum_kur("BTCUSDT", "1h", d, strateji)
    sinir = int(d["open_time"][t])
    return [s.model_dump_json() for s in sinyalleri_uret(strateji, g) if s.timestamp <= sinir]


@pytest.mark.parametrize("ad", _tek_sembollu())
@pytest.mark.parametrize(("bozma", "deger"), BOZMALAR)
def test_her_kutuphane_stratejisi_gelecegi_gormez(ad: str, bozma: str, deger) -> None:
    temiz = _alanlar()
    a = _sinyaller(_kur(ad), temiz, KESME)
    b = _sinyaller(_kur(ad), _boz(temiz, KESME, deger), KESME)
    assert a == b, f"{ad}: {bozma} bozması t'ye kadarki sinyalleri değiştirdi"


@pytest.mark.parametrize("ad", _tek_sembollu())
def test_strateji_testi_anlamsiz_degil(ad: str) -> None:
    assert _sinyaller(_kur(ad), _alanlar(), KESME), f"{ad}: kesmeye kadar hiç sinyal yok"
