"""Ölçülemeyen oynaklık = aday değil. (R1(c), 2026-09-20; `strategy/kurma.py` başlığı)

Null kalibrasyonu (`tools/faz12_coklu_test.py`) h51'in 141. denemesinde düştü: dairesel
kaydırma bir sembole ATR=0 pencere düşürdü, `Aday` `KurmaHatasi` fırlattı ve **tek sembol**
bütün evren adımını düşürdü. Karar (Scryne, A seçeneği): strateji katmanı oynaklığı
ölçülemeyen (0, NaN, inf) sembolü `Aday` kurmadan aday kümesinden çıkarır; `Aday`ın kendi
sözleşmesi (pozitif-sonlu ister) değişmez; null üreticisine özel istisna **yok**.

Bu dosya dört şeyi kanıtlıyor: (1) yardımcı 0/NaN/inf/negatifi reddediyor, pozitif-sonluyu
kabul ediyor; (2) düz fiyatlı (ATR=0) sembol aday olmuyor ve koşu düşmüyor; (3) NaN fiyatlı
sembol de aynı; (4) geçersiz sembolün varlığı geçerli adayların sonucunu **bit düzeyinde**
değiştirmiyor — "o sembol evrende hiç yokmuş" ile aynı `sonuc_hash`.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from scryne_quant.research import deney
from scryne_quant.research import evren_degerlendirme as ed
from scryne_quant.research.evren_kosu import EvrenVerisi
from scryne_quant.strategy.kurma import Aday, KurmaHatasi, oynaklik_olculebilir
from scryne_quant.strategy.kutuphane import EvrenEsitAgirlik, EvrenOynaklikAgirlik
from tests.unit.test_evren_kurma import HEDEF_BRUT, MALIYET, SEMBOLLER, N, _pencere, _veri

BOZUK = "EEEUSDT"


class TestYardimci:
    @pytest.mark.parametrize("deger", [0.0, -0.01, math.nan, math.inf, -math.inf])
    def test_olculemeyen_reddediliyor(self, deger):
        assert oynaklik_olculebilir(deger) is False

    @pytest.mark.parametrize("deger", [1e-9, 0.004, 1.0, 250.0])
    def test_pozitif_sonlu_kabul(self, deger):
        assert oynaklik_olculebilir(deger) is True

    def test_aday_sozlesmesi_degismedi(self):
        """`Aday` hâlâ pozitif-sonlu ister: dışlama stratejide, sözleşme yerinde."""
        with pytest.raises(KurmaHatasi):
            Aday(sembol="X", skor=1.0, oynaklik=0.0)
        with pytest.raises(KurmaHatasi):
            Aday(sembol="X", skor=1.0, oynaklik=math.nan)
        Aday(sembol="X", skor=1.0, oynaklik=0.01)  # geçerli


def _bozuk_veri(tur: str) -> EvrenVerisi:
    """`BOZUK` sembolün oynaklığı ölçülemez: `duz` → fiyat sabit (ATR=0); `nan` → fiyat NaN."""
    v = _veri()
    d = {a: np.array(x, copy=True) for a, x in v.diziler[BOZUK].items()}
    if tur == "duz":
        sabit = float(d["close"][0])
        for alan in ("open", "high", "low", "close"):
            d[alan][:] = sabit
    elif tur == "nan":
        for alan in ("open", "high", "low", "close"):
            d[alan][:] = np.nan
    else:
        raise ValueError(tur)
    diziler = dict(v.diziler)
    diziler[BOZUK] = d
    return EvrenVerisi(
        timeframe=v.timeframe, zamanlar=v.zamanlar, diziler=diziler, uyelik=v.uyelik,
        veri_sha256=v.veri_sha256, meta=v.meta, olcum_baslangici=v.olcum_baslangici,
        kural_kimligi=v.kural_kimligi,
    )


def _bozuk_uyesiz_veri() -> EvrenVerisi:
    """Aynı evren, `BOZUK` sembol **üyelikten** çıkarılmış: "hiç yokmuş" referansı."""
    v = _veri()
    uyelik = dict(v.uyelik)
    uyelik[BOZUK] = np.zeros(N, dtype=bool)
    return EvrenVerisi(
        timeframe=v.timeframe, zamanlar=v.zamanlar, diziler=v.diziler, uyelik=uyelik,
        veri_sha256=v.veri_sha256, meta=v.meta, olcum_baslangici=v.olcum_baslangici,
        kural_kimligi=v.kural_kimligi,
    )


def _strateji(sinif):
    azami = len(SEMBOLLER)
    if sinif is EvrenOynaklikAgirlik:
        return sinif(azami_agirlik_carpani=4.0, azami_enstruman=azami,
                     yeniden_dengele_bar=168, hedef_brut=HEDEF_BRUT)
    return sinif(yeniden_dengele_bar=168, azami_enstruman=azami,
                 azami_agirlik=HEDEF_BRUT / azami, hedef_brut=HEDEF_BRUT)


@pytest.mark.parametrize("sinif", [EvrenEsitAgirlik, EvrenOynaklikAgirlik])
@pytest.mark.parametrize("tur", ["duz", "nan"])
class TestBozukSembol:
    def test_kosu_dusmuyor_ve_bozuk_sembol_islem_gormuyor(self, sinif, tur):
        sonuc = ed.kosu(_strateji(sinif), MALIYET, _bozuk_veri(tur), _pencere())
        semboller = {i.sembol for i in sonuc.islemler}
        assert BOZUK not in semboller
        assert semboller, "geçerli semboller işlem görmeli — koşu boş değil"

    def test_bozuk_sembol_gecerli_adaylarin_sonucunu_degistirmiyor(self, sinif, tur):
        """Aday dışı = evrende yokmuş: metrikler, işlemler, özkaynak **birebir** aynı.

        `sonuc_hash`in kendisi eşit olamaz: kayıt evren muhasebesini de taşıyor (`uye_bar`,
        kalite sayımı) ve bozuk sembol üyelikte kalınca o sayılar farklı. Ekonomik alanlar
        dışında farkın yalnız bu muhasebede olduğu alan alan kanıtlanıyor.
        """
        bozuk = ed.kosu(_strateji(sinif), MALIYET, _bozuk_veri(tur), _pencere())
        referans = ed.kosu(_strateji(sinif), MALIYET, _bozuk_uyesiz_veri(), _pencere())
        farklar = deney.farklar(bozuk.sozluk(), referans.sozluk())
        muhasebe = ("/evren/", "/veri/", "/kimlik/sonuc_hash")
        ekonomik = [f for f in farklar if not f.startswith(muhasebe)]
        assert ekonomik == [], ekonomik
        assert bozuk.metrikler.sozluk() == referans.metrikler.sozluk()
        assert [i.sozluk(sembol_yaz=True) for i in bozuk.islemler] == [
            i.sozluk(sembol_yaz=True) for i in referans.islemler
        ]
