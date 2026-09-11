"""Promotion zinciri zorlanıyor. (K-010, K-019, Roadmap Faz 5 bitti kriteri)

Roadmap kriteri: *"Promotion kapıları uygulanıyor; `dirty` veya `data_quality_warning`
işaretli sonuç kapıdan geçemiyor."*

K-010'un asıl korumaya çalıştığı şey teknik bir risk değil, **insan**: *"bugünkü Scryne,
altı ay sonraki sabırsız Scryne'a karşı şimdi karar veriyor."* Bu dosya o kararın
mekanizması — ve test ettiği şeylerin üçü doğrudan sabırsızlığın yollarını kapatıyor:

1. **Aşama atlanamıyor** (`test_asama_atlanamaz`) — `live`a doğrudan yazmak yok.
2. **Elle onay makine tarafından verilemiyor** (`TestElleOnay`) — ve `risk/` içinde
   `elle_onayla`yı çağıran başka bir yer olmadığı statik olarak kontrol ediliyor.
3. **Ölçülemeyen aşama geçilmiş sayılmıyor** (`TestOlculemeyen`) — K-019'un cümlesi:
   "'Veri yoktu' ile 'kapıdan geçti' aynı şey değil."
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import pytest

from scryne_quant.risk.promotion import (
    ASGARI_PAPER_GUN,
    SIRA,
    Asama,
    Kanit,
    PromotionDefteri,
    PromotionHatasi,
    PromotionKaydi,
    sonraki,
    yeterli_mi,
)

KOK: Final = Path(__file__).resolve().parents[2] / "src"

TAM_KANIT: Final = Kanit(
    config_hash="c" * 64,
    sonuc_hash="s" * 64,
    veri_sha256="v" * 64,
    commit="a" * 40,
    dirty=False,
    mutlak_engeller=(),
    kapi_sonucu={"gecti": True, "kalan_kapilar": [], "kapilar": {}},
    risk_limit_kimligi="r" * 64,
    risk_max_drawdown=0.12,
    risk_drawdown_limiti=0.20,
    paper_gun=31.0,
    paper_kesinti=0,
    paper_mod="paper",
)


def kayit(asama: Asama = Asama.YOK) -> PromotionKaydi:
    return PromotionKaydi(strateji="test_strateji", asama=asama)


def tam_ilerlet(k: PromotionKaydi, kanit: Kanit = TAM_KANIT) -> list[str]:
    """Zinciri durduğu yere kadar ilerletir; geçilen aşamaları döndürür."""
    gecilen: list[str] = []
    while True:
        onceki = k.asama
        k.ilerlet(kanit)
        if k.asama is onceki:
            return gecilen
        gecilen.append(str(k.asama))


class TestZincirSirasi:
    def test_zincir_k010_ile_ayni(self):
        """K-010'un diyagramındaki sekiz adım, aynı sırayla."""
        assert [str(a) for a in SIRA] == [
            "yok",
            "backtest",
            "kalite_kontrol",
            "out_of_sample",
            "risk_incelemesi",
            "paper",
            "live_adayi",
            "elle_onay",
            "live",
        ]

    def test_ilerlet_tek_adim_atar(self):
        """Bir çağrıda zinciri sonuna kadar koşturmak, elle onayı bir engele çevirirdi."""
        k = kayit()
        k.ilerlet(TAM_KANIT)
        assert k.asama is Asama.BACKTEST

    def test_asama_atlanamaz(self):
        """Tam kanıtla bile zincir `live_adayi`nda duruyor: sonrası insanın."""
        k = kayit()
        gecilen = tam_ilerlet(k)
        assert gecilen == [
            "backtest",
            "kalite_kontrol",
            "out_of_sample",
            "risk_incelemesi",
            "paper",
            "live_adayi",
        ]
        assert k.asama is Asama.LIVE_ADAYI
        assert k.eksik_asamalar() == [Asama.ELLE_ONAY, Asama.LIVE]

    def test_sonraki(self):
        assert sonraki(Asama.YOK) is Asama.BACKTEST
        assert sonraki(Asama.LIVE) is None

    def test_yeterli_mi(self):
        assert yeterli_mi(Asama.LIVE, Asama.RISK_INCELEMESI) is True
        assert yeterli_mi(Asama.RISK_INCELEMESI, Asama.RISK_INCELEMESI) is True
        assert yeterli_mi(Asama.OUT_OF_SAMPLE, Asama.RISK_INCELEMESI) is False


class TestMutlakEngeller:
    """`dirty` veya `data_quality_warning` işaretli sonuç kapıdan geçemez. (K-009, K-006)"""

    def test_dirty_backtest_asamasinda_durdurulur(self):
        k = kayit()
        sonuc = k.ilerlet(Kanit(**{**_alanlar(TAM_KANIT), "dirty": True}))
        assert sonuc.gecti is False
        assert "kirli" in sonuc.gerekce
        assert k.asama is Asama.YOK

    def test_data_quality_warning_kalite_kontrolde_durdurulur(self):
        k = kayit(Asama.BACKTEST)
        sonuc = k.ilerlet(
            Kanit(**{**_alanlar(TAM_KANIT), "mutlak_engeller": ("data_quality_warning",)})
        )
        assert sonuc.gecti is False
        assert "data_quality_warning" in sonuc.gerekce
        assert k.asama is Asama.BACKTEST

    def test_gecici_maliyet_modeli_durdurulur(self):
        """K-021: kalibre edilmemiş maliyet modeliyle üretilen sonuç promotion'a giremez."""
        k = kayit(Asama.BACKTEST)
        sonuc = k.ilerlet(
            Kanit(**{**_alanlar(TAM_KANIT), "mutlak_engeller": ("gecici_maliyet_modeli",)})
        )
        assert sonuc.gecti is False
        assert k.asama is Asama.BACKTEST

    def test_dirty_kalite_kontrolde_tekrar_sayilmaz(self):
        """`dirty` zaten `backtest` aşamasında kapatıldı; iki yerde raporlanmamalı.

        Aynı engeli iki aşamada göstermek, zincirin nerede durduğunu belirsizleştirirdi.
        """
        k = kayit(Asama.BACKTEST)
        sonuc = k.ilerlet(Kanit(**{**_alanlar(TAM_KANIT), "mutlak_engeller": ("dirty",)}))
        assert sonuc.gecti is True

    def test_tum_engeller_birlikte(self):
        k = kayit(Asama.BACKTEST)
        sonuc = k.ilerlet(
            Kanit(
                **{
                    **_alanlar(TAM_KANIT),
                    "mutlak_engeller": ("dirty", "data_quality_warning", "gecici_maliyet_modeli"),
                }
            )
        )
        assert sonuc.gecti is False
        assert "data_quality_warning" in sonuc.gerekce
        assert "gecici_maliyet_modeli" in sonuc.gerekce


class TestOlculemeyen:
    """Ölçülemeyen aşama **geçilmiş sayılmaz** — `None`, `False`den farklı bir sonuç."""

    def test_kanitsiz_backtest_olculemedi(self):
        sonuc = kayit().ilerlet(Kanit())
        assert sonuc.gecti is None
        assert "yok" in sonuc.gerekce

    def test_kapi_degerlendirmesi_yoksa_olculemedi(self):
        k = kayit(Asama.KALITE_KONTROL)
        sonuc = k.ilerlet(Kanit(**{**_alanlar(TAM_KANIT), "kapi_sonucu": None}))
        assert sonuc.gecti is None
        assert k.asama is Asama.KALITE_KONTROL

    def test_risksiz_kosu_risk_incelemesini_gecemez(self):
        """Risk motoru devre dışı koşulmuş bir sonuç, risk incelemesini geçmiş sayılmaz.

        `Sonuc.risk` `None` olduğunda `risk_limit_kimligi` de `None` kalıyor — yani bu
        aşamanın kanıtı yok. Geçmiş sayılsaydı, risk limitlerinin hiç uygulanmadığı bir
        strateji live adayı olabilirdi.
        """
        k = kayit(Asama.OUT_OF_SAMPLE)
        sonuc = k.ilerlet(Kanit(**{**_alanlar(TAM_KANIT), "risk_limit_kimligi": None}))
        assert sonuc.gecti is None
        assert "risk motoru devrede değil" in sonuc.gerekce

    def test_paper_kosusu_yoksa_olculemedi(self):
        """Faz 5'te paper aşaması tanım olarak ölçülemez — Faz 6'nın işi."""
        k = kayit(Asama.RISK_INCELEMESI)
        sonuc = k.ilerlet(Kanit(**{**_alanlar(TAM_KANIT), "paper_gun": None}))
        assert sonuc.gecti is None
        assert "Faz 6" in sonuc.gerekce

    def test_olculemeyen_asama_zinciri_durdurur(self):
        """Faz 5'in gerçek durumu: paper ölçülemediği için zincir orada duruyor."""
        k = kayit()
        kanit = Kanit(**{**_alanlar(TAM_KANIT), "paper_gun": None, "paper_kesinti": None})
        gecilen = tam_ilerlet(k, kanit)
        assert gecilen == ["backtest", "kalite_kontrol", "out_of_sample", "risk_incelemesi"]
        assert k.asama is Asama.RISK_INCELEMESI


class TestRiskIncelemesi:
    def test_risk_altinda_asilan_dusus_reddedilir(self):
        """Limite **değmiş** olmak reddetme sebebi — limitin çalışmadığı değil.

        Drawdown limiti bir tavan değil tetikleyici: aşıldığında kill switch'i açar ama
        zaten olmuş bir düşüşü geri alamaz (K-008/2 pozisyon kapatmayı yasaklıyor). Faz
        5'te ölçüldü: `cok_faktor` risk altında %20,1 düştü, limit %20,0 — yani limit tam
        olarak tasarlandığı gibi çalıştı ve yine de aşıldı.

        Kapının reddetmesinin sebebi başka: backtest'te kill switch'e değen bir strateji
        canlıda elle onay bekleyerek durur.
        """
        k = kayit(Asama.OUT_OF_SAMPLE)
        sonuc = k.ilerlet(Kanit(**{**_alanlar(TAM_KANIT), "risk_max_drawdown": 0.201}))
        assert sonuc.gecti is False
        assert "kill switch tetiklenmiş" in sonuc.gerekce

    def test_limitin_altindaki_dusus_gecer(self):
        k = kayit(Asama.OUT_OF_SAMPLE)
        assert k.ilerlet(TAM_KANIT).gecti is True


class TestPaperAsamasi:
    def test_kesinti_varsa_gecmez(self):
        k = kayit(Asama.RISK_INCELEMESI)
        sonuc = k.ilerlet(Kanit(**{**_alanlar(TAM_KANIT), "paper_kesinti": 2}))
        assert sonuc.gecti is False
        assert "kesinti" in sonuc.gerekce

    def test_yetersiz_gun_sayisi_gecmez(self):
        k = kayit(Asama.RISK_INCELEMESI)
        sonuc = k.ilerlet(Kanit(**{**_alanlar(TAM_KANIT), "paper_gun": 29.0}))
        assert sonuc.gecti is False

    def test_asgari_gun_roadmapla_ayni(self):
        assert ASGARI_PAPER_GUN == 30.0


class TestElleOnay:
    """K-010: son adımdaki elle onay kaldırılamaz."""

    def test_makine_elle_onayi_gecemez(self):
        """`live_adayi`nda tam kanıtla bile `ilerlet` geçmiyor."""
        k = kayit(Asama.LIVE_ADAYI)
        sonuc = k.ilerlet(TAM_KANIT)
        assert sonuc.gecti is None
        assert "makine tarafından geçilemez" in sonuc.gerekce
        assert k.asama is Asama.LIVE_ADAYI

    def test_onay_live_adayi_disinda_verilemez(self):
        for asama in (Asama.YOK, Asama.BACKTEST, Asama.OUT_OF_SAMPLE, Asama.PAPER):
            with pytest.raises(PromotionHatasi, match="yalnızca `live_adayi`"):
                kayit(asama).elle_onayla("yeterince uzun bir gerekçe metni")

    @pytest.mark.parametrize("metin", ["", "ok", "  tamam  ", "evet"])
    def test_gerekcesiz_onay_reddedilir(self, metin):
        """Gerekçesiz onay bir tıktır, karar değil."""
        with pytest.raises(PromotionHatasi, match="gerekçe ister"):
            kayit(Asama.LIVE_ADAYI).elle_onayla(metin)

    def test_gerekceli_onay_livea_tasir(self):
        k = kayit(Asama.LIVE_ADAYI)
        sonuc = k.elle_onayla("OOS ve WF sonuçları incelendi, minimum sermaye ile başlanacak")
        assert sonuc.gecti is True
        assert k.asama is Asama.LIVE
        assert k.sozluk()["canliya_yetkili"] is True

    def test_onay_gerekcesi_kayda_giriyor(self):
        k = kayit(Asama.LIVE_ADAYI)
        k.elle_onayla("minimum sermaye ile, günlük gözden geçirmeyle")
        onay = next(g for g in k.gecmis if g["asama"] == "elle_onay")
        assert "minimum sermaye" in onay["gerekce"]
        assert onay["onceki_asama"] == "live_adayi"

    def test_risk_paketinde_otomatik_elle_onay_yok(self):
        """`elle_onayla` `risk/` içinde hiçbir yerden çağrılmıyor.

        Bu test, onayı bir koşula bağlayan kodu yakalar. `kill_switch` testindeki
        `serbest_birak` kontrolüyle aynı kalıp: K-010'un "kaldırılamaz" sözünü bir
        temenniden kısıta çeviren şey bu.
        """
        bulunan: list[str] = []
        for dosya in (KOK / "scryne_quant" / "risk").rglob("*.py"):
            agac = ast.parse(dosya.read_text(encoding="utf-8"), filename=str(dosya))
            for dugum in ast.walk(agac):
                if (
                    isinstance(dugum, ast.Call)
                    and isinstance(dugum.func, ast.Attribute)
                    and dugum.func.attr == "elle_onayla"
                ):
                    bulunan.append(f"{dosya.name}:{dugum.lineno}")
        assert not bulunan, (
            "elle onay kod içinden veriliyor; K-010'un kaldırılamaz adımı kaldırılmış "
            f"olur: {', '.join(bulunan)}"
        )


class TestKalicilik:
    def test_yazip_okuyor(self, tmp_path):
        defter = PromotionDefteri(tmp_path)
        k = kayit()
        tam_ilerlet(k)
        defter.yaz(k)

        okunan = defter.oku("test_strateji")
        assert okunan.asama is Asama.LIVE_ADAYI
        assert len(okunan.gecmis) == len(k.gecmis)

    def test_eksik_kayit_basa_donuyor(self, tmp_path):
        """Kaydı silmek bir stratejiyi live'a değil **başa** götürür.

        Varsayılanın güvenli yöne düşmesi şart: eksik dosya "zincir geçildi" diye
        okunursa, promotion'ı atlamanın yolu `rm` olurdu.
        """
        okunan = PromotionDefteri(tmp_path).oku("hic_yok")
        assert okunan.asama is Asama.YOK
        assert okunan.sozluk()["canliya_yetkili"] is False

    def test_gecmis_silinmiyor(self, tmp_path):
        """Her değerlendirme geçmişe ekleniyor; başarısız denemeler de kayıtta."""
        defter = PromotionDefteri(tmp_path)
        k = kayit()
        k.ilerlet(Kanit(**{**_alanlar(TAM_KANIT), "dirty": True}))  # başarısız
        k.ilerlet(TAM_KANIT)  # başarılı
        defter.yaz(k)

        okunan = defter.oku("test_strateji")
        assert len(okunan.gecmis) == 2
        assert [g["gecti"] for g in okunan.gecmis] == [False, True]

    def test_hepsi_listeler(self, tmp_path):
        defter = PromotionDefteri(tmp_path)
        for ad in ("a", "b", "c"):
            defter.yaz(PromotionKaydi(strateji=ad))
        assert [k.strateji for k in defter.hepsi()] == ["a", "b", "c"]


def _alanlar(k: Kanit) -> dict:
    """`Kanit`in alanları sözlük olarak — tek alanı değiştirip yeniden kurmak için."""
    return {
        "config_hash": k.config_hash,
        "sonuc_hash": k.sonuc_hash,
        "veri_sha256": k.veri_sha256,
        "commit": k.commit,
        "dirty": k.dirty,
        "mutlak_engeller": k.mutlak_engeller,
        "kapi_sonucu": k.kapi_sonucu,
        "risk_limit_kimligi": k.risk_limit_kimligi,
        "risk_max_drawdown": k.risk_max_drawdown,
        "risk_drawdown_limiti": k.risk_drawdown_limiti,
        "paper_gun": k.paper_gun,
        "paper_kesinti": k.paper_kesinti,
        "paper_mod": k.paper_mod,
    }
