"""Her limit için bir ihlal senaryosu. (§11, K-032, K-033, Roadmap Faz 5 bitti kriteri)

Roadmap şunu istiyor: *"Her limit için ihlal senaryosu testi var ve doğru davranıyor."*
Bu dosya sekiz limitin her biri için o senaryoyu kuruyor — ve her vakada **iki** şeyi
birlikte ölçüyor:

1. Limit aşıldığında doğru davranış (red veya kısıtlama).
2. Limit aşılmadığında **onay** — yani limitin her zaman reddeden bir duvar olmadığı.

İkincisi olmadan test boştur: `return Red(...)` yazan bir motor birinci grubun tamamını
geçer. Faz 3'ün dersi (fill barının açılışı ile kapanışının aynı sayı seçilmesi yüzünden
hiçbir şey kanıtlamayan K-004 testi) tam olarak buydu.

**Sınır vakaları ayrı test ediliyor.** Bir limitin "tam sınırda" ne yaptığı bir tercihtir
ve yazılı olmak zorunda: bu motorda sınır **dahil** geçer (`>` ile kontrol), çünkü
"drawdown tam %20" bir ihlal değil, limitin kendisidir.
"""

from __future__ import annotations

import pytest

from scryne_quant.risk import limitler as limit_mod
from scryne_quant.risk.durum import RiskDurumu
from scryne_quant.risk.motor import PiyasaOlcumu, RiskHatasi, RiskMotoru
from scryne_quant.risk.niyet import OnayliNiyet, Red, RedSebebi
from scryne_quant.risk.promotion import Asama
from scryne_quant.strategy.sinyal import Sinyal, Yon

BAR = 3_600_000
T0 = 1_700_006_400_000  # 1h ızgarasına hizalı


def _gerekceler() -> dict[str, limit_mod.Gerekce]:
    """Test limitleri için asgari gerekçe kümesi.

    Ölçülmüş olmak zorunda olan üç limit (`limitler.py`'deki tutarlılık kontrolü)
    `olculdu` işaretli ve sahte bir `veri_sha256` taşıyor — testin konusu gerekçe
    doğrulaması değil, limitin davranışı.
    """
    olculdu = ("ters_hareket_atr_carpani", "volatilite_esigi", "gunluk_zarar_limiti")
    return {
        ad: limit_mod.Gerekce(
            kaynak="olculdu" if ad in olculdu else "istah",
            metin=f"test limiti: {ad}",
            veri_sha256="0" * 64 if ad in olculdu else "",
            gozden_gecirme="" if ad in olculdu else "test",
        )
        for ad in limit_mod.LIMIT_ADLARI
    }


def limitler(**degisiklik) -> limit_mod.RiskLimitleri:
    """Test limitleri. Sayılar yuvarlak — okunabilirlik için, gerçeklik için değil."""
    alanlar = {
        "azami_maruziyet": 0.30,
        "islem_basina_risk": 0.005,
        "ters_hareket_atr_carpani": 5.0,
        "gunluk_zarar_limiti": 0.02,
        "drawdown_limiti": 0.20,
        "ardisik_kayip_limiti": 3,
        "cooldown_bar": 4,
        "volatilite_esigi": 0.02,
        "gerekceler": _gerekceler(),
    }
    return limit_mod.RiskLimitleri(**(alanlar | degisiklik))


def motor(**degisiklik) -> RiskMotoru:
    mod = degisiklik.pop("mod", "backtest")
    asamalar = degisiklik.pop("asamalar", None)
    durum = degisiklik.pop("durum", None)
    return RiskMotoru(
        limitler(**degisiklik), "1h", mod=mod, durum=durum, asamalar=asamalar
    )


def sinyal(hedef: float = 0.30, yon: Yon = Yon.BUY, zaman: int = T0) -> Sinyal:
    return Sinyal(
        symbol="BTCUSDT",
        side=yon,
        target_exposure=hedef,
        confidence=0.9,
        reason="TEST",
        timestamp=zaman,
    )


def olcum(
    *,
    fiyat: float = 30_000.0,
    ozkaynak: float = 10_000.0,
    maruziyet: float = 0.0,
    bar_ms: int = T0,
    atr_oran: float | None = 0.005,
) -> PiyasaOlcumu:
    """Ölçüm kurucu. `atr_oran` doğrudan veriliyor; ATR fiyattan türetiliyor."""
    return PiyasaOlcumu(
        fiyat=fiyat,
        ozkaynak=ozkaynak,
        mevcut_maruziyet=maruziyet,
        bar_ms=bar_ms,
        atr=None if atr_oran is None else fiyat * atr_oran,
    )


# --------------------------------------------------------------- azami maruziyet


class TestAzamiMaruziyet:
    def test_hedef_tavana_cekilir(self):
        m = motor(islem_basina_risk=1.0)  # sizing devre dışı kalsın
        karar = m.degerlendir(sinyal(1.0), olcum())
        assert isinstance(karar, OnayliNiyet)
        assert karar.onayli_maruziyet == pytest.approx(0.30)
        assert "azami_maruziyet" in karar.kisitlayan

    def test_tavanin_altindaki_hedefe_dokunulmaz(self):
        """Limitin her zaman kısıtlamadığının kanıtı."""
        m = motor(islem_basina_risk=1.0)
        karar = m.degerlendir(sinyal(0.10), olcum())
        assert isinstance(karar, OnayliNiyet)
        assert karar.onayli_maruziyet == pytest.approx(0.10)
        assert karar.kisitlayan == ()

    def test_tavan_asla_yukari_cekmez(self):
        """Hedef tavandan küçükse risk onu **büyütmez** — K-032'nin tek yönlü kuralı."""
        m = motor(azami_maruziyet=0.9, islem_basina_risk=1.0)
        karar = m.degerlendir(sinyal(0.05), olcum())
        assert isinstance(karar, OnayliNiyet)
        assert karar.onayli_maruziyet == pytest.approx(0.05)


# ------------------------------------------------------------- işlem başına risk


class TestIslemBasinaRisk:
    def test_volatilite_arttikca_tavan_daralir(self):
        """Aynı risk bütçesi, yüksek volatilitede küçük pozisyon.

        Tavan = risk / (çarpan × ATR/fiyat). ATR/fiyat ikiye katlandığında tavan yarıya
        iner; bu testin ölçtüğü şey formülün yönü, sayının kendisi değil.
        """
        m = motor()
        sakin = m.degerlendir(sinyal(1.0), olcum(atr_oran=0.005))
        calkantili = m.degerlendir(sinyal(1.0), olcum(atr_oran=0.010))
        assert isinstance(sakin, OnayliNiyet) and isinstance(calkantili, OnayliNiyet)
        assert calkantili.onayli_maruziyet == pytest.approx(sakin.onayli_maruziyet / 2)

    def test_tavan_formulu(self):
        """0,005 / (5,0 × 0,005) = 0,20 — azami maruziyetin (0,30) altında, yani bağlayıcı."""
        karar = motor().degerlendir(sinyal(1.0), olcum(atr_oran=0.005))
        assert isinstance(karar, OnayliNiyet)
        assert karar.onayli_maruziyet == pytest.approx(0.20)
        assert karar.kisitlayan == ("azami_maruziyet", "islem_basina_risk")

    def test_baglayici_olmadiginda_kisitlamaz(self):
        """Risk bütçesi bol olduğunda tavan devreye girmiyor."""
        karar = motor(islem_basina_risk=0.5).degerlendir(sinyal(0.10), olcum())
        assert isinstance(karar, OnayliNiyet)
        assert "islem_basina_risk" not in karar.kisitlayan

    def test_asiri_volatilitede_sifira_inen_hedef_reddedilir(self):
        """Tavan ölçülebilir bir sıfıra inerse sinyal reddedilir, sıfır büyüklükte
        onaylanmaz: sıfır boyutlu bir onay execution'a gönderilecek bir emir üretmez ama
        audit'te "onaylandı" diye görünür ve sayım yanlış olur."""
        m = motor(islem_basina_risk=1e-12, volatilite_esigi=1.0)
        karar = m.degerlendir(sinyal(1.0), olcum(atr_oran=0.5))
        assert isinstance(karar, Red)
        assert karar.sebep is RedSebebi.SIFIR_BOYUT


# --------------------------------------------------------------- günlük zarar


class TestGunlukZarar:
    def test_limit_asilinca_yeni_giris_yok(self):
        m = motor()
        m.bar_isle(T0, 10_000.0)
        m.bar_isle(T0 + BAR, 9_700.0)  # gün içinde −%3, limit %2
        karar = m.degerlendir(sinyal(), olcum(bar_ms=T0 + BAR, ozkaynak=9_700.0))
        assert isinstance(karar, Red)
        assert karar.sebep is RedSebebi.GUNLUK_ZARAR
        assert karar.ayrinti["gunluk_getiri"] == pytest.approx(-0.03)

    def test_limitin_altinda_onay(self):
        m = motor()
        m.bar_isle(T0, 10_000.0)
        m.bar_isle(T0 + BAR, 9_900.0)  # −%1
        assert isinstance(
            m.degerlendir(sinyal(), olcum(bar_ms=T0 + BAR, ozkaynak=9_900.0)), OnayliNiyet
        )

    def test_tam_sinirda_gecer(self):
        """Sınır dahil: "günlük zarar tam %2" bir ihlal değil, limitin kendisi."""
        m = motor()
        m.bar_isle(T0, 10_000.0)
        m.bar_isle(T0 + BAR, 9_800.0)  # tam −%2
        assert isinstance(
            m.degerlendir(sinyal(), olcum(bar_ms=T0 + BAR, ozkaynak=9_800.0)), OnayliNiyet
        )

    def test_gun_donumunde_limit_kalkar(self):
        """Günlük zarar geçici bir durdurmadır — gün dönümünde kendiliğinden kalkar.

        Drawdown'dan farkı bu: biri fren, diğeri birikmiş hasar.
        """
        m = motor()
        m.bar_isle(T0, 10_000.0)
        m.bar_isle(T0 + BAR, 9_000.0)
        assert isinstance(m.degerlendir(sinyal(), olcum(bar_ms=T0 + BAR)), Red)

        yarin = T0 + 86_400_000
        m.bar_isle(yarin, 9_000.0)  # yeni gün: taban 9.000'e sıfırlandı
        assert isinstance(
            m.degerlendir(sinyal(), olcum(bar_ms=yarin, ozkaynak=9_000.0)), OnayliNiyet
        )

    def test_gun_donumu_ozkaynaktan_once(self):
        """Gün tabanı, yeni günün **ilk** barının özkaynağı olmak zorunda.

        Ters sırada o barın zararı önceki güne yazılır ve her gün bir barlık kayma
        birikir — sessiz, makul görünen, gittikçe büyüyen bir hata.
        """
        d = RiskDurumu()
        d.bar_isle(T0, 10_000.0)
        yarin = T0 + 86_400_000
        d.bar_isle(yarin, 9_500.0)
        assert d.gun_basi_ozkaynak == 9_500.0
        assert d.gunluk_getiri == pytest.approx(0.0)


# ------------------------------------------------------------------- drawdown


class TestDrawdown:
    def test_limit_asilinca_kill_switch(self):
        """Drawdown limiti bir fren değil **kontak kapatma**: SAFE_MODE açılıyor."""
        m = motor()
        m.bar_isle(T0, 10_000.0)
        yarin = T0 + 86_400_000
        m.bar_isle(yarin, 7_500.0)  # zirveden −%25, limit %20 (gün tabanı sıfırlandı)
        karar = m.degerlendir(sinyal(), olcum(bar_ms=yarin, ozkaynak=7_500.0))
        assert isinstance(karar, Red)
        assert karar.sebep is RedSebebi.DRAWDOWN
        assert m.durum.safe_mode is True
        assert m.durum.safe_mode_sebep == "DRAWDOWN_LIMITI"

    def test_limitin_altinda_onay(self):
        """Düşüş **ayrı bir günde**: aynı barda olsaydı günlük zarar limiti önce tetiklenir.

        Testi ilk hâlinde bu tuzağa düştü ve ölçmek istediği şeyi ölçmedi — iki limitin
        aynı vakada tetiklendiği bir senaryo, hangisinin çalıştığını söylemez.
        """
        m = motor()
        m.bar_isle(T0, 10_000.0)
        yarin = T0 + 86_400_000
        m.bar_isle(yarin, 8_500.0)  # zirveden −%15, gün tabanı da 8.500'e sıfırlandı
        assert isinstance(
            m.degerlendir(sinyal(), olcum(bar_ms=yarin, ozkaynak=8_500.0)), OnayliNiyet
        )
        assert m.durum.safe_mode is False

    def test_tam_sinirda_gecer(self):
        """Tam −%20 bir ihlal değil, limitin kendisi.

        Bu testin geçmesi kayan nokta karşılaştırmasının çarpmayla yapılmasına bağlı:
        `1 - 8000/10000` 0,19999999999999996 verir ve limiti aşmış görünür.
        """
        m = motor()
        m.bar_isle(T0, 10_000.0)
        yarin = T0 + 86_400_000
        m.bar_isle(yarin, 8_000.0)  # tam −%20
        assert isinstance(
            m.degerlendir(sinyal(), olcum(bar_ms=yarin, ozkaynak=8_000.0)), OnayliNiyet
        )

    def test_gun_donumu_drawdowni_kaldirmaz(self):
        """Drawdown birikmiş hasardır; gün dönümü onu affetmez."""
        m = motor()
        m.bar_isle(T0, 10_000.0)
        yarin = T0 + 86_400_000
        m.bar_isle(yarin, 7_000.0)
        m.degerlendir(sinyal(), olcum(bar_ms=yarin, ozkaynak=7_000.0))
        m.bar_isle(yarin + 86_400_000, 7_000.0)
        assert m.durum.drawdown == pytest.approx(0.30)
        assert m.durum.safe_mode is True

    def test_zirve_dusmez(self):
        """Zirve yalnızca yükselir: düşmesi drawdown'ı sıfırlamanın sessiz yolu olurdu."""
        d = RiskDurumu()
        d.bar_isle(T0, 12_000.0)
        d.bar_isle(T0 + BAR, 9_000.0)
        d.bar_isle(T0 + 2 * BAR, 10_000.0)
        assert d.zirve_ozkaynak == 12_000.0


# ------------------------------------------------------------------- cooldown


class TestCooldown:
    def test_ardisik_kayip_cooldown_tetikler(self):
        m = motor()  # limit 3 kayıp, cooldown 4 bar
        for i in range(2):
            assert m.islem_kapandi(-10.0, T0 + i * BAR) is False
        assert m.islem_kapandi(-10.0, T0 + 2 * BAR) is True
        assert m.durum.cooldown_bitis_ms == T0 + 2 * BAR + 4 * BAR

    def test_cooldownda_yeni_giris_yok(self):
        m = motor()
        m.bar_isle(T0, 10_000.0)
        for i in range(3):
            m.islem_kapandi(-10.0, T0 + i * BAR)
        karar = m.degerlendir(sinyal(), olcum(bar_ms=T0 + 3 * BAR))
        assert isinstance(karar, Red)
        assert karar.sebep is RedSebebi.COOLDOWN
        assert karar.ayrinti["kalan_bar"] == 3

    def test_cooldown_bitince_onay(self):
        m = motor()
        m.bar_isle(T0, 10_000.0)
        for i in range(3):
            m.islem_kapandi(-10.0, T0 + i * BAR)
        bitis = m.durum.cooldown_bitis_ms
        assert isinstance(m.degerlendir(sinyal(), olcum(bar_ms=bitis)), OnayliNiyet)

    def test_kazanan_islem_sayaci_sifirlar(self):
        m = motor()
        m.islem_kapandi(-10.0, T0)
        m.islem_kapandi(-10.0, T0 + BAR)
        m.islem_kapandi(+10.0, T0 + 2 * BAR)
        assert m.durum.ardisik_kayip == 0
        assert m.islem_kapandi(-10.0, T0 + 3 * BAR) is False  # sayaç baştan

    def test_basabas_islem_kayip_sayilir(self):
        """Bir tur maliyetini ödedikten sonra tam sıfırda kapanan işlem kazanmamıştır.

        Kazanç sayılsaydı sayacı sıfırlar ve cooldown'ı sessizce geciktirirdi.
        """
        m = motor()
        m.islem_kapandi(0.0, T0)
        assert m.durum.ardisik_kayip == 1

    def test_cooldown_sonrasi_limit_yeniden_tam(self):
        """Cooldown bitince sayaç sıfırdan başlar; aksi hâlde limit 3'ten 1'e düşerdi."""
        m = motor()
        for i in range(3):
            m.islem_kapandi(-10.0, T0 + i * BAR)
        assert m.durum.ardisik_kayip == 0
        assert m.islem_kapandi(-10.0, T0 + 10 * BAR) is False
        assert m.islem_kapandi(-10.0, T0 + 11 * BAR) is False
        assert m.islem_kapandi(-10.0, T0 + 12 * BAR) is True


# ----------------------------------------------------------------- volatilite


class TestVolatiliteGuard:
    def test_esigin_ustunde_red(self):
        m = motor()
        karar = m.degerlendir(sinyal(), olcum(atr_oran=0.03))  # eşik %2
        assert isinstance(karar, Red)
        assert karar.sebep is RedSebebi.VOLATILITE
        assert karar.ayrinti["atr_oran"] == pytest.approx(0.03)

    def test_esigin_altinda_onay(self):
        assert isinstance(motor().degerlendir(sinyal(), olcum(atr_oran=0.01)), OnayliNiyet)

    def test_tam_esikte_gecer(self):
        assert isinstance(motor().degerlendir(sinyal(), olcum(atr_oran=0.02)), OnayliNiyet)

    def test_olculemeyen_volatilite_reddedilir(self):
        """Ölçülemeyen guard geçilmiş sayılmaz — ve sıfır sayılmaz.

        ATR yoksa `atr=0` varsaymak guard'ı geçirir **ve** boyut tavanını sonsuz yapardı:
        tek bir eksik ölçüm, iki limiti birden sessizce kaldırır.
        """
        karar = motor().degerlendir(sinyal(), olcum(atr_oran=None))
        assert isinstance(karar, Red)
        assert karar.sebep is RedSebebi.VOLATILITE_OLCULEMEDI


# ------------------------------------------------------------- azaltan niyetler


class TestAzaltanNiyetler:
    """Bir çıkışı engellemek riski azaltmaz, artırır. (K-008/3'ün genel hâli)"""

    @pytest.mark.parametrize(
        ("yon", "hedef"), [(Yon.FLAT, 0.0), (Yon.SELL, 0.1)]
    )
    def test_safe_modeda_cikis_gecer(self, yon, hedef):
        m = motor()
        m.durum.kill("TEST", T0)
        karar = m.degerlendir(sinyal(hedef, yon), olcum())
        assert isinstance(karar, OnayliNiyet)
        assert karar.onayli_maruziyet == hedef
        assert karar.azaltma is True

    def test_cooldownda_cikis_gecer(self):
        m = motor()
        for i in range(3):
            m.islem_kapandi(-10.0, T0 + i * BAR)
        assert isinstance(
            m.degerlendir(sinyal(0.0, Yon.FLAT), olcum(bar_ms=T0 + 3 * BAR)), OnayliNiyet
        )

    def test_asiri_volatilitede_cikis_gecer(self):
        karar = motor().degerlendir(sinyal(0.0, Yon.FLAT), olcum(atr_oran=0.5))
        assert isinstance(karar, OnayliNiyet)

    def test_promotionsuz_cikis_gecer(self):
        """Promotion'u olmayan bir strateji bile pozisyonundan çıkabilir.

        Çıkışı engellemek, zinciri atlayarak açılmış bir pozisyonu kilitlemek olurdu.
        """
        m = motor(mod="live")
        assert isinstance(m.degerlendir(sinyal(0.0, Yon.FLAT), olcum()), OnayliNiyet)

    def test_cikis_kisitlanmaz(self):
        """Azaltan niyet boyutlandırmadan da geçmiyor: hedefi olduğu gibi onaylanıyor."""
        m = motor(azami_maruziyet=0.01, islem_basina_risk=1e-9)
        karar = m.degerlendir(sinyal(0.2, Yon.SELL), olcum())
        assert isinstance(karar, OnayliNiyet)
        assert karar.onayli_maruziyet == pytest.approx(0.2)
        assert karar.kisitlayan == ()


# -------------------------------------------------------------------- promotion


class TestPromotionKapisi:
    def test_backtest_modu_promotion_istemez(self):
        assert isinstance(motor(mod="backtest").degerlendir(sinyal(), olcum()), OnayliNiyet)

    def test_paper_modu_risk_incelemesi_ister(self):
        karar = motor(mod="paper").degerlendir(sinyal(), olcum())
        assert isinstance(karar, Red)
        assert karar.sebep is RedSebebi.PROMOTION_YOK
        assert karar.ayrinti["gereken"] == "risk_incelemesi"

    def test_paper_modu_yeterli_asamada_onaylar(self):
        m = motor(mod="paper", asamalar={"BTCUSDT": Asama.RISK_INCELEMESI})
        assert isinstance(m.degerlendir(sinyal(), olcum()), OnayliNiyet)

    def test_live_modu_yalnizca_zincirin_sonunu_kabul_eder(self):
        m = motor(mod="live", asamalar={"BTCUSDT": Asama.LIVE_ADAYI})
        karar = m.degerlendir(sinyal(), olcum())
        assert isinstance(karar, Red)
        assert karar.sebep is RedSebebi.PROMOTION_YOK

    def test_live_modu_onay_verilmisse_kabul_eder(self):
        m = motor(mod="live", asamalar={"BTCUSDT": Asama.LIVE})
        assert isinstance(m.degerlendir(sinyal(), olcum()), OnayliNiyet)

    def test_taninmayan_strateji_reddedilir(self):
        """Varsayılan güvenli yöne düşmeli: kayıtsız strateji `YOK` sayılır."""
        m = motor(mod="live", asamalar={"ETHUSDT": Asama.LIVE})
        assert isinstance(m.degerlendir(sinyal(), olcum()), Red)

    def test_bilinmeyen_mod_reddedilir(self):
        with pytest.raises(RiskHatasi, match="bilinmeyen mod"):
            motor(mod="canli")


# ----------------------------------------------------------------- geçersiz ölçüm


class TestGecersizOlcum:
    @pytest.mark.parametrize(("fiyat", "ozkaynak"), [(0.0, 10_000.0), (30_000.0, 0.0)])
    def test_gecersiz_olcumle_karar_verilmez(self, fiyat, ozkaynak):
        karar = motor().degerlendir(sinyal(), olcum(fiyat=fiyat, ozkaynak=ozkaynak))
        assert isinstance(karar, Red)
        assert karar.sebep is RedSebebi.GECERSIZ_OLCUM


# ------------------------------------------------------------ limit tutarlılığı


class TestLimitKonfigurasyonu:
    def test_drawdown_limiti_promotion_kapisinin_altinda_olmali(self):
        """Fren kapıdan **önce** devreye girmek zorunda (K-033)."""
        with pytest.raises(ValueError, match="promotion kapısının"):
            limitler(drawdown_limiti=limit_mod.PROMOTION_DRAWDOWN_KAPISI)

    def test_promotion_kapisi_k019_ile_ayni(self):
        """`limitler.py` K-019'un eşiğini kopyalıyor; ikisi ayrışırsa bu test kırılır.

        Sayı iki yerde yaşıyor ve bunun sebebi `risk/`in `research/`i import etmemesi
        (canlı karar yolu araştırma koduna bağlanmamalı). Kopyanın bedeli bu test.
        """
        from scryne_quant.research.kapilar import ESIKLER

        k019 = next(e for e in ESIKLER if e.ad == "max_drawdown")
        assert k019.sinir == limit_mod.PROMOTION_DRAWDOWN_KAPISI

    def test_gerekcesiz_limit_tanimlanamaz(self):
        eksik = _gerekceler()
        del eksik["cooldown_bar"]
        with pytest.raises(ValueError, match="gerekçesi olmayan"):
            limitler(gerekceler=eksik)

    def test_istah_gozden_gecirme_kosulu_olmadan_tanimlanamaz(self):
        with pytest.raises(ValueError, match="gozden_gecirme"):
            limit_mod.Gerekce(kaynak="istah", metin="sebepsiz")

    def test_olculmus_limit_veri_kimligi_olmadan_tanimlanamaz(self):
        with pytest.raises(ValueError, match="veri_sha256"):
            limit_mod.Gerekce(kaynak="olculdu", metin="kimliksiz ölçüm")

    def test_olculmesi_zorunlu_limitler_istah_olamaz(self):
        sahte = _gerekceler()
        sahte["volatilite_esigi"] = limit_mod.Gerekce(
            kaynak="istah", metin="canım böyle istedi", gozden_gecirme="asla"
        )
        with pytest.raises(ValueError, match="ölçülmüş olmak zorunda"):
            limitler(gerekceler=sahte)

    def test_kimlik_gerekce_metninden_bagimsiz(self):
        """Gerekçedeki bir yazım düzeltmesi limitlerin değiştiği anlamına gelmez."""
        a = limitler()
        degisik = _gerekceler()
        degisik["cooldown_bar"] = limit_mod.Gerekce(
            kaynak="istah", metin="yeniden yazılmış gerekçe", gozden_gecirme="test"
        )
        assert limitler(gerekceler=degisik).kimlik() == a.kimlik()

    def test_kimlik_sayi_degisince_degisir(self):
        assert limitler(cooldown_bar=8).kimlik() != limitler().kimlik()

    def test_yazma_okuma_dongusu(self, tmp_path):
        yol = tmp_path / "risk.json"
        limit_mod.yaz(limitler(), yol)
        okunan = limit_mod.yukle(yol)
        assert okunan.kimlik() == limitler().kimlik()

    def test_dosya_yoksa_varsayilana_dusmez(self, tmp_path):
        """Sessizce bir varsayılan limit kümesiyle işlem yapmak, motorun tersi."""
        with pytest.raises(FileNotFoundError, match="risk konfigürasyonu yok"):
            limit_mod.yukle(tmp_path / "yok.json")

    def test_yururlukteki_konfigurasyon_gecerli(self):
        """`config/risk.json` yüklenebiliyor ve ölçülmüş limitleri dağılımıyla taşıyor."""
        yururlukte = limit_mod.yukle()
        for ad in ("volatilite_esigi", "ters_hareket_atr_carpani", "gunluk_zarar_limiti"):
            g = yururlukte.gerekceler[ad]
            assert g.kaynak == "olculdu"
            assert g.dagilim, f"{ad}: ölçülmüş limit dağılımını taşımalı (K-021 kalıbı)"
            assert len(g.veri_sha256) == 64


# ------------------------------------------------------------------ karar sırası


class TestKararSirasi:
    """Sıra sabittir ve sıranın kendisi bir karar (motor.py'nin modül docstring'i)."""

    def test_safe_mode_gunluk_zarardan_once(self):
        """İkisi birden geçerliyse SAFE_MODE raporlanır: kök neden o."""
        m = motor()
        m.bar_isle(T0, 10_000.0)
        m.bar_isle(T0 + BAR, 9_000.0)
        m.durum.kill("ONCEKI_SEBEP", T0)
        karar = m.degerlendir(sinyal(), olcum(bar_ms=T0 + BAR, ozkaynak=9_000.0))
        assert isinstance(karar, Red)
        assert karar.sebep is RedSebebi.SAFE_MODE

    def test_drawdown_gunluk_zarardan_once(self):
        """Drawdown kill switch tetikliyor; günlük zarar yalnızca durduruyor."""
        m = motor()
        m.bar_isle(T0, 10_000.0)
        m.bar_isle(T0 + BAR, 7_000.0)  # hem günlük −%30 hem drawdown %30
        karar = m.degerlendir(sinyal(), olcum(bar_ms=T0 + BAR, ozkaynak=7_000.0))
        assert isinstance(karar, Red)
        assert karar.sebep is RedSebebi.DRAWDOWN

    def test_durdurmalar_boyutlandirmadan_once(self):
        """Reddedilen bir sinyal için boyut hesaplanmıyor.

        Hesaplansaydı audit'e "şu kadar onaylanacaktı" diye yanıltıcı bir sayı girerdi.
        """
        m = motor()
        karar = m.degerlendir(sinyal(1.0), olcum(atr_oran=0.5))
        assert isinstance(karar, Red)
        assert "onayli_maruziyet" not in karar.sozluk()

    def test_sayaclar_tutarli(self):
        """Değerlendirilen = onay + red. Sessiz kayıp olmamalı."""
        m = motor()
        m.bar_isle(T0, 10_000.0)
        m.degerlendir(sinyal(), olcum())
        m.degerlendir(sinyal(), olcum(atr_oran=0.5))
        m.degerlendir(sinyal(0.0, Yon.FLAT), olcum())
        ozet = m.ozet()
        assert ozet["degerlendirilen"] == 3
        assert ozet["onay"] + sum(ozet["red"].values()) == 3
