"""Promotion kaydı zinciri (P1) ve audit bağı (P2). (K-082, İz A)

W2 B4: `runs/promotion/<strateji>.json` düz JSON'du — bütünlük yok; `live/baslat.py` canlı
açılışta aşamaları oradan okuyor ve `MOD_ESIGI["live"]` ona bakıyor. Bu dosya üç şeyi kanıtlar:

1. **P1 zincir:** her satır `onceki_hash`+`satir_hash`; ilk satır `KOK_HASH`e bağlı; hash
   kanonik içerikten (hash alanları hariç, strateji adı dahil) türer. Değiştirilmiş satır,
   bozuk `onceki_hash`, yeniden sıralama, eksik orta satır, zincirsiz eski biçim, aşama ↔
   geçmiş uyuşmazlığı, başka stratejiye taşınmış zincir → `PromotionHatasi` (fail closed).
2. **P2 audit:** `yaz(audit=…)` her yeni satırı `OlayTuru.PROMOTION` olarak audit'e yazar
   (append-only zincir), audit hash'i satıra `audit_hash` olarak döner; `audit_ile_dogrula`
   iki yönlü referansı ve kısaltmayı (dosyadan silinmiş son satır) yakalar.
3. **Fail-closed sınırı:** `paper`/`live` promotion'a dayanır → bozuk kayıt ya da audit yokken
   koşu **açılmaz**; `gozlem` promotion'a bakmaz (K-035) → koşu açılır, olay günlüğe düşer,
   aşama `YOK`. Araştırma/backtest yolu (`RiskMotoru(mod="backtest")`) promotion dosyasına
   hiç dokunmaz.
"""

from __future__ import annotations

import copy
import json

import pytest

from scryne_quant.risk.audit import KOK_HASH, OlayTuru, SqliteDefter
from scryne_quant.risk.promotion import (
    Asama,
    PromotionDefteri,
    PromotionHatasi,
    PromotionKaydi,
    beklenen_asama,
    satir_hashi,
    zinciri_dogrula,
)
from tests.unit.test_promotion import TAM_KANIT, tam_ilerlet

AD = "test_strateji"


def _zincirli() -> PromotionKaydi:
    k = PromotionKaydi(strateji=AD)
    tam_ilerlet(k)  # backtest → … → live_adayi; başarılı satırlar
    return k


def _yaz_ham(defter: PromotionDefteri, govde: dict) -> None:
    defter.yol(govde["strateji"]).write_text(
        json.dumps(govde, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )


# ------------------------------------------------------------------ 1. P1 zincir


class TestZincirKurulusu:
    def test_ilk_satir_kok_hashe_bagli_sonrakiler_oncekine(self):
        k = _zincirli()
        assert len(k.gecmis) >= 3
        assert k.gecmis[0]["onceki_hash"] == KOK_HASH
        for onceki, satir in zip(k.gecmis, k.gecmis[1:], strict=False):
            assert satir["onceki_hash"] == onceki["satir_hash"]
        assert k.son_hash == k.gecmis[-1]["satir_hash"]
        assert zinciri_dogrula(AD, k.gecmis) == k.son_hash

    def test_hash_kanonik_ve_hash_alanlarini_disarida_birakiyor(self):
        satir = {"b": 1, "a": {"y": 2, "x": [1, 2]}, "gecti": True}
        h1 = satir_hashi(AD, satir, KOK_HASH)
        h2 = satir_hashi(AD, {"gecti": True, "a": {"x": [1, 2], "y": 2}, "b": 1}, KOK_HASH)
        assert h1 == h2, "anahtar sırası hash'i değiştirmemeli (kanonik JSON)"
        ile = {**satir, "onceki_hash": "z", "satir_hash": "q", "audit_hash": "w"}
        assert satir_hashi(AD, ile, KOK_HASH) == h1, "hash alanları hash'e girmez"
        assert satir_hashi("baska", satir, KOK_HASH) != h1, "strateji adı hash'e girer"
        assert satir_hashi(AD, satir, "f" * 64) != h1, "önceki hash hash'e girer"

    def test_basarisiz_satirlar_da_zincirde(self):
        from scryne_quant.risk.promotion import Kanit
        from tests.unit.test_promotion import _alanlar

        k = PromotionKaydi(strateji=AD)
        k.ilerlet(Kanit(**{**_alanlar(TAM_KANIT), "dirty": True}))  # kaldı
        k.ilerlet(TAM_KANIT)  # geçti
        assert [s["gecti"] for s in k.gecmis] == [False, True]
        zinciri_dogrula(AD, k.gecmis)
        assert beklenen_asama(k.gecmis) is Asama.BACKTEST


class TestYukleFailClosed:
    def _govde(self) -> dict:
        return _zincirli().sozluk()

    def test_temiz_kayit_yukleniyor(self, tmp_path):
        d = PromotionDefteri(tmp_path)
        k = _zincirli()
        d.yaz(k)
        okunan = d.oku(AD)
        assert okunan.asama is k.asama and okunan.son_hash == k.son_hash

    def test_degistirilmis_satir_reddediliyor(self):
        g = self._govde()
        g["gecmis"][1]["gerekce"] = "sonradan düzeltildi"
        with pytest.raises(PromotionHatasi, match="değiştirilmiş"):
            PromotionKaydi.yukle(g)

    def test_kanit_degisikligi_de_yakalaniyor(self):
        g = self._govde()
        g["gecmis"][0]["kanit"]["dirty"] = True
        with pytest.raises(PromotionHatasi, match="değiştirilmiş"):
            PromotionKaydi.yukle(g)

    def test_bozuk_onceki_hash_reddediliyor(self):
        g = self._govde()
        g["gecmis"][2]["onceki_hash"] = "0" * 63 + "1"
        with pytest.raises(PromotionHatasi, match="onceki_hash"):
            PromotionKaydi.yukle(g)

    def test_yeniden_siralama_reddediliyor(self):
        g = self._govde()
        g["gecmis"][0], g["gecmis"][1] = g["gecmis"][1], g["gecmis"][0]
        with pytest.raises(PromotionHatasi, match="onceki_hash"):
            PromotionKaydi.yukle(g)

    def test_orta_satir_silinince_reddediliyor(self):
        g = self._govde()
        del g["gecmis"][1]
        with pytest.raises(PromotionHatasi, match="onceki_hash"):
            PromotionKaydi.yukle(g)

    def test_zincirsiz_eski_bicim_sessiz_kabul_edilmiyor(self):
        g = self._govde()
        for satir in g["gecmis"]:
            satir.pop("onceki_hash")
            satir.pop("satir_hash")
        with pytest.raises(PromotionHatasi, match="K-082 öncesi"):
            PromotionKaydi.yukle(g)

    def test_asama_gecmisle_uyusmazsa_reddediliyor(self):
        g = self._govde()
        g["asama"] = "live"  # geçmiş live_adayi diyor
        with pytest.raises(PromotionHatasi, match="aşama alanı"):
            PromotionKaydi.yukle(g)

    def test_zincir_baska_stratejiye_tasinamaz(self):
        g = self._govde()
        g["strateji"] = "kopya"
        with pytest.raises(PromotionHatasi, match="değiştirilmiş"):
            PromotionKaydi.yukle(g)

    def test_son_satirlar_silinince_dosya_icinden_fark_edilmez_audit_yakalar(self, tmp_path):
        """Kısaltma: zincir dosya içinde tutarlı kalır (bilinen sınır) — P2 yakalar."""
        d = PromotionDefteri(tmp_path)
        k = _zincirli()
        with SqliteDefter(":memory:") as audit:
            d.yaz(k, audit=audit)
            g = json.loads(d.yol(AD).read_text(encoding="utf-8"))
            g["gecmis"] = g["gecmis"][:2]
            g["asama"] = str(beklenen_asama(g["gecmis"]))
            _yaz_ham(d, g)
            assert d.oku(AD).asama is Asama.KALITE_KONTROL  # dosya kendi içinde tutarlı
            with pytest.raises(PromotionHatasi, match="kısaltılmış"):
                d.oku(AD, audit=audit)


# ------------------------------------------------------------------ 2. P2 audit


class TestAuditBagi:
    def test_yaz_her_satiri_audite_yazar_ve_referansi_iki_yonlu(self, tmp_path):
        d = PromotionDefteri(tmp_path)
        k = _zincirli()
        with SqliteDefter(":memory:") as audit:
            d.yaz(k, audit=audit)
            olaylar = audit.oku(tur=OlayTuru.PROMOTION)
            assert len(olaylar) == len(k.gecmis)
            for satir, olay in zip(k.gecmis, olaylar, strict=True):
                assert satir["audit_hash"] == olay["satir_hash"]
                assert olay["govde"]["satir_hash"] == satir["satir_hash"]
                assert olay["govde"]["strateji"] == AD
                assert olay["zaman_ms"] == satir["zaman_ms"]
            assert audit.dogrula()
            d.oku(AD, audit=audit)  # geçer

    def test_ikinci_yazim_yalnizca_yeni_satirlari_audite_ekler(self, tmp_path):
        d = PromotionDefteri(tmp_path)
        k = _zincirli()
        with SqliteDefter(":memory:") as audit:
            d.yaz(k, audit=audit)
            n = len(audit.oku(tur=OlayTuru.PROMOTION))
            k.elle_onayla("tatbikat: elle onay testi, gerçek değil")
            d.yaz(k, audit=audit)
            assert len(audit.oku(tur=OlayTuru.PROMOTION)) == n + 2  # elle_onay + live
            okunan = d.oku(AD, audit=audit)
            assert okunan.asama is Asama.LIVE

    def test_audite_yazilmamis_satir_reddediliyor(self, tmp_path):
        d = PromotionDefteri(tmp_path)
        d.yaz(_zincirli())  # audit'siz yazım — araştırma kullanımı
        with SqliteDefter(":memory:") as audit, pytest.raises(PromotionHatasi, match="audit_hash"):
            d.oku(AD, audit=audit)

    def test_baska_audit_defteriyle_uyusmazlik_reddediliyor(self, tmp_path):
        d = PromotionDefteri(tmp_path)
        with SqliteDefter(":memory:") as a1:
            d.yaz(_zincirli(), audit=a1)
        with SqliteDefter(":memory:") as a2, pytest.raises(PromotionHatasi, match="karşılığı yok"):
            d.oku(AD, audit=a2)

    def test_bozuk_audit_zinciri_reddediliyor(self, tmp_path):
        class BozukAudit(SqliteDefter):
            def dogrula(self) -> bool:
                return False

        d = PromotionDefteri(tmp_path)
        with BozukAudit(":memory:") as audit:
            d.yaz(_zincirli(), audit=audit)
            with pytest.raises(PromotionHatasi, match="audit defterinin zinciri"):
                d.oku(AD, audit=audit)


# ------------------------------------------------------------------ 3. göç


class TestZincirle:
    def _eski(self, tmp_path) -> PromotionDefteri:
        d = PromotionDefteri(tmp_path)
        g = _zincirli().sozluk()
        for satir in g["gecmis"]:
            satir.pop("onceki_hash")
            satir.pop("satir_hash")
        _yaz_ham(d, g)
        return d

    def test_eski_kayit_acikca_goc_ediliyor_icerik_degismiyor(self, tmp_path):
        d = self._eski(tmp_path)
        eski = copy.deepcopy(json.loads(d.yol(AD).read_text(encoding="utf-8")))
        with pytest.raises(PromotionHatasi, match="K-082 öncesi"):
            d.oku(AD)
        with SqliteDefter(":memory:") as audit:
            k = d.zincirle(AD, audit=audit)
            okunan = d.oku(AD, audit=audit)
            assert okunan.asama is k.asama is Asama(eski["asama"])
            for e, y in zip(eski["gecmis"], okunan.gecmis, strict=True):
                for alan in ("zaman_ms", "asama", "gecti", "gerekce", "onceki_asama", "kanit"):
                    assert e[alan] == y[alan]
            assert all(o["govde"].get("goc") is True for o in audit.oku(tur=OlayTuru.PROMOTION))
            with pytest.raises(PromotionHatasi, match="zaten zincirli"):
                d.zincirle(AD, audit=audit)

    def test_kaydi_olmayan_strateji_goc_edilemez(self, tmp_path):
        with SqliteDefter(":memory:") as audit, pytest.raises(PromotionHatasi, match="kayıt yok"):
            PromotionDefteri(tmp_path).zincirle("yok", audit=audit)


# ------------------------------------------------------------------ 4. açılış sınırı


class TestAcilisSiniri:
    def _ortak(self, tmp_path):
        from scryne_quant.common.maliyet import MaliyetModeli
        from scryne_quant.strategy.kutuphane.sma_kesisim import SmaKesisim
        from tests.conftest import risk_limitleri

        return {
            "strateji": SmaKesisim(hizli=5, yavas=20),
            "maliyet": MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0),
            "limitler": risk_limitleri(),
            "kosu_yolu": tmp_path / "k.sqlite",
            "depo_kok": tmp_path / "depo",
            "adaptor": None,
            "promotion_kok": tmp_path / "promotion",
        }

    def _kimlik(self, mod: str):
        from scryne_quant.strategy.kutuphane.sma_kesisim import SmaKesisim
        from tests.unit.test_paper_dongu import kimlik as kimlik_kur

        return kimlik_kur(mod, strateji=SmaKesisim(hizli=5, yavas=20).sozluk())

    def _bozuk_kayit(self, kok):
        d = PromotionDefteri(kok)
        g = _zincirli().sozluk()
        g["gecmis"][1]["gerekce"] = "kurcalandı"
        _yaz_ham(d, g)

    def test_gozlem_bozuk_kayitla_acilir_olay_yazar_asama_yok(self, tmp_path):
        from scryne_quant.live import baslat as baslat_mod
        from scryne_quant.live.depo import KosuOlayi

        ortak = self._ortak(tmp_path)
        self._bozuk_kayit(ortak["promotion_kok"])
        kurulum, _ = baslat_mod.kur(kimlik=self._kimlik("gozlem"), **ortak)
        try:
            assert kurulum.motor.risk.asamalar.get(AD) is Asama.YOK
            olaylar = kurulum.motor.depo.olaylar()
            assert any(o["tur"] == str(KosuOlayi.PROMOTION_OKUNAMADI) for o in olaylar)
        finally:
            kurulum.kapat()

    def test_paper_bozuk_kayitla_acilmaz(self, tmp_path):
        from scryne_quant.live import baslat as baslat_mod

        ortak = self._ortak(tmp_path)
        self._bozuk_kayit(ortak["promotion_kok"])
        with pytest.raises(PromotionHatasi, match="değiştirilmiş"):
            baslat_mod.kur(
                kimlik=self._kimlik("paper"), audit_yolu=tmp_path / "audit.sqlite", **ortak
            )

    def test_paper_auditsiz_acilmaz(self, tmp_path):
        from scryne_quant.live import baslat as baslat_mod

        ortak = self._ortak(tmp_path)
        PromotionDefteri(ortak["promotion_kok"]).yaz(_zincirli())
        with pytest.raises(PromotionHatasi, match="audit_yolu"):
            baslat_mod.kur(kimlik=self._kimlik("paper"), **ortak)

    def test_paper_dogrulanmis_kayitla_acilir(self, tmp_path):
        from scryne_quant.live import baslat as baslat_mod

        ortak = self._ortak(tmp_path)
        audit_yolu = tmp_path / "audit.sqlite"
        with SqliteDefter(audit_yolu) as audit:
            PromotionDefteri(ortak["promotion_kok"]).yaz(_zincirli(), audit=audit)
        kurulum, _ = baslat_mod.kur(kimlik=self._kimlik("paper"), audit_yolu=audit_yolu, **ortak)
        try:
            assert kurulum.motor.risk.asamalar[AD] is Asama.LIVE_ADAYI
        finally:
            kurulum.kapat()

    def test_paper_audit_karsiligi_olmayan_kayitla_acilmaz(self, tmp_path):
        from scryne_quant.live import baslat as baslat_mod

        ortak = self._ortak(tmp_path)
        PromotionDefteri(ortak["promotion_kok"]).yaz(_zincirli())  # audit'siz
        with pytest.raises(PromotionHatasi, match="audit_hash"):
            baslat_mod.kur(
                kimlik=self._kimlik("paper"), audit_yolu=tmp_path / "audit.sqlite", **ortak
            )

    def test_backtest_yolu_promotion_dosyasina_dokunmaz(self, tmp_path):
        """Araştırma: `RiskMotoru(mod="backtest")` promotion defterini hiç okumaz."""
        from scryne_quant.risk.motor import RiskMotoru
        from tests.conftest import risk_limitleri

        self._bozuk_kayit(tmp_path / "promotion")
        motor = RiskMotoru(risk_limitleri(), "1h", mod="backtest")
        assert motor.asamalar == {}


# ------------------------------------------------------------------ 5. CLI


class TestCli:
    def test_zincirle_ve_durum(self, tmp_path):
        from typer.testing import CliRunner

        from scryne_quant.cli import main as cli

        runner = CliRunner()
        kok, audit = tmp_path / "promotion", tmp_path / "audit.sqlite"
        d = PromotionDefteri(kok)
        g = _zincirli().sozluk()
        for satir in g["gecmis"]:
            satir.pop("onceki_hash")
            satir.pop("satir_hash")
        _yaz_ham(d, g)

        durum = runner.invoke(cli.app, ["promotion", "durum", AD, "--kok", str(kok)])
        assert durum.exit_code != 0 and "K-082 öncesi" in (durum.stdout + str(durum.exception))

        goc = runner.invoke(
            cli.app, ["promotion", "zincirle", AD, "--kok", str(kok), "--audit", str(audit)]
        )
        assert goc.exit_code == 0, goc.stdout + str(goc.exception)
        assert "zincirlendi" in goc.stdout

        durum = runner.invoke(cli.app, ["promotion", "durum", AD, "--kok", str(kok), "--json"])
        assert durum.exit_code == 0, durum.stdout + str(durum.exception)
        kayit = json.loads(durum.stdout)["kayitlar"][0]
        assert kayit["asama"] == "live_adayi"
        assert all("satir_hash" in s and "audit_hash" in s for s in kayit["gecmis"])
        with SqliteDefter(audit) as a:
            assert len(a.oku(tur=OlayTuru.PROMOTION)) == len(kayit["gecmis"]) and a.dogrula()

    def test_onayla_audite_yazar(self, tmp_path):
        from typer.testing import CliRunner

        from scryne_quant.cli import main as cli

        runner = CliRunner()
        kok, audit = tmp_path / "promotion", tmp_path / "audit.sqlite"
        with SqliteDefter(audit) as a:
            PromotionDefteri(kok).yaz(_zincirli(), audit=a)
        sonuc = runner.invoke(cli.app, [
            "promotion", "onayla", AD, "--not", "tatbikat: CLI elle onay testi",
            "--kok", str(kok), "--audit", str(audit),
        ])
        assert sonuc.exit_code == 0, sonuc.stdout + str(sonuc.exception)
        with SqliteDefter(audit) as a:
            okunan = PromotionDefteri(kok).oku(AD, audit=a)
            assert okunan.asama is Asama.LIVE
            son = a.oku(tur=OlayTuru.PROMOTION)[-1]
            assert son["govde"]["asama"] == "live" and son["durum"]["asama_sonrasi"] == "live"
