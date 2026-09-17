"""Dashboard API'si: dört sayfanın veri sözleşmesi ve salt-okunurluk. (K-012, K-036)

İki tür test var ve ikincisi daha önemli:

1. **Sözleşme**: her ucun döndürdüğü alanlar. Arayüz bunlara göre yazılıyor; eksilen bir
   alan tarayıcıda `undefined` olarak görünür, testte kırmızı olarak.
2. **Sınır**: API'de yazma ucu **yok**. Risk limitlerini, strateji parametrelerini veya
   SAFE_MODE'u değiştiren bir uç, K-008/4 ve K-009'un koruduğu şeyi bir tıklamaya
   indirgerdi. Bu, "unutulmuş bir özellik" değil bir karar, ve kararın testi burada.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from scryne_quant.live.api import Yayinci, uygulama_kur
from scryne_quant.live.toparlanma import toparlan
from scryne_quant.risk.audit import BellekDefteri
from tests.unit.test_paper_dongu import barlar, kosuyu_isle, motor_kur


@pytest.fixture
def istemci():
    defter = BellekDefteri()
    m = motor_kur({16: ("BUY", 0.25), 30: ("FLAT", 0.0)})
    m.risk.defter = defter
    toparlan(m, [])
    kosuyu_isle(m, barlar(40))
    app = uygulama_kur(m, defter=defter)
    with TestClient(app) as c:
        c.motor = m  # type: ignore[attr-defined]
        yield c


class TestOverview:
    def test_ozet_alanlari(self, istemci) -> None:
        g = istemci.get("/api/ozet").json()
        for ad in ("kosu", "portfoy", "ozkaynak", "maruziyet", "risk", "tazelik",
                   "pencere", "saglik", "bekleyen", "acik_islem", "durdu"):
            assert ad in g, ad

    def test_saglik_kesintiyi_gun_sayisiyla_birlikte_veriyor(self, istemci) -> None:
        # Tek başına bir gün sayısı göstermek kesintileri görünmez kılardı; Faz 6'nın
        # kriteri ikisinin **birlikte** okunmasını istiyor.
        s = istemci.get("/api/ozet").json()["saglik"]
        assert "calisma_gun" in s
        assert s["kesinti_sayisi"] == 0
        assert s["kesintisiz"] is True
        assert s["safe_mode"] is False
        assert "bayat" in s and "veri_yasi_ms" in s


class TestStrategies:
    def test_strateji_alanlari(self, istemci) -> None:
        g = istemci.get("/api/strateji").json()
        assert g["mod"] == "gozlem"
        assert g["strateji"]["ad"] == "planli"
        assert "sayimlar" in g and "red" in g["sayimlar"]

    def test_gozlem_kosusu_kanit_uretmedigini_soyluyor(self, istemci) -> None:
        # K-035: ekranda "30 gün kesintisiz" yazan bir kutunun yanında o koşunun kapıya
        # sayılmadığı yazmıyorsa, ekran yanıltır.
        assert istemci.get("/api/strateji").json()["kanit_uretir"] is False


class TestPositions:
    def test_pozisyon_alanlari(self, istemci) -> None:
        g = istemci.get("/api/pozisyon").json()
        for ad in ("fiyat", "portfoy", "acik", "maruziyet", "filller", "fill_sayisi"):
            assert ad in g, ad

    def test_filller_yeniden_eskiye(self, istemci) -> None:
        filller = istemci.get("/api/pozisyon").json()["filller"]
        assert len(filller) >= 2
        assert filller[0]["zaman_ms"] > filller[-1]["zaman_ms"]

    def test_limit_sinirlari_zorlaniyor(self, istemci) -> None:
        assert istemci.get("/api/pozisyon?limit=0").status_code == 422
        assert istemci.get("/api/pozisyon?limit=5000").status_code == 422


class TestLogs:
    def test_olay_kesinti_sayisiyla_geliyor(self, istemci) -> None:
        g = istemci.get("/api/olay").json()
        assert g["kesinti_sayisi"] == 0
        assert "kopma" in g["kesinti_turleri"]
        # Süreç çökmesi kesinti sayılır ve geriye dönük yazılır (Faz 6 kriteri).
        assert "temiz_kapanmadi" in g["kesinti_turleri"]

    def test_audit_zincir_gecerliligini_gosteriyor(self, istemci) -> None:
        # "Kurcalanmadı" bilgisi, ancak gösterildiğinde bir güvence (K-032).
        g = istemci.get("/api/audit").json()
        assert g["zincir_gecerli"] is True
        assert len(g["kayitlar"]) >= 1

    def test_audit_defteri_yoksa_503(self) -> None:
        m = motor_kur({})
        toparlan(m, [])
        with TestClient(uygulama_kur(m, defter=None)) as c:
            assert c.get("/api/audit").status_code == 503


class TestSaltOkunur:
    """API'de yazma ucu yok — bir eksiklik değil, bir sınır (K-008/4, K-009)."""

    def test_hicbir_yazma_yontemi_tanimli_degil(self, istemci) -> None:
        semalar = istemci.get("/api/openapi.json").json()["paths"]
        yontemler = {y.upper() for yollar in semalar.values() for y in yollar}
        assert yontemler == {"GET"}

    def test_risk_ve_safe_mode_ucu_yok(self, istemci) -> None:
        yollar = istemci.get("/api/openapi.json").json()["paths"]
        assert not [y for y in yollar if "serbest" in y or "limit" in y.rstrip("s")]


class TestYayinci:
    def test_dolu_kuyrukta_eski_dusuyor_yayinci_bloklanmiyor(self) -> None:
        # Bir dashboard sekmesinin yavaşlığı trader döngüsünü yavaşlatamamalı.
        y = Yayinci()
        kuyruk = y.abone()
        for i in range(100):
            y.yayinla({"i": i})
        assert kuyruk.full()
        ilk = json.loads(kuyruk.get_nowait())
        assert ilk["i"] > 0  # en eskiler düşürüldü

    def test_abonelik_birakiliyor(self) -> None:
        y = Yayinci()
        k = y.abone()
        assert y.abone_sayisi == 1
        y.birak(k)
        assert y.abone_sayisi == 0


class TestSpaGeriDususu:
    """SPA geri düşüşü `/api/` altını **yutmamalı**.

    İlk yazımda `/{yol:path}` her şeyi yakalıyordu: yanlış yazılmış ya da kaldırılmış bir
    API yolu `index.html`i **200** ile döndürüyordu. İstemci tarafında bu "JSON
    bekleniyordu, HTML geldi" diye görünür — yani hata asıl sebebinden uzakta patlar ve
    kaldırılmış bir uç, çalışan bir uç gibi durur.
    """

    @pytest.fixture
    def web_istemci(self, tmp_path):
        web = tmp_path / "dist"
        (web / "assets").mkdir(parents=True)
        (web / "index.html").write_text("<!doctype html><title>SQ</title>", encoding="utf-8")
        (web / "favicon.svg").write_text("<svg/>", encoding="utf-8")
        m = motor_kur({})
        toparlan(m, [])
        with TestClient(uygulama_kur(m, defter=BellekDefteri(), web_kok=web)) as c:
            yield c

    def test_bilinmeyen_api_yolu_404(self, web_istemci) -> None:
        cevap = web_istemci.get("/api/olmayan-uc")
        assert cevap.status_code == 404
        assert "html" not in cevap.headers["content-type"]

    def test_bilinen_api_yolu_calismaya_devam_ediyor(self, web_istemci) -> None:
        assert web_istemci.get("/api/ozet").status_code == 200

    def test_istemci_yolu_index_dosyasina_dusuyor(self, web_istemci) -> None:
        cevap = web_istemci.get("/pozisyon")
        assert cevap.status_code == 200
        assert "<title>SQ</title>" in cevap.text

    def test_gercek_dosya_oldugu_gibi_servis_ediliyor(self, web_istemci) -> None:
        assert web_istemci.get("/favicon.svg").text == "<svg/>"


class TestIzleme:
    def test_izleme_durumu_ve_sapma(self, tmp_path) -> None:
        import json

        m = motor_kur({})
        toparlan(m, [])
        izleme_kok, paper_kok = tmp_path / "izleme", tmp_path / "paper"
        with TestClient(uygulama_kur(m, izleme_kok=izleme_kok, paper_kok=paper_kok)) as c:
            assert c.get("/api/izleme").json()["var"] is False
            izleme_kok.mkdir()
            paper_kok.mkdir()
            (izleme_kok / "durum.json").write_text(json.dumps({
                "zaman": "x", "sistem": {"disk_bos_gb": 50.0}, "alarmlar": [],
                "kosular": [{"kosu": "evren-kiyas", "surec_yasiyor": True}]}))
            (paper_kok / "evren-kiyas.sapma.jsonl").write_text(
                json.dumps({"ilk_ayrisan_adim": None}) + "\n"
                + json.dumps({"ilk_ayrisan_adim": 5}) + "\n")
            g = c.get("/api/izleme").json()
            assert g["var"] is True and g["yazildi_ms"] > 0
            assert g["kosular"][0]["sapma"] == {"ilk_ayrisan_adim": 5}
