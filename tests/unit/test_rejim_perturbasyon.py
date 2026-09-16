"""Rejim bölümlemesi ve parametre pertürbasyonu. (K-054, Faz 11)

İki kapının ölçüsü de basit görünüyor ve ikisinde de sessizce yanlış olmanın bir yolu var:

- **Rejim**: etiketi `t`nin kapanışıyla hesaplamak. O bar kazandıysa rejimi "yükselen"
  demek, kapanışı bilerek rejimi adlandırmaktır — look-ahead'in en kibar biçimi.
- **Pertürbasyon**: komşuyu "ızgarada iki eksende de yakın olan" diye tanımlamak. O
  hâlde bozulmanın hangi eksenden geldiği bilinemez.

Bu dosya ikisini de negatif kontrolle ölçüyor.
"""

from __future__ import annotations

import numpy as np
import pytest

from scryne_quant.research.perturbasyon import PerturbasyonHatasi, dusus_hesapla
from scryne_quant.research.rejim import (
    DUSEN,
    ISINMA,
    YUKSELEN,
    RejimHatasi,
    etiketle,
    olc,
)

YIL_BAR = 8766.0


def _kapanis(n: int = 1000, tohum: int = 0) -> np.ndarray:
    rng = np.random.default_rng(tohum)
    return 100.0 * np.cumprod(1.0 + rng.normal(0.0002, 0.01, n))


class TestRejimEtiketi:
    def test_isinma_bos_etiket(self):
        e = etiketle(_kapanis(300), pencere=100)
        assert list(e[:101]) == [ISINMA] * 101
        assert e[101] in (YUKSELEN, DUSEN)

    def test_yukselen_ve_dusen_ayirt_ediliyor(self):
        k = np.concatenate([np.linspace(100, 200, 600), np.linspace(200, 120, 600)])
        e = etiketle(k, pencere=200)
        assert e[400] == YUKSELEN
        assert e[1000] == DUSEN

    def test_etiket_nedensel(self):
        """`t` sonrası bozulunca `t`nin etiketi değişmemeli.

        Etiket `t−1`e kadarki pencereden hesaplanıyor; `t`nin kendi kapanışı bile dahil
        değil. Dahil olsaydı bar `t`de o barın getirisiyle rejimi adlandırmış olurduk.

        Karşılaştırma **ilk bozuk barı da kapsıyor** (`[:501]`, bozma 500'den başlıyor):
        nedensel ile hileli etiketleyici arasındaki fark tam olarak o tek bar. Daha dar
        bir pencerede test ikisini de geçirir ve hiçbir şey kanıtlamaz.
        """
        k = _kapanis(800)
        temiz = etiketle(k, pencere=200)
        bozuk_k = k.copy()
        bozuk_k[500:] = np.random.default_rng(9).uniform(1, 1e5, 300)
        bozuk = etiketle(bozuk_k, pencere=200)
        assert list(temiz[:501]) == list(bozuk[:501])

    def test_t_dahil_edilseydi_yakalanirdi(self):
        """Negatif kontrol: `t`yi dahil eden bir etiketleyici bozmayla değişirdi.

        Bozma **iki yönlü ve sabit** (çok yüksek / çok düşük), rastgele değil — Faz 2'nin
        ölçülmüş dersi: rastgele bozma tek barlık bir hileyi yazı-turayla yakalıyor,
        çünkü bozulan değer tesadüfen aynı kararı verebilir. İki yönden biri kararı
        kesinlikle çevirir.
        """
        k = _kapanis(800)

        def hileli(kapanis: np.ndarray, pencere: int) -> list[str]:
            # `t` dahil: t'nin kendi kapanışını kullanıyor.
            out = [ISINMA] * len(kapanis)
            for t in range(pencere, len(kapanis)):
                out[t] = YUKSELEN if kapanis[t] > kapanis[t - pencere] else DUSEN
            return out

        temiz_hileli = hileli(k, 200)[:501]
        temiz_nedensel = list(etiketle(k, pencere=200)[:501])
        yakalandi = False
        for deger in (1e-6, 1e9):
            bozuk_k = k.copy()
            bozuk_k[500:] = deger
            assert list(etiketle(bozuk_k, pencere=200)[:501]) == temiz_nedensel
            if hileli(bozuk_k, 200)[:501] != temiz_hileli:
                yakalandi = True
        assert yakalandi, "hileli etiketleyici hiçbir bozmayla yakalanamadı"

    def test_gecersiz_pencere(self):
        with pytest.raises(RejimHatasi, match="pencere"):
            etiketle(_kapanis(100), pencere=0)


class TestRejimOlcumu:
    def test_iki_rejim_ayri_olculuyor(self):
        k = np.concatenate([np.linspace(100, 200, 600), np.linspace(200, 120, 600)])
        e = etiketle(k, pencere=200)
        rng = np.random.default_rng(1)
        oz = 10_000 * np.cumprod(1 + rng.normal(0, 0.002, len(k)))
        o = olc(oz, e, yil_bar=YIL_BAR)
        assert set(o.rejimler) == {YUKSELEN, DUSEN}
        assert o.en_kotu_sharpe is not None
        assert o.en_kotu_rejim in (YUKSELEN, DUSEN)

    def test_tek_rejimli_ornek_olculemez(self):
        """Bir rejimi hiç görmeden 'rejimler arası kararlı' denemez (K-019)."""
        k = np.linspace(100, 300, 1200)  # sürekli yükselen
        e = etiketle(k, pencere=200)
        oz = 10_000 * np.cumprod(1 + np.random.default_rng(2).normal(0, 0.002, len(k)))
        o = olc(oz, e, yil_bar=YIL_BAR)
        assert o.en_kotu_sharpe is None
        assert DUSEN in o.olculemeyen

    def test_en_kotu_rejim_seciliyor(self):
        """Ölçü **en kötü** rejim; ortalama, kötü rejimi iyi rejimle gizlerdi."""
        n = 1200
        e = np.array([YUKSELEN] * (n // 2) + [DUSEN] * (n - n // 2), dtype=object)
        getiri = np.concatenate(
            [np.full(n // 2 - 1, 0.001), np.full(n - n // 2, -0.001)]
        )
        oz = 10_000 * np.cumprod(np.concatenate([[1.0], 1 + getiri]))
        o = olc(oz, e, yil_bar=YIL_BAR)
        assert o.en_kotu_rejim == DUSEN
        assert o.en_kotu_sharpe < 0

    def test_uzunluk_uyusmazligi_reddediliyor(self):
        with pytest.raises(RejimHatasi, match="aynı olmalı"):
            olc(np.ones(10), [YUKSELEN] * 5, yil_bar=YIL_BAR)


class TestPerturbasyon:
    def _izgara(self) -> list[dict[str, int]]:
        return [{"a": a, "b": b} for a in (1, 2, 3) for b in (10, 20, 30)]

    def test_izole_zirve_yuksek_dusus(self):
        skor = np.array([0.1, 0.2, 0.1, 0.2, 0.9, 0.2, 0.1, 0.2, 0.1])
        assert dusus_hesapla(self._izgara(), skor, 4) > 0.8

    def test_plato_dusuk_dusus(self):
        skor = np.array([0.5, 0.6, 0.65, 0.6, 0.7, 0.68, 0.65, 0.68, 0.66])
        assert dusus_hesapla(self._izgara(), skor, 4) < 0.3

    def test_komsu_tam_bir_eksende_bir_adim(self):
        """Çapraz komşu (iki eksende birden) sayılmaz."""
        skor = np.zeros(9)
        skor[4] = 1.0  # merkez
        # merkezin komşuları: (1,20),(3,20),(2,10),(2,30) — köşeler değil
        ps = self._izgara()
        dusus = dusus_hesapla(ps, skor, 4)
        # Dört komşunun hepsi 0 → medyan 0, aralık 1 → düşüş 1,0
        assert dusus == pytest.approx(1.0)

    def test_tek_noktali_eksen_komsuluk_uretmiyor(self):
        ps = [{"a": a, "sabit": 0.2} for a in (1, 2, 3)]
        skor = np.array([0.0, 1.0, 0.0])
        assert dusus_hesapla(ps, skor, 1) == pytest.approx(1.0)

    def test_komsusuz_nokta_olculemez(self):
        assert dusus_hesapla([{"a": 1}], np.array([1.0]), 0) is None

    def test_duz_izgara_olculemez(self):
        """Bütün skorlar aynıysa seçim diye bir şey yok; sıfır dönmek 'kusursuz plato'
        diye raporlamak olurdu."""
        assert dusus_hesapla(self._izgara(), np.ones(9), 4) is None

    def test_uzunluk_uyusmazligi_reddediliyor(self):
        with pytest.raises(PerturbasyonHatasi, match="aynı olmalı"):
            dusus_hesapla(self._izgara(), np.ones(5), 0)

    def test_negatif_skorlarda_da_tanimli(self):
        """Payda aralık, skorun kendisi değil: negatif Sharpe'ta işaret çevrilmiyor."""
        skor = np.array([-2.0, -1.5, -2.0, -1.5, -0.5, -1.5, -2.0, -1.5, -2.0])
        dusus = dusus_hesapla(self._izgara(), skor, 4)
        assert dusus is not None and dusus > 0.5
