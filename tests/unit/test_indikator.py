"""İndikatör doğrulaması: bağımsız referans + nedensellik. (Faz 2 bitti kriteri, K-026)

İki ayrı iddia test ediliyor ve karıştırılmamalı:

- **Doğruluk:** sayılarımız TA-Lib'in sayılarıyla aynı mı (`tests/fixtures/` altındaki
  dondurulmuş referans). Referans bizim kodumuzdan türetilmedi; başka bir uygulamadan
  geldi — türetilseydi test hiçbir şey kanıtlamazdı.
- **Nedensellik:** `çıktı[t]` yalnızca `girdi[0..t]`'ye bağlı mı. Bu, K-002'nin indikatör
  katmanındaki karşılığı ve doğruluktan bağımsız: yanlış ama nedensel bir indikatör de,
  doğru ama geleceğe bakan bir indikatör de mümkün.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from scryne_quant.features import indikator as ind

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "indikator_referans.json"

#: TA-Lib yürüyen toplam, numpy pencere başına toplam kullanıyor; ikisi de doğru, kayan
#: nokta toplama sırası farklı. Ölçülen en büyük bağıl fark 3,1e-12 (Bollinger'ın standart
#: sapması); tolerans onun bir mertebe üstünde. Bu bir "yaklaşık doğru" izni değil —
#: konvansiyon farkları (tohumlama, ddof, ısınma uzunluğu) bu toleransın kat kat üstünde
#: sapma üretir ve testi kırar.
BAGIL_TOLERANS = 1e-11


def _yukle() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _dizi(degerler: list[float | None]) -> np.ndarray:
    return np.array([np.nan if d is None else d for d in degerler], dtype=np.float64)


REFERANS = _yukle()
VAKALAR = {v["ad"]: v for v in REFERANS["vakalar"]}


def _bizim(vaka: dict, anahtar: str) -> np.ndarray:
    """Referanstaki bir sütun adını bizim fonksiyonlarımızdan üretir."""
    g = {ad: _dizi(seri) for ad, seri in vaka["girdi"].items()}
    h, d, k, v = g["high"], g["low"], g["close"], g["volume"]

    if anahtar == "true_range":
        return ind.gercek_aralik(h, d, k)
    ad, _, kuyruk = anahtar.partition("_")
    if ad == "sma":
        return ind.sma(k, int(kuyruk))
    if ad == "ema":
        return ind.ema(k, int(kuyruk))
    if ad == "rsi":
        return ind.rsi(k, int(kuyruk))
    if ad == "atr":
        return ind.atr(h, d, k, int(kuyruk))
    if ad == "hacim":
        return ind.hacim_ortalamasi(v, int(kuyruk.removeprefix("sma_")))
    if ad == "enyuksek":
        return ind.en_yuksek(h, int(kuyruk))
    if ad == "endusuk":
        return ind.en_dusuk(d, int(kuyruk))
    if ad == "roc":
        return ind.roc(k, int(kuyruk))
    if ad == "bollinger":
        pencere, katsayi, band = kuyruk.split("_")
        bantlar = ind.bollinger(k, int(pencere), float(katsayi))
        return {"alt": bantlar.alt, "orta": bantlar.orta, "ust": bantlar.ust}[band]
    raise AssertionError(f"referansta tanınmayan sütun: {anahtar}")


def _tum_sutunlar() -> list[tuple[str, str]]:
    return [(v["ad"], s) for v in REFERANS["vakalar"] for s in sorted(v["beklenen"])]


class TestReferans:
    """Her indikatör, TA-Lib'den dondurulmuş bağımsız referansla karşılaştırılır."""

    @pytest.mark.parametrize(("vaka_adi", "sutun"), _tum_sutunlar())
    def test_referansla_ayni(self, vaka_adi: str, sutun: str):
        vaka = VAKALAR[vaka_adi]
        beklenen = _dizi(vaka["beklenen"][sutun])
        bizim = _bizim(vaka, sutun)

        assert bizim.shape == beklenen.shape

        # Isınma maskesi **birebir** eşit olmalı. Tolerans sayılar için; "ilk geçerli
        # değer hangi indekste" bir konvansiyon sorusudur ve yaklaşık cevabı yoktur.
        if vaka_adi == "duz_40" and sutun.startswith("rsi_"):
            pytest.skip("hareketsiz seride TA-Lib'den bilinçli sapma; ayrı testte")
        np.testing.assert_array_equal(
            np.isnan(bizim), np.isnan(beklenen), err_msg=f"{vaka_adi}/{sutun}: NaN maskesi"
        )

        gecerli = ~np.isnan(beklenen)
        np.testing.assert_allclose(
            bizim[gecerli],
            beklenen[gecerli],
            rtol=BAGIL_TOLERANS,
            atol=0.0,
            err_msg=f"{vaka_adi}/{sutun}",
        )

    def test_alti_indikatorun_hepsi_kapsanmis(self):
        """Faz 2 ≥6 indikatör istiyor; referansın gerçekten hepsini içerdiğini sabitler."""
        sutunlar = {s for v in REFERANS["vakalar"] for s in v["beklenen"]}
        aileler = {s.split("_")[0] for s in sutunlar}
        assert {
            "sma", "ema", "rsi", "atr", "bollinger", "hacim", "enyuksek", "endusuk", "roc"
        } <= aileler
        assert len(aileler - {"true"}) >= 6

    def test_referans_baska_bir_uygulamadan_geliyor(self):
        """Referansın kaynağı kayıtlı olmalı — kendi çıktımızdan türetilmiş olamaz."""
        kaynak = REFERANS["kaynak"]
        assert kaynak["kutuphane"] == "TA-Lib"
        assert kaynak["surum"]


class TestNedensellik:
    """`çıktı[t]` yalnızca `girdi[0..t]`'ye bağlı olmalı. (K-002'nin indikatör ayağı)"""

    KESME = 120

    def _girdi(self) -> dict[str, np.ndarray]:
        vaka = VAKALAR["sentetik_400"]
        return {ad: _dizi(seri) for ad, seri in vaka["girdi"].items()}

    @staticmethod
    def _boz(g: dict[str, np.ndarray], t: int) -> dict[str, np.ndarray]:
        """`t`'den sonraki her şeyi tanınmaz hâle getirir."""
        rng = np.random.default_rng(1234)
        bozuk = {ad: seri.copy() for ad, seri in g.items()}
        n = len(bozuk["close"]) - (t + 1)
        for ad in ("open", "high", "low", "close"):
            bozuk[ad][t + 1 :] = rng.uniform(1.0, 90_000.0, n)
        bozuk["volume"][t + 1 :] = rng.uniform(0.0, 1e6, n)
        # Yüksek/düşük tutarlılığını korumaya çalışmıyoruz: bozulmuş gelecek gerçekten
        # bozuk olmalı, "biraz farklı ama hâlâ geçerli" değil.
        return bozuk

    @pytest.mark.parametrize(
        "cagri",
        [
            pytest.param(lambda g: ind.sma(g["close"], 20), id="sma_20"),
            pytest.param(lambda g: ind.ema(g["close"], 20), id="ema_20"),
            pytest.param(lambda g: ind.rsi(g["close"], 14), id="rsi_14"),
            pytest.param(lambda g: ind.atr(g["high"], g["low"], g["close"], 14), id="atr_14"),
            pytest.param(
                lambda g: ind.gercek_aralik(g["high"], g["low"], g["close"]), id="true_range"
            ),
            pytest.param(lambda g: ind.bollinger(g["close"], 20, 2.0).ust, id="bb_ust"),
            pytest.param(lambda g: ind.bollinger(g["close"], 20, 2.0).alt, id="bb_alt"),
            pytest.param(lambda g: ind.hacim_ortalamasi(g["volume"], 20), id="hacim_sma_20"),
            pytest.param(lambda g: ind.en_yuksek(g["high"], 20), id="en_yuksek_20"),
            pytest.param(lambda g: ind.en_dusuk(g["low"], 20), id="en_dusuk_20"),
            pytest.param(lambda g: ind.roc(g["close"], 10), id="roc_10"),
        ],
    )
    def test_gelecek_bozulunca_gecmis_degismiyor(self, cagri):
        temiz = self._girdi()
        bozuk = self._boz(temiz, self.KESME)

        a = cagri(temiz)[: self.KESME + 1]
        b = cagri(bozuk)[: self.KESME + 1]

        # `assert_array_equal` NaN'ları eşit sayar ve bit düzeyinde karşılaştırır —
        # "yaklaşık aynı" burada yeterli değil, K-002 bit düzeyinde eşitlik istiyor.
        np.testing.assert_array_equal(a, b)

    def test_bozma_gercekten_bir_sey_degistiriyor(self):
        """Negatif kontrol: bozma etkisizse yukarıdaki testler boş yere yeşil olurdu."""
        temiz = self._girdi()
        bozuk = self._boz(temiz, self.KESME)
        a = ind.sma(temiz["close"], 20)
        b = ind.sma(bozuk["close"], 20)
        assert not np.array_equal(a[self.KESME + 1 :], b[self.KESME + 1 :])


class TestSozlesme:
    def test_girdi_degistirilmiyor(self):
        x = np.linspace(100.0, 200.0, 60)
        kopya = x.copy()
        ind.sma(x, 10)
        ind.ema(x, 10)
        ind.rsi(x, 14)
        ind.bollinger(x, 20, 2.0)
        np.testing.assert_array_equal(x, kopya)

    def test_salt_okunur_girdi_kabul_edilir(self):
        """Motor `ctx`'e giden dizileri yazılamaz yapıyor; indikatörler onları alabilmeli."""
        x = np.linspace(100.0, 200.0, 60)
        x.flags.writeable = False
        assert not np.isnan(ind.sma(x, 10)[-1])

    def test_isinma_nan_uzunluk_korunuyor(self):
        x = np.linspace(100.0, 200.0, 60)
        for cikti, ilk in ((ind.sma(x, 10), 9), (ind.ema(x, 10), 9), (ind.rsi(x, 14), 14)):
            assert cikti.size == x.size
            assert np.all(np.isnan(cikti[:ilk]))
            assert not np.isnan(cikti[ilk])

    @pytest.mark.parametrize(
        "cagri",
        [
            lambda: ind.sma(np.arange(5.0), 0),
            lambda: ind.sma(np.arange(5.0), 10),
            lambda: ind.ema(np.arange(5.0), 10),
            lambda: ind.rsi(np.arange(5.0), 14),
            lambda: ind.bollinger(np.arange(5.0), 20),
            lambda: ind.bollinger(np.arange(30.0), 20, -1.0),
            lambda: ind.sma(np.zeros((3, 3)), 2),
            lambda: ind.en_yuksek(np.arange(5.0), 10),
            lambda: ind.roc(np.arange(5.0), 10),
        ],
    )
    def test_anlamsiz_parametre_hata_veriyor(self, cagri):
        # Sessizce kısa seri döndürmek, backtest'i eksik veriyle çalıştırmak demek olurdu.
        with pytest.raises(ind.GecersizParametre):
            cagri()

    def test_hareketsiz_seride_rsi_tanimsiz(self):
        """TA-Lib'den **bilinçli sapma** (K-026): düz seride TA-Lib 0.0, biz NaN veriyoruz.

        0.0 RSI ölçeğinde azami aşırı satımdır: hiç hareket etmeyen bir piyasa,
        mean-reversion stratejisine üretilebilecek en güçlü alım sinyalini verirdi.
        """
        duz = np.full(40, 100.0)
        cikti = ind.rsi(duz, 14)
        assert np.all(np.isnan(cikti))

        referans = _dizi(VAKALAR["duz_40"]["beklenen"]["rsi_14"])
        assert referans[20] == 0.0, (
            "TA-Lib davranışı değişmiş; sapmanın gerekçesi gözden geçirilmeli"
        )

    def test_kesintisiz_yukselisde_rsi_yuz(self):
        artan = 100.0 + np.arange(40, dtype=np.float64)
        cikti = ind.rsi(artan, 14)
        assert cikti[14] == pytest.approx(100.0)

    def test_bollinger_bantlari_sirali(self):
        vaka = VAKALAR["sentetik_400"]
        k = _dizi(vaka["girdi"]["close"])
        b = ind.bollinger(k, 20, 2.0)
        gecerli = ~np.isnan(b.orta)
        assert np.all(b.alt[gecerli] <= b.orta[gecerli])
        assert np.all(b.orta[gecerli] <= b.ust[gecerli])

    def test_atr_negatif_olamaz(self):
        vaka = VAKALAR["sentetik_400"]
        g = {ad: _dizi(seri) for ad, seri in vaka["girdi"].items()}
        a = ind.atr(g["high"], g["low"], g["close"], 14)
        assert np.all(a[~np.isnan(a)] >= 0.0)

    def test_kanal_siniri_pencereyi_kapsiyor(self):
        """`en_yuksek` `t`'nin **kendi** zirvesini de içerir — kaydırma stratejinin işi.

        Bunu indikatöre gömmek TA-Lib `MAX` ile karşılaştırmayı imkânsız kılardı; Donchian
        kırılımı yazan strateji `ctx.ozellik("kanal_ust", 1)` ile bir bar geriden okur.
        """
        x = np.array([1.0, 5.0, 3.0, 2.0, 9.0])
        np.testing.assert_array_equal(ind.en_yuksek(x, 3)[2:], np.array([5.0, 5.0, 9.0]))
        np.testing.assert_array_equal(ind.en_dusuk(x, 3)[2:], np.array([1.0, 2.0, 2.0]))

    def test_roc_yuzde_olceginde(self):
        """TA-Lib `ROC` yüzde döndürür, `ROCP` kesir. Karıştırmak 100 kat hata demek."""
        x = np.array([100.0, 110.0, 121.0])
        assert ind.roc(x, 1)[1] == pytest.approx(10.0)
        assert ind.roc(x, 2)[2] == pytest.approx(21.0)


class TestFundingIndikatorleri:
    """`persentil_sirasi` ve `kumulatif` — funding'in iki okuma biçimi. (K-042)

    Bu ikisinin TA-Lib karşılığı yok, yani K-026'nın "bağımsız referansla doğrula" kuralı
    burada elle kurulmuş beklenen değerlerle sağlanıyor. Küçük ve elle sayılabilir diziler
    kullanılıyor: doğruluğu okuyan kişi de kontrol edebilmeli.
    """

    def test_persentil_elle_hesaplanan_degerle(self):
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        out = ind.persentil_sirasi(x, 3)
        # [1,2,3] -> 3 en büyük, 3/3; [2,3,4] -> 3/3; [3,4,5] -> 3/3
        assert np.isnan(out[:2]).all()
        np.testing.assert_allclose(out[2:], [1.0, 1.0, 1.0])

    def test_persentil_dusen_seride(self):
        x = np.array([5.0, 4.0, 3.0, 2.0, 1.0])
        out = ind.persentil_sirasi(x, 3)
        # her pencerede son değer en küçük: 1/3
        np.testing.assert_allclose(out[2:], [1 / 3, 1 / 3, 1 / 3])

    def test_persentil_ortada(self):
        x = np.array([1.0, 3.0, 2.0])
        # [1,3,2] içinde 2'den küçük/eşit olanlar: 1 ve 2 → 2/3
        assert ind.persentil_sirasi(x, 3)[2] == pytest.approx(2 / 3)

    def test_persentil_araligi_sifir_bir(self):
        rng = np.random.default_rng(7)
        out = ind.persentil_sirasi(rng.normal(size=500), 50)
        gecerli = out[~np.isnan(out)]
        assert gecerli.min() >= 1 / 50 and gecerli.max() <= 1.0

    def test_persentil_seviyeden_bagimsiz(self):
        """Seriye sabit eklemek persentil sırasını değiştirmemeli — K-042/3'ün gerekçesi.

        Funding'in medyanı kalıcı pozitif; mutlak eşik bu kaymadan etkilenir, persentil
        etkilenmez. Test o iddianın kendisi.
        """
        rng = np.random.default_rng(11)
        x = rng.normal(size=200)
        np.testing.assert_allclose(
            ind.persentil_sirasi(x, 30), ind.persentil_sirasi(x + 100.0, 30)
        )

    def test_kumulatif_elle_hesaplanan_degerle(self):
        x = np.array([1.0, 2.0, 3.0, 4.0])
        out = ind.kumulatif(x, 2)
        assert np.isnan(out[0])
        np.testing.assert_allclose(out[1:], [3.0, 5.0, 7.0])

    @pytest.mark.parametrize("fon", [ind.persentil_sirasi, ind.kumulatif])
    def test_penceredeki_nan_sonucu_nan_yapiyor(self, fon):
        """Boşluk uydurulmaz (K-024): eksik bir değer sıfır sayılmaz."""
        x = np.array([1.0, np.nan, 3.0, 4.0, 5.0])
        out = fon(x, 3)
        assert np.isnan(out[2]) and np.isnan(out[3])
        assert not np.isnan(out[4])

    @pytest.mark.parametrize("fon", [ind.persentil_sirasi, ind.kumulatif])
    def test_nedensel(self, fon):
        """Geleceği bozmak geçmişi değiştirmemeli (K-002)."""
        rng = np.random.default_rng(3)
        x = rng.normal(size=120)
        temiz = fon(x, 20)
        bozuk_x = x.copy()
        bozuk_x[80:] = 999.0
        bozuk = fon(bozuk_x, 20)
        np.testing.assert_array_equal(temiz[:80], bozuk[:80])
