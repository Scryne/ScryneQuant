"""Gölge motoru: karar üretmez, kayıt üretir; replay ile aynı durum hash'i. (K-074/1, /5, /6)"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import numpy as np
import pytest

from scryne_quant.features.barlar import bar_dizileri
from scryne_quant.jev import ayarlar as ayar_mod
from scryne_quant.jev.defter import JevDefteri, OlayTuru
from scryne_quant.jev.durum import PENCERE_BAR
from scryne_quant.jev.golge import GolgeHatasi, GolgeKosturucu, GolgeMotoru
from scryne_quant.jev.tekrar import tekrar_kos
from scryne_quant.live.akis import Bar, Kaynak
from tests.conftest import bar_uret

SAAT = 3_600_000
N = PENCERE_BAR + 30
ISINMA = PENCERE_BAR + 5  # ısınma barı sayısı (BACKFILL); kalanı "canlı" (AKIS)


class _Cevap:
    def __init__(self, **k: Any) -> None:
        self.__dict__.update(k)


def _yanit(model: str = "jev-1.13.0", long: float = 0.7) -> Any:
    y = _Cevap()
    y.model = model
    y.usage = _Cevap(input_tokens=1500, output_tokens=120)
    y.answers = {
        "yon": _Cevap(
            choice="long",
            confidence=0.6,
            probabilities={"long": long, "short": 0.05, "flat": round(0.95 - long, 2)},
        ),
        "rejim": _Cevap(
            choice="trend_yukari",
            confidence=0.5,
            probabilities={
                "trend_yukari": 0.6,
                "trend_asagi": 0.05,
                "aralik": 0.15,
                "yuksek_volatilite": 0.05,
                "belirsiz": 0.15,
            },
        ),
        "kurulum": _Cevap(score=1.6, confidence=0.5),
        "cekimser": _Cevap(noul=0.2),
    }
    return y


class _SahteIstemci:
    def __init__(self) -> None:
        self.cagri = 0
        self.hata: BaseException | None = None
        self.long = 0.7

    def system_one(self, state, questions, *, model=None):
        self.cagri += 1
        if self.hata is not None:
            raise self.hata
        return _yanit(long=self.long)


class _SahteAkis:
    def __init__(self, barlar: list[Bar]) -> None:
        self._barlar = barlar
        self.kapali = False

    @property
    def sembol(self) -> str:
        return "BTCUSDT"

    @property
    def timeframe(self) -> str:
        return "1h"

    def kapat(self) -> None:
        self.kapali = True

    async def barlar(self) -> AsyncIterator[Bar]:
        for b in self._barlar:
            if self.kapali:
                return
            yield b


def _barlar(kaynak: Kaynak, df) -> list[Bar]:
    return [
        Bar(
            open_time=int(r.open_time),
            open=float(r.open),
            high=float(r.high),
            low=float(r.low),
            close=float(r.close),
            volume=float(r.volume),
            quote_volume=float(r.quote_volume),
            trades=int(r.trades),
            kaynak=kaynak,
        )
        for r in df.itertuples()
    ]


@pytest.fixture
def ayar():
    return ayar_mod.yukle()


@pytest.fixture
def df():
    return bar_uret(n=N, tohum=21)


@pytest.fixture
def saat():
    class _S:
        def __init__(self) -> None:
            self.an = 1_700_000_000_000

        def __call__(self) -> int:
            return self.an

    return _S()


def _motor(ayar, saat, istemci=None, defter=None, funding_kaynagi=None):
    return GolgeMotoru(
        kosu="golge-test",
        ayarlar=ayar,
        defter=defter or JevDefteri(),
        istemci=istemci or _SahteIstemci(),
        funding_kaynagi=funding_kaynagi,
        saat=saat,
    )


def _canli_bar_isle(m, bar, saat):
    """Barın kapanışından 90 s sonra 'işlenmiş' gibi duvar saatini ayarlar."""
    saat.an = bar.open_time + SAAT + 90_000
    return m.bar_isle(bar)


class TestBarIsle:
    def test_isinma_backfill_olmali(self, ayar, saat, df):
        m = _motor(ayar, saat)
        with pytest.raises(GolgeHatasi):
            m.isinma(_barlar(Kaynak.AKIS, df.iloc[:5]))

    def test_pencere_eksikken_karar_yok(self, ayar, saat, df):
        m = _motor(ayar, saat)
        m.isinma(_barlar(Kaynak.BACKFILL, df.iloc[:100]))
        s = _canli_bar_isle(m, _barlar(Kaynak.AKIS, df.iloc[100:101])[0], saat)
        assert not s.islendi and "pencere eksik" in s.sebep and s.karar is None
        assert m.istemci.cagri == 0
        assert m.defter.olaylar(tur=OlayTuru.BAR_ATLANDI)

    def test_tam_pencerede_karar_yazilir(self, ayar, saat, df):
        m = _motor(ayar, saat)
        m.isinma(_barlar(Kaynak.BACKFILL, df.iloc[:ISINMA]))
        bar = _barlar(Kaynak.AKIS, df.iloc[ISINMA : ISINMA + 1])[0]
        s = _canli_bar_isle(m, bar, saat)
        assert s.islendi and s.karar is not None and s.karar.gecerli
        assert s.karar.yon.value == "long" and s.karar.ileriye_donuk and not s.karar.leak_riski
        assert s.karar.karar_ms == bar.open_time
        assert m.defter.sayim() == {"gecerli": 1} and m.defter.dogrula()
        satir = m.defter.kararlar()[0]
        assert satir["durum"]["kalite"] == {"karar_bari": "ok", "karar_bari_ok": True}
        assert satir["yanit"]["model"] == "jev-1.13.0"

    def test_backfilled_karar_bari_atlanir(self, ayar, saat, df):
        m = _motor(ayar, saat)
        m.isinma(_barlar(Kaynak.BACKFILL, df.iloc[:ISINMA]))
        bar = _barlar(Kaynak.BACKFILL, df.iloc[ISINMA : ISINMA + 1])[0]
        s = _canli_bar_isle(m, bar, saat)
        assert not s.islendi and "ok değil" in s.sebep and m.istemci.cagri == 0

    def test_revizyon_karar_uretmez(self, ayar, saat, df):
        m = _motor(ayar, saat)
        m.isinma(_barlar(Kaynak.BACKFILL, df.iloc[:ISINMA]))
        bar = _barlar(Kaynak.AKIS, df.iloc[ISINMA : ISINMA + 1])[0]
        _canli_bar_isle(m, bar, saat)
        s = m.bar_isle(bar)
        assert not s.islendi and s.sebep == "revizyon" and m.istemci.cagri == 1

    def test_hata_fail_closed_kayit(self, ayar, saat, df):
        ist = _SahteIstemci()
        ist.hata = TimeoutError("yavaş")
        m = _motor(ayar, saat, istemci=ist)
        m.isinma(_barlar(Kaynak.BACKFILL, df.iloc[:ISINMA]))
        bar = _barlar(Kaynak.AKIS, df.iloc[ISINMA : ISINMA + 1])[0]
        s = _canli_bar_isle(m, bar, saat)
        assert s.islendi and s.karar is not None and not s.karar.gecerli
        assert s.karar.durum.value == "timeout" and s.karar.yon is None
        assert m.defter.sayim() == {"timeout": 1}
        # Sonraki bar hata geçince önceki kararsızlık taşınmaz: yeni karar kendi cevabı
        ist.hata = None
        bar2 = _barlar(Kaynak.AKIS, df.iloc[ISINMA + 1 : ISINMA + 2])[0]
        s2 = _canli_bar_isle(m, bar2, saat)
        assert s2.karar.gecerli and m.defter.sayim() == {"timeout": 1, "gecerli": 1}

    def test_bayat_uretim_gecersiz(self, ayar, saat, df):
        m = _motor(ayar, saat)
        m.isinma(_barlar(Kaynak.BACKFILL, df.iloc[:ISINMA]))
        bar = _barlar(Kaynak.AKIS, df.iloc[ISINMA : ISINMA + 1])[0]
        saat.an = bar.open_time + SAAT + ayar.bayat_ms + 1
        s = m.bar_isle(bar)
        assert s.karar.durum.value == "bayat_durum" and not s.karar.ileriye_donuk

    def test_tutarlilik_her_n_kararda(self, ayar, saat, df):
        m = _motor(ayar, saat)
        m.isinma(_barlar(Kaynak.BACKFILL, df.iloc[:ISINMA]))
        n = ayar.tutarlilik_her_n_karar
        canli = _barlar(Kaynak.AKIS, df.iloc[ISINMA : ISINMA + n])
        for b in canli:
            _canli_bar_isle(m, b, saat)
        assert m.istemci.cagri == n + 1  # n karar + 1 tutarlılık sorgusu
        t = m.defter.olaylar(tur=OlayTuru.TUTARLILIK)
        assert len(t) == 1 and t[0]["ayrinti"]["yon_sapma"] == pytest.approx(0.0)
        assert m.defter.sayim() == {"gecerli": n}

    def test_funding_tazeleme_ve_hata(self, ayar, saat, df):
        cagrilar: list[tuple[str, int]] = []

        def kaynak(sembol, bas):
            cagrilar.append((sembol, bas))
            if len(cagrilar) == 2:
                raise ConnectionError("fapi")
            t0 = int(df.open_time.iloc[0]) // (8 * SAAT) * 8 * SAAT
            return [(t0 + k * 8 * SAAT, 0.0001) for k in range(400) if t0 + k * 8 * SAAT >= bas]

        m = _motor(ayar, saat, funding_kaynagi=kaynak)
        m.isinma(_barlar(Kaynak.BACKFILL, df.iloc[:ISINMA]))
        canli = _barlar(Kaynak.AKIS, df.iloc[ISINMA : ISINMA + 2])
        s1 = _canli_bar_isle(m, canli[0], saat)
        s2 = _canli_bar_isle(m, canli[1], saat)
        assert cagrilar[0][0] == "BTCUSDT"
        assert s1.karar.gecerli and s2.karar.gecerli
        assert m.defter.kararlar()[0]["durum"]["funding"]["durum"] == "guncel"
        assert m.defter.olaylar(tur=OlayTuru.BAYAT_VERI)[0]["ayrinti"]["kaynak"] == "funding"
        # İkinci çağrı hata verdi ama eldeki seri kullanıldı
        assert m.defter.kararlar()[1]["durum"]["funding"]["durum"] == "guncel"


class TestReplayEsitligi:
    """Spec §38: tek state builder. Gölge ve replay aynı bar için aynı durum hash'ini üretir."""

    def test_golge_ve_tekrar_ayni_hash(self, ayar, saat, df):
        m = _motor(ayar, saat)
        m.isinma(_barlar(Kaynak.BACKFILL, df.iloc[:ISINMA]))
        canli = _barlar(Kaynak.AKIS, df.iloc[ISINMA:])
        for b in canli:
            _canli_bar_isle(m, b, saat)
        golge = {s["karar_ms"]: s["durum_hash"] for s in m.defter.kararlar()}

        diziler = bar_dizileri(df)  # replay: Parquet'teki gibi hepsi `ok`
        with JevDefteri() as d2:
            tekrar_kos(
                diziler,
                ayarlar=ayar,
                defter=d2,
                kosu="tekrar-esitlik",
                ilk=ISINMA,
                son=N - 1,
                istemci=None,
                saat=saat,
            )
            tekrar = {s["karar_ms"]: s["durum_hash"] for s in d2.kararlar()}
        assert golge and golge == tekrar

    def test_gecmis_bar_bozulunca_golge_hashi_degismez(self, ayar, saat, df):
        """Pencere dışında kalan geçmiş, canlı durumu etkilemez (PENCERE_BAR sözleşmesi)."""
        bozuk = df.copy()
        bozuk.loc[: N - PENCERE_BAR - 10, ["open", "high", "low", "close"]] *= 3.0
        h = []
        for veri in (df, bozuk):
            m = _motor(ayar, saat)
            m.isinma(_barlar(Kaynak.BACKFILL, veri.iloc[:ISINMA]))
            son = _barlar(Kaynak.AKIS, veri.iloc[N - 1 : N])[0]
            # pencere kapasitesi aşıldığında en eski barlar düşer; son bar aynı
            for b in _barlar(Kaynak.AKIS, veri.iloc[ISINMA : N - 1]):
                _canli_bar_isle(m, b, saat)
            s = _canli_bar_isle(m, son, saat)
            h.append(s.karar.durum_hash)
        assert h[0] == h[1]


class TestKosturucu:
    def test_akis_bitince_durur_ve_olay_yazar(self, ayar, saat, df):
        m = _motor(ayar, saat)
        m.isinma(_barlar(Kaynak.BACKFILL, df.iloc[:ISINMA]))
        canli = _barlar(Kaynak.AKIS, df.iloc[ISINMA : ISINMA + 3])
        saat.an = canli[-1].open_time + SAAT + 60_000
        sonuclar = []
        k = GolgeKosturucu(m, _SahteAkis(canli), bar_kancasi=sonuclar.append)
        ozet = asyncio.run(k.calistir())
        assert ozet["islenen_bar"] == 3 and ozet["hata"] is None and len(sonuclar) == 3
        turler = [o["tur"] for o in m.defter.olaylar()]
        assert turler[0] == "basladi" and turler[-1] == "durdu"

    def test_durdurma_istegi_periyodik_yoklanir(self, ayar, saat, df):
        """Bar gelmese de bayrak yoklanır ve koşu durur (1h barda bir saat beklenmez)."""
        m = _motor(ayar, saat)
        m.isinma(_barlar(Kaynak.BACKFILL, df.iloc[:ISINMA]))

        class _BeklemeAkisi(_SahteAkis):
            async def barlar(self):
                yield self._barlar[0]
                while not self.kapali:
                    await asyncio.sleep(0.01)

        canli = _barlar(Kaynak.AKIS, df.iloc[ISINMA : ISINMA + 1])
        saat.an = canli[0].open_time + SAAT + 60_000
        k = GolgeKosturucu(
            m,
            _BeklemeAkisi(canli),
            durdurma_istegi=lambda: {"sebep": "test"},
            yoklama_araligi_s=0.02,
        )
        ozet = asyncio.run(asyncio.wait_for(k.calistir(), timeout=5))
        assert ozet["islenen_bar"] == 1
        durdu = m.defter.olaylar(tur=OlayTuru.DURDU)[-1]["ayrinti"]
        assert durdu["sebep"] == "istek" and durdu["istek"] == {"sebep": "test"}

    def test_hata_kaydedilir_ve_yukselir(self, ayar, saat, df):
        m = _motor(ayar, saat)
        m.isinma(_barlar(Kaynak.BACKFILL, df.iloc[:ISINMA]))
        geri = _barlar(Kaynak.AKIS, df.iloc[ISINMA - 3 : ISINMA - 2])  # akış geriye gitti
        k = GolgeKosturucu(m, _SahteAkis(geri))
        with pytest.raises(Exception, match="geriye"):
            asyncio.run(k.calistir())
        assert m.defter.olaylar(tur=OlayTuru.HATA)


def test_kanonik_durum_numpy_disi_tip_icermiyor(ayar, saat, df):
    m = _motor(ayar, saat)
    m.isinma(_barlar(Kaynak.BACKFILL, df.iloc[:ISINMA]))
    s = _canli_bar_isle(m, _barlar(Kaynak.AKIS, df.iloc[ISINMA : ISINMA + 1])[0], saat)
    durum = m.defter.durum_bul(s.karar.durum_hash)

    def _tara(x):
        if isinstance(x, dict):
            return all(_tara(v) for v in x.values())
        if isinstance(x, list):
            return all(_tara(v) for v in x)
        return not isinstance(x, np.generic | np.ndarray)

    assert _tara(durum)


def test_durum_json_her_barda_yaziliyor(ayar, saat, df, tmp_path):
    """Pano bu dosyayı okur; `jev` import etmez. Alanlar sözleşme (K-074)."""
    import json

    yol = tmp_path / "golge-x.sqlite"
    m = _motor(ayar, saat, defter=JevDefteri(yol))
    m.isinma(_barlar(Kaynak.BACKFILL, df.iloc[:ISINMA]))
    durum_yolu = tmp_path / "golge-x.sqlite.durum.json"
    d0 = json.loads(durum_yolu.read_text(encoding="utf-8"))
    assert d0["toplam"] == 0 and d0["son_karar"] is None and d0["kanit"] is False
    s = _canli_bar_isle(m, _barlar(Kaynak.AKIS, df.iloc[ISINMA : ISINMA + 1])[0], saat)
    d1 = json.loads(durum_yolu.read_text(encoding="utf-8"))
    assert d1["toplam"] == 1 and d1["gecerli"] == 1 and d1["zincir_gecerli"] is True
    assert d1["son_karar"]["yon"] == "long" and d1["son_karar"]["karar_ms"] == s.bar_ms
    assert d1["yon_dagilimi"] == {"long": 1} and d1["cekimserlik_orani"] == 0.0
    assert d1["mod"] == "golge" and d1["yazildi_ms"] == saat.an
    assert not (tmp_path / "golge-x.sqlite.durum.json.tmp").exists()
