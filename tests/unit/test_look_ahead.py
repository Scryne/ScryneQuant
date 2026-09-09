"""Look-ahead testi: `t` sonrası bozulduğunda sinyaller değişmez. (K-002, Faz 2)

Projedeki en önemli test bu. Look-ahead bias'ın maliyeti asimetriktir: backtest'te
sonucu iyileştirir, canlıda zarara çevirir — yani kendini fark ettirmeyen tek yönlü bir
hata. K-002 bu yüzden testi sözleşmenin ilk gününe koydu.

Ölçüm şu: veri setinin `t` sonrasındaki tamamı tanınmaz hâle getirilir, strateji baştan
`t`'ye kadar yeniden koşturulur, üretilen sinyaller **bit düzeyinde** karşılaştırılır.
Tek bir sinyalin tek bir alanı bile oynarsa geçmişe geleceğe bakan bir yol var demektir.

Testin kendisinin de kanıtlanması gerekiyor: `TestNegatifKontrol` kasten hile yapan bir
strateji yazıp bu testin onu **yakaladığını** gösteriyor. Hiçbir zaman kırmızıya
dönemeyen bir look-ahead testi, güvenlik değil tiyatrodur.
"""

from __future__ import annotations

import numpy as np
import pytest

from scryne_quant.features.barlar import bar_dizileri
from scryne_quant.strategy.baglam import GecmisYok, GelecekErisimi
from scryne_quant.strategy.kosu import gorunum_kur, sinyalleri_uret
from scryne_quant.strategy.kutuphane.sma_kesisim import SmaKesisim
from scryne_quant.strategy.sinyal import Sinyal, Yon
from scryne_quant.strategy.temel import Strateji
from tests.conftest import bar_uret

#: Kesme noktası. Isınma (yavaş SMA = 50) çoktan bitmiş, ama serinin sonuna kadar bol
#: miktarda bozulacak bar kalıyor.
KESME = 200
BAR_SAYISI = 600


def _girdi(tohum: int = 11) -> dict[str, np.ndarray]:
    return bar_dizileri(bar_uret(n=BAR_SAYISI, tohum=tohum))


def _boz_rastgele(diziler: dict[str, np.ndarray], t: int, tohum: int = 99):
    """`t`'den sonraki her fiyat ve hacmi tanınmaz rastgele değerlerle ezer.

    Bozma agresif: "biraz kaydır" bir look-ahead'i yakalamaya yetmeyebilir, çünkü küçük
    fark yuvarlanarak aynı sinyali üretebilir.
    """
    rng = np.random.default_rng(tohum)
    n = len(diziler["close"]) - (t + 1)
    bozuk = {ad: np.array(seri) for ad, seri in diziler.items()}
    for ad in ("open", "high", "low", "close"):
        bozuk[ad][t + 1 :] = rng.uniform(1.0, 90_000.0, n)
    bozuk["volume"][t + 1 :] = rng.uniform(0.0, 1e6, n)
    bozuk["quote_volume"][t + 1 :] = rng.uniform(0.0, 1e9, n)
    bozuk["trades"][t + 1 :] = rng.integers(0, 10_000, n)
    return bozuk


def _boz_sabit(diziler: dict[str, np.ndarray], t: int, fiyat: float):
    """`t`'den sonrasını tek bir uç fiyata sabitler."""
    bozuk = {ad: np.array(seri) for ad, seri in diziler.items()}
    for ad in ("open", "high", "low", "close"):
        bozuk[ad][t + 1 :] = fiyat
    bozuk["volume"][t + 1 :] = 0.0
    bozuk["quote_volume"][t + 1 :] = 0.0
    bozuk["trades"][t + 1 :] = 0
    return bozuk


#: Üç ayrı bozma. Tek bir bozmayla yetinmek testin **gücünü** düşürüyor: yalnızca bir bar
#: ileri bakan bir hile, kesme noktasındaki tek bir sinyali etkiler ve rastgele bozmanın
#: o sinyali gerçekten çevirmesi yazı-tura meselesidir. Ölçtük: rastgele bozma tek başına
#: `HileliStrateji`'yi kaçırdı. Uçtan uca iki yönlü sabit bozma (çok yüksek / çok düşük)
#: bu kaçışı kapatıyor — hangi yöne bakan hile olursa olsun en az birinde kararı çevirir.
BOZMALAR = (
    ("rastgele", lambda d, t: _boz_rastgele(d, t)),
    ("yukari", lambda d, t: _boz_sabit(d, t, 1e9)),
    ("asagi", lambda d, t: _boz_sabit(d, t, 1e-3)),
)


def _sinyaller_t_kadar(strateji: Strateji, diziler: dict[str, np.ndarray], t: int) -> list[str]:
    """Stratejiyi koşturur, `t` dahil olan sinyalleri kanonik JSON olarak döndürür.

    Karşılaştırma JSON metni üzerinden: `==` kayan noktada -0.0 ile 0.0'ı eşit sayar,
    metin saymaz. Ayrıca audit log'a giden gösterim de bu — testin baktığı şey ile
    kaydedilen şey aynı olmalı.
    """
    gorunum = gorunum_kur("BTCUSDT", "1h", diziler, strateji)
    sinir = int(diziler["open_time"][t])
    return [s.model_dump_json() for s in sinyalleri_uret(strateji, gorunum) if s.timestamp <= sinir]


class TestBozulmusGelecek:
    @pytest.mark.parametrize(("bozma_adi", "boz"), BOZMALAR)
    def test_sinyaller_bit_duzeyinde_ayni(self, bozma_adi: str, boz):
        temiz = _girdi()
        bozuk = boz(temiz, KESME)

        a = _sinyaller_t_kadar(SmaKesisim(20, 50), temiz, KESME)
        b = _sinyaller_t_kadar(SmaKesisim(20, 50), bozuk, KESME)

        assert a, "test anlamsız: kesme noktasına kadar hiç sinyal üretilmemiş"
        assert a == b, f"{bozma_adi} bozması sinyalleri değiştirdi"

    def test_hemen_sonraki_bar_bozulunca_da_ayni(self):
        """En sinsi durum: yalnızca `t+1`. Bir bar kayması burada yakalanır.

        Fill `t+1` açılışındadır (K-004) ama o fiyatı **strateji** görmez; gören taraf
        Faz 3'ün fill modelidir. Strateji `t+1`'i görüyorsa sözleşme kırılmıştır.
        """
        temiz = _girdi()
        bozuk = {ad: np.array(seri) for ad, seri in temiz.items()}
        for ad in ("open", "high", "low", "close", "volume"):
            bozuk[ad][KESME + 1] = 1.0

        assert _sinyaller_t_kadar(SmaKesisim(20, 50), temiz, KESME) == _sinyaller_t_kadar(
            SmaKesisim(20, 50), bozuk, KESME
        )

    @pytest.mark.parametrize("t", [60, 120, 200, 400, 598])
    @pytest.mark.parametrize(("bozma_adi", "boz"), BOZMALAR)
    def test_her_kesme_noktasinda_gecerli(self, bozma_adi: str, boz, t: int):
        temiz = _girdi()
        bozuk = boz(temiz, t)
        assert _sinyaller_t_kadar(SmaKesisim(20, 50), temiz, t) == _sinyaller_t_kadar(
            SmaKesisim(20, 50), bozuk, t
        ), f"{bozma_adi} bozması, kesme={t}"

    def test_ayni_girdi_ayni_cikti(self):
        """Determinizm (K-009): iki koşu aynı sinyalleri verir."""
        diziler = _girdi()
        a = _sinyaller_t_kadar(SmaKesisim(20, 50), diziler, KESME)
        b = _sinyaller_t_kadar(SmaKesisim(20, 50), diziler, KESME)
        assert a == b

    def test_ayni_ornekle_ikinci_kosu_ayni(self):
        """`hazirla()` durumu sıfırlıyor mu — aynı örnek iki kez koşturulunca."""
        diziler = _girdi()
        strateji = SmaKesisim(20, 50)
        a = _sinyaller_t_kadar(strateji, diziler, KESME)
        b = _sinyaller_t_kadar(strateji, diziler, KESME)
        assert a == b


class HileliStrateji(Strateji):
    """Kasten geleceğe bakar. **Üretimde kullanılmaz**; testin testi.

    `ctx`'in erişimcileri geleceği reddettiği için hile ancak özel alana uzanarak
    yapılabilir — yani sözleşmeyi bilerek delmek gerekir. Bu testin gösterdiği şey,
    birisi bir gün bunu yaptığında bozulmuş-gelecek testinin kırmızıya döneceği.
    """

    ad = "hileli"

    def ozellikler(self):
        return ()

    def on_bar(self, ctx):
        gelecek = ctx._gorunum.barlar["close"]
        i = ctx.uzunluk - 1
        if i + 1 >= len(gelecek):
            return None
        if gelecek[i + 1] > gelecek[i]:
            return Sinyal(
                symbol=ctx.sembol,
                side=Yon.BUY,
                target_exposure=0.2,
                confidence=1.0,
                reason="GELECEK_YUKSELIYOR",
                timestamp=ctx.zaman,
            )
        return None


class TestNegatifKontrol:
    """Testin testi. Bu sınıf yeşilse yukarıdaki yeşiller bir şey ifade ediyor demektir."""

    def test_hile_en_az_bir_bozmayla_yakalaniyor(self):
        """Üç bozmanın **en az biri** hileyi yakalamalı.

        "Hepsi yakalasın" demek yanlış olurdu ve bu ölçüldü: hile `close[t+1] > close[t]`
        soruyor; temiz seride cevabı "hayır" olan bir barda geleceği aşağı çekmek cevabı
        değiştirmez. Değiştiren, cevabı ters yöne zorlayan bozmadır. İki yönlü sabit
        bozmanın birlikte bulunmasının sebebi tam olarak bu: hangi yöne bakan hile olursa
        olsun, ikisinden biri kararı çevirir.
        """
        temiz = _girdi()
        temiz_sinyaller = _sinyaller_t_kadar(HileliStrateji(), temiz, KESME)

        yakalayan = [
            ad
            for ad, boz in BOZMALAR
            if _sinyaller_t_kadar(HileliStrateji(), boz(temiz, KESME), KESME) != temiz_sinyaller
        ]
        assert yakalayan, "hiçbir bozma bariz look-ahead'i yakalayamadı"

    def test_rastgele_bozma_tek_basina_yetersiz(self):
        """Ölçülmüş sınır: rastgele bozma, tek bar ileri bakan hileyi bu kesme noktasında
        **kaçırıyor** — riske giren tek sinyalin kararı tesadüfen aynı kalıyor.

        Bu test o zayıflığı belgeliyor; sabit yön bozmaları bu yüzden var. Bir gün burası
        kırmızıya dönerse yapılacak şey, testi silmek değil, üstteki gerekçeyi güncellemek.
        """
        temiz = _girdi()
        a = _sinyaller_t_kadar(HileliStrateji(), temiz, KESME)
        b = _sinyaller_t_kadar(HileliStrateji(), _boz_rastgele(temiz, KESME), KESME)
        assert a == b, "rastgele bozma artık yakalıyor — notu güncelle, zararı yok"


class TestErisimSozlesmesi:
    """Sonuca değil, sözleşmeye bakan testler: geleceğe uzanmak *ifade edilemez* olmalı."""

    def _ctx(self, i: int = 100):
        strateji = SmaKesisim(20, 50)
        return gorunum_kur("BTCUSDT", "1h", _girdi(), strateji).baglam(i)

    @pytest.mark.parametrize("geri", [-1, -5, -1000])
    def test_negatif_geri_gelecek_erisimidir(self, geri: int):
        ctx = self._ctx()
        with pytest.raises(GelecekErisimi):
            ctx.bar("close", geri)
        with pytest.raises(GelecekErisimi):
            ctx.ozellik("sma_hizli", geri)

    def test_isinma_oncesi_ayri_bir_hata(self):
        """Geçmişin yokluğu ile geleceğe uzanmak aynı hata değil; teşhis edilebilir kalmalı."""
        ctx = self._ctx(i=5)
        with pytest.raises(GecmisYok):
            ctx.bar("close", 10)

    def test_seri_kopya_dondurur(self):
        """Dilim döndürseydik `.base` üzerinden tüm seriye — yani geleceğe — yol açılırdı."""
        ctx = self._ctx()
        seri = ctx.bar_serisi("close", 10)
        assert seri.base is None
        assert seri.flags.owndata

    def test_seri_degistirmek_gorunumu_bozmuyor(self):
        ctx = self._ctx()
        seri = ctx.bar_serisi("close", 10)
        onceki = ctx.bar("close")
        seri[:] = -1.0
        assert ctx.bar("close") == onceki

    def test_gorunum_dizileri_yazilamaz(self):
        ctx = self._ctx()
        with pytest.raises(ValueError, match="read-only"):
            ctx._gorunum.barlar["close"][0] = 1.0
        with pytest.raises(ValueError, match="read-only"):
            ctx._gorunum.ozellikler["sma_hizli"][0] = 1.0

    def test_bool_geri_reddediliyor(self):
        """`ctx.bar("close", True)` sessizce `geri=1` olurdu — okuyanın anladığı bu değil."""
        ctx = self._ctx()
        with pytest.raises(TypeError):
            ctx.bar("close", True)
