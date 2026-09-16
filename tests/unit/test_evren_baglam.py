"""Evren `ctx`i: sözleşme ve **evren look-ahead** testi. (Faz 10, K-052/3)

`test_look_ahead.py` fiyat geleceğini ölçüyor; bu dosya ikinci biçimi ölçüyor: **hayatta
kalma geleceği.** `t` anında listelenmemiş ya da o ay evren kuralını sağlamayan bir
enstrümanın görünmesi, fiyat geleceğini görmek kadar ciddi bir look-ahead — ve çok daha
sessiz, çünkü sonucu iyileştirirken hiçbir kod yolu şikâyet etmez.

Ölçüm iki eksende birden bozuyor:

1. `t` sonrasındaki **fiyatlar** tanınmaz hâle getiriliyor.
2. `t` sonrasındaki **üyelik** tersine çevriliyor (üye olanlar çıkıyor, olmayanlar giriyor)
   ve bir sembolün listesi tamamen siliniyor (delist).

`t`ye kadarki kararlar bit düzeyinde aynı kalmalı. `TestNegatifKontrol` kasten evrenin
geleceğine bakan bir strateji yazıp bu testin onu **yakaladığını** gösteriyor: hiçbir zaman
kırmızıya dönemeyen bir look-ahead testi güvenlik değil tiyatrodur.
"""

from __future__ import annotations

import numpy as np
import pytest

from scryne_quant.data.semalar import KaliteDurumu
from scryne_quant.features.barlar import bar_dizileri
from scryne_quant.strategy.evren import (
    KARAR_VERILEBILIR,
    LISTELENMEDI,
    EvrenDisi,
    EvrenGorunumu,
    EvrenSozlesmesi,
)
from scryne_quant.strategy.hedef import hedef_kur
from scryne_quant.strategy.kosu import evren_gorunum_kur
from scryne_quant.strategy.sinyal import Sinyal, Yon
from scryne_quant.strategy.temel import PortfoyStratejisi
from tests.conftest import bar_uret

BAR_SAYISI = 300
KESME = 150
SEMBOLLER = ("AAAUSDT", "BBBUSDT", "CCCUSDT")


def _diziler(tohum_taban: int = 7) -> dict[str, dict[str, np.ndarray]]:
    return {
        sembol: bar_dizileri(bar_uret(n=BAR_SAYISI, tohum=tohum_taban + i))
        for i, sembol in enumerate(SEMBOLLER)
    }


def _uyelik() -> dict[str, np.ndarray]:
    """Zamanla değişen bir üyelik: AAA hep üye, BBB ilk yarı, CCC ikinci yarı."""
    n = BAR_SAYISI
    aaa = np.ones(n, dtype=bool)
    bbb = np.zeros(n, dtype=bool)
    bbb[: n // 2] = True
    ccc = np.zeros(n, dtype=bool)
    ccc[n // 2 :] = True
    return {"AAAUSDT": aaa, "BBBUSDT": bbb, "CCCUSDT": ccc}


class SiralayanStrateji(PortfoyStratejisi):
    """Her barda üyeleri kapanış fiyatına göre sıralayıp ilk ikisini eşit ağırlıkla tutar.

    Cross-sectional ailenin en sade hâli: karar **evrenin kimlerden oluştuğuna** bağlı.
    Look-ahead testinin ölçmek istediği tam olarak bu bağımlılık — evren değişirse karar
    değişmeli, evrenin *geleceği* değişirse değişmemeli.
    """

    ad = "siralayan"

    def ozellikler(self):
        return ()

    def on_bar(self, ctx):
        uyeler = ctx.uyeler()
        if not uyeler:
            return None
        sirali = sorted(uyeler, key=lambda s: (-ctx.enstruman(s).bar("close"), s))[:2]
        agirlik = 0.5 if len(sirali) > 1 else 1.0
        sinyaller = [
            Sinyal(
                symbol=s,
                side=Yon.BUY,
                target_exposure=agirlik,
                confidence=0.5,
                reason="EN_YUKSEK_KAPANIS",
                timestamp=ctx.zaman,
            )
            for s in sirali
        ]
        for s in ctx.acik_pozisyonlar():
            if s not in sirali and s in ctx.gorunur():
                sinyaller.append(
                    Sinyal(
                        symbol=s,
                        side=Yon.FLAT,
                        target_exposure=0.0,
                        confidence=0.0,
                        reason="SIRALAMADAN_DUSTU",
                        timestamp=ctx.zaman,
                    )
                )
        return hedef_kur(ctx.zaman, sinyaller)


def _kararlar_t_kadar(
    strateji: PortfoyStratejisi,
    diziler: dict[str, dict[str, np.ndarray]],
    uyelik: dict[str, np.ndarray],
    t: int,
) -> list[str]:
    """Stratejiyi evren akışında koşturur; `t` dahil hedefleri kanonik JSON olarak döndürür.

    Karşılaştırma metin üzerinden: `==` kayan noktada −0.0 ile 0.0'ı eşit sayar, metin
    saymaz — ve audit'e giden gösterim de bu.
    """
    strateji.hazirla()
    gorunum = evren_gorunum_kur("1h", diziler, uyelik, strateji)
    cikti: list[str] = []
    for i, ctx in enumerate(gorunum.akis(parametreler=strateji.parametreler)):
        if i > t:
            break
        hedef = strateji.on_bar(ctx)
        if hedef is not None:
            cikti.append(str(hedef.sozluk()))
    return cikti


def _boz_fiyat(diziler, t: int, tohum: int = 99):
    rng = np.random.default_rng(tohum)
    bozuk = {s: {a: np.array(d) for a, d in v.items()} for s, v in diziler.items()}
    n = BAR_SAYISI - (t + 1)
    for v in bozuk.values():
        for alan in ("open", "high", "low", "close"):
            v[alan][t + 1 :] = rng.uniform(1.0, 90_000.0, n)
        v["volume"][t + 1 :] = rng.uniform(0.0, 1e6, n)
        v["quote_volume"][t + 1 :] = rng.uniform(0.0, 1e9, n)
    return bozuk


def _boz_uyelik(uyelik: dict[str, np.ndarray], t: int) -> dict[str, np.ndarray]:
    """`t` sonrasındaki üyeliği tersine çevirir: giren çıkar, çıkan girer."""
    bozuk = {s: np.array(d) for s, d in uyelik.items()}
    for d in bozuk.values():
        d[t + 1 :] = ~d[t + 1 :]
    return bozuk


def _delist(diziler, uyelik, sembol: str, t: int):
    """`t` sonrasında bir sembolü tamamen siler: barları `listelenmedi`, üyeliği `False`."""
    yeni_d = {s: {a: np.array(d) for a, d in v.items()} for s, v in diziler.items()}
    yeni_u = {s: np.array(d) for s, d in uyelik.items()}
    for alan in ("open", "high", "low", "close", "volume", "quote_volume"):
        yeni_d[sembol][alan][t + 1 :] = np.nan
    yeni_d[sembol]["quality_status"] = np.array(
        yeni_d[sembol]["quality_status"], dtype=object
    )
    yeni_d[sembol]["quality_status"][t + 1 :] = LISTELENMEDI
    yeni_u[sembol][t + 1 :] = False
    return yeni_d, yeni_u


class TestEvrenLookAhead:
    """Bitti kriteri: `t` sonrası fiyat **ve** listeleme bilgisi bozulunca sonuç değişmez."""

    def test_fiyat_gelecegi_bozulunca_ayni(self):
        diziler, uyelik = _diziler(), _uyelik()
        a = _kararlar_t_kadar(SiralayanStrateji(), diziler, uyelik, KESME)
        b = _kararlar_t_kadar(SiralayanStrateji(), _boz_fiyat(diziler, KESME), uyelik, KESME)
        assert a, "test anlamsız: kesmeye kadar hiç hedef üretilmemiş"
        assert a == b

    @pytest.mark.parametrize("t", [30, 80, KESME, 220, 298])
    def test_uyelik_gelecegi_bozulunca_ayni(self, t: int):
        diziler, uyelik = _diziler(), _uyelik()
        a = _kararlar_t_kadar(SiralayanStrateji(), diziler, uyelik, t)
        b = _kararlar_t_kadar(SiralayanStrateji(), diziler, _boz_uyelik(uyelik, t), t)
        assert a == b, f"üyelik geleceği kararları değiştirdi (kesme={t})"

    def test_delist_gelecegi_bozulunca_ayni(self):
        """Bir sembol `t` sonrasında tamamen kaybolsa da `t`ye kadarki kararlar aynı.

        Bu, hayatta kalma yanlılığının doğrudan testi: bugünkü listeden kurulan bir evren,
        delist edilenleri geçmişte de yok sayardı ve sonuç iyileşirdi.
        """
        diziler, uyelik = _diziler(), _uyelik()
        a = _kararlar_t_kadar(SiralayanStrateji(), diziler, uyelik, KESME)
        d2, u2 = _delist(diziler, uyelik, "AAAUSDT", KESME)
        b = _kararlar_t_kadar(SiralayanStrateji(), d2, u2, KESME)
        assert a == b

    def test_hem_fiyat_hem_uyelik_bozulunca_ayni(self):
        diziler, uyelik = _diziler(), _uyelik()
        a = _kararlar_t_kadar(SiralayanStrateji(), diziler, uyelik, KESME)
        b = _kararlar_t_kadar(
            SiralayanStrateji(),
            _boz_fiyat(diziler, KESME),
            _boz_uyelik(uyelik, KESME),
            KESME,
        )
        assert a == b

    def test_uyelik_gecmisi_degisince_karar_degisiyor(self):
        """Testin anlamlı olduğunun kanıtı: evren **geçmişi** değişirse karar değişmeli.

        Aksi hâlde yukarıdaki dört test, evreni hiç okumayan bir stratejiyle de yeşil
        olurdu.
        """
        diziler, uyelik = _diziler(), _uyelik()
        a = _kararlar_t_kadar(SiralayanStrateji(), diziler, uyelik, KESME)
        degisik = {s: np.array(d) for s, d in uyelik.items()}
        degisik["CCCUSDT"][:] = True
        b = _kararlar_t_kadar(SiralayanStrateji(), diziler, degisik, KESME)
        assert a != b


class GelecegeBakanEvrenStratejisi(PortfoyStratejisi):
    """Kasten evrenin **geleceğine** bakar. Üretimde kullanılmaz; testin testi.

    `ctx` bunu ifade edilemez kılıyor, bu yüzden hile ancak özel alana uzanarak
    yapılabilir — yani sözleşmeyi bilerek delmek gerekir.
    """

    ad = "gelecege_bakan"

    def ozellikler(self):
        return ()

    def on_bar(self, ctx):
        i = ctx.uzunluk - 1
        gorunum = ctx._gorunum
        ileri = min(i + 1, len(gorunum) - 1)
        gelecek_uyeler = [s for s in gorunum.semboller if bool(gorunum.uyelik[s][ileri])]
        if not gelecek_uyeler:
            return None
        sembol = sorted(gelecek_uyeler)[0]
        return hedef_kur(
            ctx.zaman,
            [
                Sinyal(
                    symbol=sembol,
                    side=Yon.BUY,
                    target_exposure=0.5,
                    confidence=1.0,
                    reason="YARIN_UYE_OLACAK",
                    timestamp=ctx.zaman,
                )
            ],
        )


class TestNegatifKontrol:
    """Bu sınıf yeşilse yukarıdaki yeşiller bir şey ifade ediyor demektir."""

    def test_evren_hilesi_yakalaniyor(self):
        diziler, uyelik = _diziler(), _uyelik()
        temiz = _kararlar_t_kadar(GelecegeBakanEvrenStratejisi(), diziler, uyelik, KESME)
        bozuk = _kararlar_t_kadar(
            GelecegeBakanEvrenStratejisi(), diziler, _boz_uyelik(uyelik, KESME), KESME
        )
        assert temiz != bozuk, "bariz evren look-ahead'i yakalanamadı"


class TestSozlesme:
    """Sonuca değil sözleşmeye bakan testler."""

    def test_uye_olmayan_enstruman_gorunmuyor(self):
        diziler, uyelik = _diziler(), _uyelik()
        gorunum = evren_gorunum_kur("1h", diziler, uyelik, SiralayanStrateji())
        ctx = gorunum.baglam(0)
        assert ctx.uyeler() == ("AAAUSDT", "BBBUSDT")
        with pytest.raises(EvrenDisi, match="evren üyesi değil"):
            ctx.enstruman("CCCUSDT")

    def test_acik_pozisyon_uye_olmasa_da_gorunur(self):
        """Evrenden çıkan enstrümanı göremeyen strateji pozisyonunu kapatamaz.

        Bu bir look-ahead değil: zaten sahip olduğun şeyi görmek gelecek bilgisi değildir.
        Seçmek olurdu — ve `uyeler()` hâlâ yalnızca üyeleri döndürüyor.
        """
        from scryne_quant.strategy.baglam import PozisyonDurumu

        diziler, uyelik = _diziler(), _uyelik()
        gorunum = evren_gorunum_kur("1h", diziler, uyelik, SiralayanStrateji())
        ctx = gorunum.baglam(0, {"CCCUSDT": PozisyonDurumu(miktar=1.0, ortalama_maliyet=10.0)})
        assert "CCCUSDT" not in ctx.uyeler()
        assert "CCCUSDT" in ctx.gorunur()
        assert ctx.enstruman("CCCUSDT").bar("close") > 0

    def test_ok_olmayan_barda_enstruman_gorunmuyor(self):
        """K-028: `ok` olmayan barda ne karar verilir ne fill yapılır."""
        diziler, uyelik = _diziler(), _uyelik()
        diziler["AAAUSDT"]["quality_status"] = np.array(
            diziler["AAAUSDT"]["quality_status"], dtype=object
        )
        diziler["AAAUSDT"]["quality_status"][5] = KaliteDurumu.SUSPECT
        gorunum = evren_gorunum_kur("1h", diziler, uyelik, SiralayanStrateji())
        assert "AAAUSDT" in gorunum.baglam(4).uyeler()
        assert "AAAUSDT" not in gorunum.baglam(5).uyeler()

    def test_karar_verilebilir_sabiti_kalite_enumuyla_ayni(self):
        """`strategy/` `data/`yi import edemez (K-027); iki sabitin aynı kaldığı burada tutulur."""
        assert str(KaliteDurumu.OK) == KARAR_VERILEBILIR

    def test_listelenmemis_barda_uyelik_reddediliyor(self):
        diziler, uyelik = _diziler(), _uyelik()
        d2, u2 = _delist(diziler, uyelik, "BBBUSDT", KESME)
        u2["BBBUSDT"][KESME + 10] = True  # olmayan barda üyelik iddiası
        with pytest.raises(EvrenSozlesmesi, match="listelenmemiş barda evren üyeliği"):
            evren_gorunum_kur("1h", d2, u2, SiralayanStrateji())

    def test_eksik_uyelik_reddediliyor(self):
        diziler, uyelik = _diziler(), _uyelik()
        del uyelik["CCCUSDT"]
        with pytest.raises(EvrenSozlesmesi, match="üyelik dizisi olmalı"):
            evren_gorunum_kur("1h", diziler, uyelik, SiralayanStrateji())

    def test_izgara_disi_sembol_reddediliyor(self):
        diziler, uyelik = _diziler(), _uyelik()
        kisa = {a: d[:-5] for a, d in diziler["CCCUSDT"].items()}
        diziler["CCCUSDT"] = kisa
        uyelik["CCCUSDT"] = uyelik["CCCUSDT"][:-5]
        with pytest.raises(EvrenSozlesmesi):
            evren_gorunum_kur("1h", diziler, uyelik, SiralayanStrateji())

    def test_bos_evren_reddediliyor(self):
        with pytest.raises(EvrenSozlesmesi, match="en az bir enstrüman"):
            EvrenGorunumu(
                timeframe="1h",
                zamanlar=np.array([1, 2], dtype="int64"),
                gorunumler={},
                uyelik={},
            )
