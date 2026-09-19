"""Kanonik durum: determinizm, byte-identical sızıntı, PIT, 4h kapanış. (K-074/4, spec §15)

Bu dosyanın en önemli testi `TestSizinti`: karar barı `i` sonrası **bozulduğunda ve
silindiğinde** kanonik JSON byte düzeyinde aynı kalıyor mu. `test_look_ahead.py`nin kalıbı
(üç bozma + negatif kontrol) aynen alındı; fark, ölçülen nesnenin sinyal dizisi değil durumun
kendisi olması. Negatif kontrol şart: hiç kırmızıya dönemeyen bir sızıntı testi tiyatrodur.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable

import numpy as np
import pytest

from scryne_quant.common.zaman import timeframe_ms
from scryne_quant.data import funding as funding_mod
from scryne_quant.features.barlar import bar_dizileri
from scryne_quant.jev import durum as durum_mod
from scryne_quant.jev.durum import (
    BAYAT,
    EKSIK,
    FUNDING_BAYAT_MS,
    GUNCEL,
    PENCERE_BAR,
    DurumHatasi,
    durum_hash,
    kanonik_durum,
    kanonik_json,
    kapanmis_4h,
)
from tests.conftest import bar_uret

SAAT = timeframe_ms("1h")
BAR_SAYISI = 1_500
#: Kesme noktaları: ısınma bitmiş, sonrasında bol bozulacak bar var; biri 4h kova sonuna,
#: biri kova ortasına denk geliyor.
KESMELER = (900, 903, 1_100, 1_299)


def _diziler(tohum: int = 11, n: int = BAR_SAYISI) -> dict[str, np.ndarray]:
    return bar_dizileri(bar_uret(n=n, tohum=tohum))


def _funding(diziler: dict[str, np.ndarray], tohum: int = 5) -> tuple[np.ndarray, np.ndarray]:
    """8 saatlik ızgarada, bar serisinin başından sonuna (ve biraz ötesine) funding."""
    rng = np.random.default_rng(tohum)
    bas = (int(diziler["open_time"][0]) // (8 * SAAT)) * 8 * SAAT
    son = int(diziler["open_time"][-1]) + 8 * SAAT
    z = np.arange(bas, son + 1, 8 * SAAT, dtype=np.int64)
    return z, rng.normal(0.0001, 0.0002, z.size)


def _kur(diziler, i, funding=None, sembol="BTCUSDT"):
    if funding is None:
        return kanonik_durum(diziler, i, sembol=sembol)
    return kanonik_durum(
        diziler, i, sembol=sembol, funding_time_ms=funding[0], funding_rate=funding[1]
    )


# ------------------------------------------------------------------ bozma araçları


def _boz_rastgele(diziler, t, tohum=99):
    rng = np.random.default_rng(tohum)
    n = len(diziler["close"]) - (t + 1)
    bozuk = {ad: np.array(seri) for ad, seri in diziler.items()}
    for ad in ("open", "high", "low", "close"):
        bozuk[ad][t + 1 :] = rng.uniform(1.0, 90_000.0, n)
    bozuk["volume"][t + 1 :] = rng.uniform(0.0, 1e6, n)
    bozuk["quality_status"] = np.array(diziler["quality_status"], dtype=object)
    bozuk["quality_status"][t + 1 :] = "suspect"
    return bozuk


def _boz_sabit(diziler, t, fiyat):
    bozuk = {ad: np.array(seri) for ad, seri in diziler.items()}
    for ad in ("open", "high", "low", "close"):
        bozuk[ad][t + 1 :] = fiyat
    return bozuk


def _sil(diziler, t):
    """`t` sonrasını **siler**: spec §15'in "görünmez/silinmiş" adımı."""
    return {ad: np.array(seri[: t + 1]) for ad, seri in diziler.items()}


BOZMALAR: tuple[tuple[str, Callable], ...] = (
    ("rastgele", lambda d, t: _boz_rastgele(d, t)),
    ("yukari", lambda d, t: _boz_sabit(d, t, 1e9)),
    ("asagi", lambda d, t: _boz_sabit(d, t, 1e-3)),
    ("silme", _sil),
)


def _funding_boz(funding, t_ms):
    """`t` sonrası funding oranlarını ezer ve zamanını korur; ayrıca bir de siler."""
    z, r = funding
    bozuk = np.array(r)
    bozuk[z > t_ms] = 0.0029  # tavana yakın uç değer
    return z, bozuk


def _funding_sil(funding, t_ms):
    z, r = funding
    m = z <= t_ms
    return z[m], r[m]


# ------------------------------------------------------------------ determinizm


class TestDeterminizm:
    def test_ayni_girdi_ayni_bytes_ve_hash(self):
        d = _diziler()
        f = _funding(d)
        ilk = kanonik_json(_kur(d, 1_000, f))
        for _ in range(10):
            assert kanonik_json(_kur(d, 1_000, f)) == ilk
        assert durum_hash(_kur(d, 1_000, f)) == durum_hash(_kur(d, 1_000, f))

    def test_hash_kanonik_jsonun_sha256si(self):
        import hashlib

        s = _kur(_diziler(), 1_000)
        assert durum_hash(s) == hashlib.sha256(kanonik_json(s)).hexdigest()

    def test_json_nan_icermez_ve_numpy_tipi_yok(self):
        s = _kur(_diziler(), 1_000, _funding(_diziler()))
        metin = kanonik_json(s).decode()
        assert "NaN" not in metin and "Infinity" not in metin
        yeniden = json.loads(metin)
        assert yeniden == s  # numpy skaler olsaydı eşitlik/round-trip bozulurdu

    def test_farkli_bar_farkli_hash(self):
        d = _diziler()
        assert durum_hash(_kur(d, 1_000)) != durum_hash(_kur(d, 1_001))

    def test_zaman_alanlari(self):
        d = _diziler()
        s = _kur(d, 1_000)
        assert s["karar_ms"] == int(d["open_time"][1_000])
        assert s["veri_kesimi_ms"] == s["karar_ms"] + SAAT
        assert s["kaynak_kesimleri"]["bar_ms"] == s["veri_kesimi_ms"]
        assert s["surum"] == durum_mod.DURUM_SURUMU
        assert s["karar_utc"].endswith("UTC")

    def test_pencere_disi_gecmis_etkisiz(self):
        """Replay (tam seri) ile canlı (sınırlı pencere) aynı hash'i vermeli (K-074/4)."""
        d = _diziler()
        i = 1_400
        tam = _kur(d, i)
        kesik = {k: v[i - PENCERE_BAR + 1 : i + 1] for k, v in d.items()}
        assert kanonik_json(_kur(kesik, PENCERE_BAR - 1)) == kanonik_json(tam)
        # Pencere öncesine bir bar daha eklemek de değiştirmemeli
        bir_fazla = {k: v[i - PENCERE_BAR : i + 1] for k, v in d.items()}
        assert kanonik_json(_kur(bir_fazla, PENCERE_BAR)) == kanonik_json(tam)


# ------------------------------------------------------------------ sızıntı


class TestSizinti:
    """Spec §15: t sonrası bozulunca/silinince snapshot byte-identical."""

    @pytest.mark.parametrize("bozma_adi,boz", BOZMALAR, ids=[b[0] for b in BOZMALAR])
    @pytest.mark.parametrize("t", KESMELER)
    def test_bar_bozma_ve_silme_byte_identical(self, bozma_adi, boz, t):
        d = _diziler()
        f = _funding(d)
        a = kanonik_json(_kur(d, t, f))
        b = kanonik_json(_kur(boz(d, t), t, f))
        assert a == b, f"{bozma_adi} bozması t={t} durumunu değiştirdi"

    @pytest.mark.parametrize("t", KESMELER)
    def test_hemen_sonraki_bar_bozulunca_da_ayni(self, t):
        d = _diziler()
        bozuk = {ad: np.array(seri) for ad, seri in d.items()}
        for ad in ("open", "high", "low", "close"):
            bozuk[ad][t + 1] = 1e9
        assert kanonik_json(_kur(bozuk, t)) == kanonik_json(_kur(d, t))

    @pytest.mark.parametrize("t", KESMELER)
    def test_gelecek_funding_bozulunca_ve_silinince_ayni(self, t):
        d = _diziler()
        f = _funding(d)
        t_ms = int(d["open_time"][t])
        a = kanonik_json(_kur(d, t, f))
        assert kanonik_json(_kur(d, t, _funding_boz(f, t_ms))) == a
        assert kanonik_json(_kur(d, t, _funding_sil(f, t_ms))) == a

    def test_funding_kesme_kurali_karar_barinin_acilisi(self):
        """`funding_time ≤ karar_ms` görünür; 1 ms sonrası görünmez (K-042/4 ile aynı kural)."""
        d = _diziler()
        t = 1_000
        t_ms = int(d["open_time"][t])
        z = np.array([t_ms - 8 * SAAT, t_ms, t_ms + 1], dtype=np.int64)
        r = np.array([0.0001, 0.0020, 0.0029])
        s = _kur(d, t, (z, r))
        assert s["funding"]["son_odeme_ms"] == t_ms
        assert s["funding"]["son_oran_yuzde"] == pytest.approx(0.20)
        assert s["kaynak_kesimleri"]["funding_ms"] == t_ms

    def test_test_anlamsiz_degil(self):
        """Bozma gerçekten `t` sonrasını değiştiriyor: `t+1`de kurulan durum farklı çıkmalı."""
        d = _diziler()
        t = 1_000
        assert kanonik_json(_kur(_boz_sabit(d, t, 1e9), t + 1)) != kanonik_json(_kur(d, t + 1))


class TestNegatifKontrol:
    """Kasıtlı sızdıran bir kurucu, aynı testle **yakalanmalı**."""

    @staticmethod
    def _sizdiran(diziler, i, **kw):
        s = kanonik_durum(diziler, i, **kw)
        # Hile: bir sonraki barın kapanışını "momentum" diye duruma sokar.
        if i + 1 < len(diziler["close"]):
            s["1h"]["hile"] = float(diziler["close"][i + 1])
        return s

    def test_hile_en_az_bir_bozmayla_yakalaniyor(self):
        d = _diziler()
        t = 1_000
        temiz = kanonik_json(self._sizdiran(d, t, sembol="BTCUSDT"))
        yakalandi = [
            kanonik_json(self._sizdiran(boz(d, t), t, sembol="BTCUSDT")) != temiz
            for _, boz in BOZMALAR
            if _ != "silme"
        ]
        assert any(yakalandi)

    def test_silme_hileyi_yapisal_olarak_yakalar(self):
        """Silme sonrası geleceğe erişim indeks hatası ya da farklı bytes olmalı."""
        d = _diziler()
        t = 1_000
        temiz = kanonik_json(self._sizdiran(d, t, sembol="BTCUSDT"))
        assert kanonik_json(self._sizdiran(_sil(d, t), t, sembol="BTCUSDT")) != temiz


# ------------------------------------------------------------------ 4h kapanış


class TestKapanmis4h:
    def test_kova_yalnizca_kapanmissa_girer(self):
        d = _diziler()
        adim4 = timeframe_ms("4h")
        for i in KESMELER:
            kesim = int(d["open_time"][i]) + SAAT
            d4, _ = kapanmis_4h(d, i, veri_kesimi_ms=kesim)
            assert d4["open_time"].size > 0
            assert int(d4["open_time"][-1]) + adim4 <= kesim
            # Bir sonraki kova kapanmamış olmalı: onun açılışı + 4h > kesim
            assert int(d4["open_time"][-1]) + 2 * adim4 > kesim

    def test_kova_sonundaki_bar_kovayi_kapatir(self):
        """`t` kovanın 4. saatiyse o kova karar anında kapanmıştır ve görünür."""
        d = _diziler()
        adim4 = timeframe_ms("4h")
        # Kova sonu: (open_time + 1h) % 4h == 0 olan ilk bar 1_000'den sonra
        i = next(k for k in range(1_000, 1_100) if (int(d["open_time"][k]) + SAAT) % adim4 == 0)
        s_son = _kur(d, i)
        s_onceki = _kur(d, i - 1)
        assert s_son["4h_kapanmis"]["son_kova_ms"] == (int(d["open_time"][i]) // adim4) * adim4
        assert s_onceki["4h_kapanmis"]["son_kova_ms"] == s_son["4h_kapanmis"]["son_kova_ms"] - adim4

    def test_ohlc_toplama_dogru(self):
        d = _diziler()
        i = 1_000
        d4, _ = kapanmis_4h(d, i, veri_kesimi_ms=int(d["open_time"][i]) + SAAT)
        adim4 = timeframe_ms("4h")
        b = int(d4["open_time"][-1])
        m = (d["open_time"] >= b) & (d["open_time"] < b + adim4)
        assert d4["open"][-1] == d["open"][m][0]
        assert d4["close"][-1] == d["close"][m][-1]
        assert d4["high"][-1] == d["high"][m].max()
        assert d4["low"][-1] == d["low"][m].min()

    def test_ok_olmayan_bar_kovayi_dusurur(self):
        d = _diziler()
        i = 1_000
        kesim = int(d["open_time"][i]) + SAAT
        temiz, eksik0 = kapanmis_4h(d, i, veri_kesimi_ms=kesim)
        bozuk = {k: np.array(v) for k, v in d.items()}
        bozuk["quality_status"] = np.array(d["quality_status"], dtype=object)
        bozuk["quality_status"][i - 10] = "gap"
        kirli, eksik1 = kapanmis_4h(bozuk, i, veri_kesimi_ms=kesim)
        assert eksik1 == eksik0 + 1
        assert kirli["open_time"].size == temiz["open_time"].size - 1
        # Düşen kova uydurulmadı: kalan kovalar temiz kümenin alt kümesi
        assert set(kirli["open_time"]) < set(temiz["open_time"])

    def test_backfilled_bar_kovayi_dusurmez(self):
        """Isınma barları REST'ten `backfilled` gelir; replay ile eşitlik için kovaya girer."""
        d = _diziler()
        i = 1_000
        kesim = int(d["open_time"][i]) + SAAT
        temiz, e0 = kapanmis_4h(d, i, veri_kesimi_ms=kesim)
        geri = {k: np.array(v) for k, v in d.items()}
        geri["quality_status"] = np.array(d["quality_status"], dtype=object)
        geri["quality_status"][: i - 5] = "backfilled"
        dolu, e1 = kapanmis_4h(geri, i, veri_kesimi_ms=kesim)
        assert e1 == e0 and np.array_equal(dolu["close"], temiz["close"])
        assert kanonik_json(_kur(geri, i)) == kanonik_json(_kur(d, i))

    def test_eksik_bar_kovayi_dusurur(self):
        d = _diziler()
        i = 1_000
        # i-10. barı seriden çıkar (boşluk)
        m = np.ones(len(d["open_time"]), dtype=bool)
        m[i - 10] = False
        eksikli = {k: np.array(v)[m] for k, v in d.items()}
        kesim = int(d["open_time"][i]) + SAAT
        temiz, e0 = kapanmis_4h(d, i, veri_kesimi_ms=kesim)
        kirli, e1 = kapanmis_4h(eksikli, i - 1, veri_kesimi_ms=kesim)
        assert e1 == e0 + 1
        assert kirli["open_time"].size == temiz["open_time"].size - 1


# ------------------------------------------------------------------ eksik / bayat


class TestEksikVeBayat:
    def test_isinma_eksik_etiketi(self):
        s = _kur(_diziler(n=30), 5)
        assert s["1h"]["rsi14"] == EKSIK
        assert s["1h"]["ema50_ema200"] == EKSIK
        assert s["1h"]["yapi"] == EKSIK
        assert s["4h_kapanmis"]["kapanis_ema20"] == EKSIK

    def test_funding_yoksa_eksik(self):
        s = _kur(_diziler(), 1_000)
        assert s["funding"] == {"veri": EKSIK}
        assert s["kaynak_kesimleri"]["funding_ms"] is None

    def test_funding_bayat_etiketi(self):
        d = _diziler()
        t = 1_000
        t_ms = int(d["open_time"][t])
        z = np.array([t_ms - FUNDING_BAYAT_MS - 1], dtype=np.int64)
        s = _kur(d, t, (z, np.array([0.0001])))
        assert s["funding"]["durum"] == BAYAT
        z = np.array([t_ms - FUNDING_BAYAT_MS], dtype=np.int64)
        assert _kur(d, t, (z, np.array([0.0001])))["funding"]["durum"] == GUNCEL

    def test_bayat_siniri_data_funding_ile_ayni(self):
        assert FUNDING_BAYAT_MS == funding_mod.BAYAT_MS

    def test_sifir_asla_eksik_anlamina_gelmez(self):
        """Spec §56: durumda 'yok' anlamında 0 bulunmaz; eksik alanlar etiketlidir."""
        s = _kur(_diziler(n=30), 5)
        for blok in ("1h", "4h_kapanmis"):
            for ad, deger in s[blok].items():
                if ad in ("bar_sayisi", "eksik_kova", "son_kova_ms"):
                    continue
                assert deger != 0, f"{blok}.{ad} sıfır — eksik mi, gerçekten sıfır mı belirsiz"

    def test_karar_bari_ok_degilse_kalite_bloguna_yazilir(self):
        d = _diziler()
        bozuk = {k: np.array(v) for k, v in d.items()}
        bozuk["quality_status"] = np.array(d["quality_status"], dtype=object)
        bozuk["quality_status"][1_000] = "backfilled"
        s = _kur(bozuk, 1_000)
        assert s["kalite"] == {"karar_bari": "backfilled", "karar_bari_ok": False}


# ------------------------------------------------------------------ hatalar


class TestHatalar:
    def test_eksik_alan(self):
        d = _diziler()
        d.pop("high")
        with pytest.raises(DurumHatasi):
            _kur(d, 100)

    def test_indeks_araligi(self):
        d = _diziler(n=50)
        with pytest.raises(DurumHatasi):
            _kur(d, 50)
        with pytest.raises(DurumHatasi):
            _kur(d, -1)

    def test_hizasiz_bar(self):
        d = _diziler()
        d = {k: np.array(v) for k, v in d.items()}
        d["open_time"] = d["open_time"] + 1
        with pytest.raises(DurumHatasi):
            _kur(d, 100)

    def test_funding_sirasiz(self):
        d = _diziler()
        z = np.array([2_000_000_000_000, 1_999_999_000_000], dtype=np.int64)
        with pytest.raises(DurumHatasi):
            _kur(d, 100, (z, np.array([0.0, 0.0])))

    def test_yuvarlama_eksi_sifir_uretmez(self):
        assert math.copysign(1.0, durum_mod._yuvarla(-0.001)) == 1.0
