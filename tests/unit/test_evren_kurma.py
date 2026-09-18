"""Aynı seçim, farklı kurma. (Faz 16, `kurma_evren` programı)

Ölçülenler:

1. **Kapalı konumda kıyasla bit düzeyinde aynı.** `azami_agirlik_carpani = 1` ve
   `turnover_bandi = 0` kıyasın kendisidir. Bu, programın bütün karşılaştırmalarının
   dayandığı varsayım: kıyastan fark **yalnızca** kurma ayarından gelmeli.
2. Kapalı konum ızgaralarda **yok** — orada olsaydı tarama kendi kıyasını "en iyi" seçebilirdi.
3. Açık konumda sonuç gerçekten değişiyor (ızgara noktaları birbirinin kopyası değil):
   ölü bir eksen, olmayan bir platoyu var gösterir.
4. Oynaklık ayarlı dağıtımda ağırlık `1/σ` ile orantılı ve tavan bağlayıcı.
5. Turnover bandı yalnızca **bastırır**: bant büyüdükçe işlem sayısı artmaz.
6. Izgara/aile kayıtları program defteriyle tutarlı.
"""

from __future__ import annotations

import numpy as np
import pytest

from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.features.barlar import bar_dizileri
from scryne_quant.research import evren_degerlendirme as ed
from scryne_quant.research.bolme import Pencere
from scryne_quant.research.coklu_test_evren import SINYAL_OZELLIKLERI
from scryne_quant.research.evren_kosu import EvrenVerisi
from scryne_quant.research.izgaralar import (
    KURMA_CEKILISLERI,
    cekilis_programi,
    evren_cekilisi,
)
from scryne_quant.research.tarama import izgara as izgara_uret
from scryne_quant.strategy.kutuphane import (
    EVREN_AILELER,
    EvrenEsitAgirlik,
    EvrenOynaklikAgirlik,
    EvrenTurnoverBandi,
)
from tests.conftest import bar_uret

MALIYET = MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0)
N = 1_600
SEMBOLLER = ("AAAUSDT", "BBBUSDT", "BTCUSDT", "CCCUSDT", "DDDUSDT", "EEEUSDT")
HEDEF_BRUT = 0.2


#: Sembol başına oynaklık çarpanı. `bar_uret` bütün tohumlarda **aynı** oynaklığı üretiyor
#: (mutlak σ sabit), dolayısıyla farklı tohum yeterli değil: `1/σ` dağıtımı eşit ağırlığa
#: çok yakın çıkar ve tavan ekseni ölü görünür. İlk koşuda tam olarak bu oldu — dört çarpan
#: da aynı `sonuc_hash`i verdi. Getiriler çarpanla ölçekleniyor, yani oynaklık gerçekten
#: farklı; fiyat düzeyini ölçeklemek işe yaramazdı (ATR de aynı oranda ölçeklenir, ATR/fiyat
#: değişmez).
OYNAKLIK_CARPANI = (0.4, 0.7, 1.0, 1.6, 2.5, 4.0)


def _oynaklik_olcekle(d: dict[str, np.ndarray], k: float) -> dict[str, np.ndarray]:
    kapanis = d["close"].astype(np.float64)
    getiri = np.diff(np.log(kapanis), prepend=np.log(kapanis[0]))
    yeni_kapanis = kapanis[0] * np.exp(np.cumsum(getiri * k))
    oran = yeni_kapanis / kapanis
    out = dict(d)
    for alan in ("open", "high", "low", "close"):
        out[alan] = d[alan].astype(np.float64) * oran
    return out


def _veri() -> EvrenVerisi:
    diziler = {
        s: _oynaklik_olcekle(
            {a: np.array(x, copy=True)
             for a, x in bar_dizileri(bar_uret(n=N, tohum=101 + 7 * i)).items()},
            OYNAKLIK_CARPANI[i],
        )
        for i, s in enumerate(SEMBOLLER)
    }
    return EvrenVerisi(
        timeframe="1h",
        zamanlar=diziler["AAAUSDT"]["open_time"],
        diziler=diziler,
        uyelik={s: np.ones(N, dtype=bool) for s in SEMBOLLER},
        veri_sha256={s: "0" * 64 for s in SEMBOLLER},
        meta={},
        olcum_baslangici=722,
        kural_kimligi="test",
    )


def _pencere() -> Pencere:
    return Pencere("p", baslangic=722, bitis=N, isinma_baslangic=0)


def _kiyas(veri: EvrenVerisi, azami: int) -> object:
    return ed.kosu(
        EvrenEsitAgirlik(yeniden_dengele_bar=168, azami_enstruman=azami,
                         azami_agirlik=HEDEF_BRUT / azami, hedef_brut=HEDEF_BRUT),
        MALIYET, veri, _pencere(),
    )


class TestKapaliKonum:
    @pytest.mark.parametrize("azami", [2, 4])
    def test_carpan_bir_iken_kiyasla_ayni_kapanista(self, azami):
        """Tavan eşit paya oturunca 1/σ dağıtımı tümüyle kırpılır → eşit ağırlık.

        **Burada bit düzeyinde eşitlik aranmıyor ve bu bilinçli.** Turnover bandında
        aranıyor, çünkü orada `bant = 0` kod yolunu hiç değiştirmez. Çarpan = 1'de kod yolu
        gerçekten farklı: önce `1/σ` payları hesaplanır, sonra hepsi tavana kırpılır, artan
        pay kilitlenmemişlere dağıtılır. Sonuç matematiksel olarak eşit ağırlıktır ama
        aritmetik sırası farklı olduğu için son bitler tutmayabilir (0,098 + 0,002, 0,1'in
        bir ULP yakınıdır, kendisi değil). Bit eşitliği iddia etmek, tutmadığı anda testi
        susturmak için gevşetilecek bir iddia olurdu; ölçülebilir ve doğru olan iddia
        **ağırlıkların eşitliği**.
        """
        veri = _veri()
        kiyas = _kiyas(veri, azami)
        s = ed.kosu(
            EvrenOynaklikAgirlik(azami_agirlik_carpani=1.0, azami_enstruman=azami,
                                 yeniden_dengele_bar=168, hedef_brut=HEDEF_BRUT),
            MALIYET, veri, _pencere(),
        )
        assert s.metrikler.islem_sayisi == kiyas.metrikler.islem_sayisi
        assert np.allclose(s.ozkaynak, kiyas.ozkaynak, rtol=1e-9, atol=0.0)

    def test_carpan_bir_iken_agirliklar_esit(self):
        """Yukarıdaki testin asıl iddiası, doğrudan ölçülmüş hâli."""
        from scryne_quant.strategy.kurma import Aday, agirliklar

        ayarlar = EvrenOynaklikAgirlik(
            azami_agirlik_carpani=1.0, azami_enstruman=4, hedef_brut=HEDEF_BRUT
        )._ayarlar
        adaylar = [
            Aday(sembol=c, skor=4.0 - i, oynaklik=0.01 * (i + 1), mevcut_agirlik=0.0,
                 reason="TEST")
            for i, c in enumerate("ABCD")
        ]
        w = list(agirliklar(adaylar, ayarlar).values())
        assert max(w) - min(w) < 1e-12
        assert sum(w) == pytest.approx(HEDEF_BRUT, rel=1e-12)

    @pytest.mark.parametrize("azami", [2, 4])
    def test_bant_sifirken_kiyasla_bit_duzeyinde_ayni(self, azami):
        veri = _veri()
        kiyas = _kiyas(veri, azami)
        s = ed.kosu(
            EvrenTurnoverBandi(turnover_bandi=0.0, azami_enstruman=azami,
                               yeniden_dengele_bar=168, hedef_brut=HEDEF_BRUT),
            MALIYET, veri, _pencere(),
        )
        assert s.sonuc_hash == kiyas.sonuc_hash
        assert s.ozkaynak.tobytes() == kiyas.ozkaynak.tobytes()

    def test_kapali_konum_izgaralarda_yok(self):
        """Kıyasın kendisi bir ızgara noktası olamaz; olsaydı tarama onu seçebilirdi."""
        assert 1.0 not in KURMA_CEKILISLERI["kurma_oynaklik"][1]["azami_agirlik_carpani"]
        assert 0.0 not in KURMA_CEKILISLERI["kurma_turnover"][1]["turnover_bandi"]


class TestEksenCalisiyor:
    def test_carpan_ekseni_sonucu_gercekten_degistiriyor(self):
        """Dört çarpanın hepsi aynı sonucu verirse eksen ölüdür ve plato uydurur."""
        veri = _veri()
        hashler = {
            c: ed.kosu(
                EvrenOynaklikAgirlik(azami_agirlik_carpani=c, azami_enstruman=4,
                                     yeniden_dengele_bar=168, hedef_brut=HEDEF_BRUT),
                MALIYET, veri, _pencere(),
            ).sonuc_hash
            for c in KURMA_CEKILISLERI["kurma_oynaklik"][1]["azami_agirlik_carpani"]
        }
        assert len(set(hashler.values())) > 1, hashler

    def test_bant_yalnizca_surukleme_uzerinde_calisir(self):
        """Bant hedefi değil, **hedef ile mevcut arasındaki farkı** bastırır.

        Eşit ağırlıkta hedef sabittir (`hedef_brut / n`); fark yalnızca fiyat sürüklemesinden
        doğar. Bu yüzden bandın etkisi sürükleme büyüklüğüne bağlı ve sentetik fixture'da
        (bar başına ~%0,08 oynaklık) haftalık sürükleme en küçük banttan bile küçük kalıyor —
        orada bütün bant değerleri aynı sonucu veriyor. Ölçülen şey bir fixture özelliği,
        bandın özelliği değil; o yüzden bant burada doğrudan sınanıyor.
        """
        from scryne_quant.strategy.kurma import Aday, turnover_uygula

        hedefler = {"A": 0.05, "B": 0.05}
        adaylar = {
            "A": Aday(sembol="A", skor=2.0, oynaklik=0.01, mevcut_agirlik=0.058,
                      reason="TEST"),
            "B": Aday(sembol="B", skor=1.0, oynaklik=0.01, mevcut_agirlik=0.049,
                      reason="TEST"),
        }
        # Fark: A 0,008 · B 0,001.
        assert turnover_uygula(hedefler, adaylar, 0.0) == hedefler
        bantli = turnover_uygula(hedefler, adaylar, 0.002)
        assert bantli["A"] == pytest.approx(0.05)    # 0,008 > bant → dengelenir
        assert bantli["B"] == pytest.approx(0.049)   # 0,001 < bant → mevcut korunur
        hepsi = turnover_uygula(hedefler, adaylar, 0.01)
        assert hepsi == {"A": pytest.approx(0.058), "B": pytest.approx(0.049)}

    def test_bant_islem_sayisini_artirmaz(self):
        """Bant yalnızca bastırır; işlem sayısı bantla birlikte **artamaz**.

        Eşitlik de geçer: düşük sürüklemeli veride hiçbir dengeleme bastırılmaz.
        """
        veri = _veri()
        islem = [
            ed.kosu(
                EvrenTurnoverBandi(turnover_bandi=b, azami_enstruman=4,
                                   yeniden_dengele_bar=168, hedef_brut=HEDEF_BRUT),
                MALIYET, veri, _pencere(),
            ).metrikler.islem_sayisi
            for b in (0.0, 0.0025, 0.005, 0.01, 0.02)
        ]
        assert islem == sorted(islem, reverse=True), islem


class TestAgirlikDagitimi:
    def test_tavansiz_agirlik_bir_bolu_sigma_ile_orantili(self):
        from scryne_quant.strategy.kurma import Aday, agirliklar

        ayarlar = EvrenOynaklikAgirlik(
            azami_agirlik_carpani=10.0, azami_enstruman=3, hedef_brut=HEDEF_BRUT
        )._ayarlar
        adaylar = [
            Aday(sembol="A", skor=3.0, oynaklik=0.01, mevcut_agirlik=0.0, reason="TEST"),
            Aday(sembol="B", skor=2.0, oynaklik=0.02, mevcut_agirlik=0.0, reason="TEST"),
            Aday(sembol="C", skor=1.0, oynaklik=0.04, mevcut_agirlik=0.0, reason="TEST"),
        ]
        w = agirliklar(adaylar, ayarlar)
        assert w["A"] == pytest.approx(2 * w["B"], rel=1e-9)
        assert w["B"] == pytest.approx(2 * w["C"], rel=1e-9)
        assert sum(w.values()) == pytest.approx(HEDEF_BRUT, rel=1e-9)

    def test_carpan_tavani_gercekten_bagliyor(self):
        from scryne_quant.strategy.kurma import Aday, agirliklar

        ayarlar = EvrenOynaklikAgirlik(
            azami_agirlik_carpani=1.25, azami_enstruman=3, hedef_brut=HEDEF_BRUT
        )._ayarlar
        esit_pay = HEDEF_BRUT / 3
        adaylar = [
            Aday(sembol="A", skor=3.0, oynaklik=0.01, mevcut_agirlik=0.0, reason="TEST"),
            Aday(sembol="B", skor=2.0, oynaklik=0.02, mevcut_agirlik=0.0, reason="TEST"),
            Aday(sembol="C", skor=1.0, oynaklik=0.04, mevcut_agirlik=0.0, reason="TEST"),
        ]
        w = agirliklar(adaylar, ayarlar)
        assert w["A"] == pytest.approx(esit_pay * 1.25, rel=1e-9)
        assert max(w.values()) <= esit_pay * 1.25 + 1e-12

    def test_carpan_bir_altinda_reddediliyor(self):
        with pytest.raises(ValueError, match="azami_agirlik_carpani"):
            EvrenOynaklikAgirlik(azami_agirlik_carpani=0.9)

    def test_negatif_bant_reddediliyor(self):
        with pytest.raises(ValueError, match="turnover_bandi"):
            EvrenTurnoverBandi(turnover_bandi=-0.01)


class TestKayitTutarliligi:
    def test_cekilisler_programa_bagli_ve_aile_kayitli(self):
        for ad, (strateji, _) in KURMA_CEKILISLERI.items():
            assert cekilis_programi(ad) == "kurma_evren"
            assert evren_cekilisi(ad)[0] == strateji
            assert strateji in EVREN_AILELER
            assert strateji in SINYAL_OZELLIKLERI

    def test_izgaralar_on_iki_noktali(self):
        """Türev/konumlanma ile aynı biçim: K-058'in `pbo` eşiği 12 noktada kalibre edildi."""
        for ad, (_, g) in KURMA_CEKILISLERI.items():
            assert len(izgara_uret(g)) == 12, ad

    def test_kurma_kiyas_degil(self):
        """`EvrenEsitAgirlik.sozluk` 'kiyas: True' yazıyor; bunlar çekiliş."""
        assert EvrenOynaklikAgirlik().sozluk()["kiyas"] is False
        assert EvrenTurnoverBandi().sozluk()["kiyas"] is False
