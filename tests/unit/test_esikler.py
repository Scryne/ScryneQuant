"""`config/esikler.json` ↔ kod: eşik kaydı tek ve açık kaynak, ayar mekanizması değil. (K-113)

Threshold-Policy'nin kabulü şu demek: yürürlükteki her promotion eşiği `config/esikler.json`'da
bir satır olarak durur, satır kaynağını (`olculdu`/`istah`/`null-kalibre`/`politika`) ve
dayandığı kararı (K-XXX) taşır, ve kodun sabiti o satıra **eşittir**. Kod dosyayı okumaz —
okusaydı bir eşik test yazmadan, K yazmadan, JSON düzenlenerek değiştirilebilirdi ve bu tam
olarak K-010'un yasakladığı "sonuçlara bakıp eşiği ayarla" kapısı olurdu. Bunun yerine üç
şey aynı anda değişmek zorunda: kod, bu dosya, Kararlar.md — ve bu testler ikisini birbirine,
üçüncüsünü başlığıyla bağlar.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scryne_quant.backtest import metrikler as metrikler_mod
from scryne_quant.common.zaman import timeframe_ms
from scryne_quant.research import kapilar, kapilar_v2

KOK = Path(__file__).resolve().parents[2]
ESIKLER_JSON = KOK / "config" / "esikler.json"
KARARLAR = KOK / "docs" / "Kararlar.md"
OOS_SURESI_KAYDI = KOK / "docs" / "research" / "records" / "2026-09-22-R5-oos-suresi.json"

KAYNAKLAR = {"olculdu", "istah", "null-kalibre", "politika"}


@pytest.fixture(scope="module")
def kayit() -> dict:
    return json.loads(ESIKLER_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def karar_basliklari() -> set[str]:
    metin = KARARLAR.read_text(encoding="utf-8")
    return set(re.findall(r"^## (K-\d{3})\b", metin, flags=re.MULTILINE))


def _kod_esikleri() -> dict[str, kapilar.Esik]:
    hepsi = {e.ad: e for e in kapilar.ESIKLER}
    for e in kapilar_v2.ESIKLER_V2:
        assert e.ad not in hepsi, f"{e.ad} iki listede birden"
        hepsi[e.ad] = e
    return hepsi


class TestKayitKoduBirebirTutuyor:
    def test_her_kod_esiginin_kayitta_tek_satiri_var(self, kayit):
        kod = _kod_esikleri()
        satirlar = {s["ad"]: s for s in kayit["kapilar"]}
        assert len(satirlar) == len(kayit["kapilar"]), "kayıtta yinelenen eşik adı"
        assert set(satirlar) == set(kod), (
            f"kayıt ↔ kod ayrıştı: yalnız kayıtta {set(satirlar) - set(kod)}, "
            f"yalnız kodda {set(kod) - set(satirlar)}"
        )

    def test_deger_yon_alan_on_kosul_esit(self, kayit):
        kod = _kod_esikleri()
        for s in kayit["kapilar"]:
            e = kod[s["ad"]]
            assert s["deger"] == e.sinir, f"{e.ad}: kayıt {s['deger']} ≠ kod {e.sinir}"
            assert s["yon"] == e.yon, e.ad
            assert s["alan"] == e.alan, e.ad
            assert s.get("on_kosul") == e.on_kosul, f"{e.ad}: ön koşul ayrıştı"

    def test_kayit_bir_ayar_dosyasi_degil(self):
        """Kod `esikler.json`'ı okumaz: eşik JSON düzenlenerek değiştirilemez."""
        for modul in (kapilar, kapilar_v2):
            kaynak = Path(modul.__file__).read_text(encoding="utf-8")
            assert "esikler.json" not in kaynak.replace("test_esikler", ""), modul.__name__

    def test_girdiler_kodla_esit(self, kayit):
        g = {s["ad"]: s["deger"] for s in kayit["girdiler"]}
        assert g["asgari_yillik_pencere_gun"] == kapilar.ASGARI_YILLIK_PENCERE_GUN
        assert (
            g["asgari_yillik_pencere_gun"] * 24 * 3_600_000
            == metrikler_mod.ASGARI_YILLIK_PENCERE_MS
        )
        assert g["coklu_test_cekilis_sayisi"] == kapilar.COKLU_TEST_CEKILIS_SAYISI
        assert g["yanlis_pozitif"] == kapilar_v2.YANLIS_POZITIF


class TestHerSatirinKaynagiVeKarariVar:
    def test_kaynak_sinifi_gecerli(self, kayit):
        for s in kayit["kapilar"] + kayit["girdiler"]:
            assert s["kaynak"] in KAYNAKLAR, f"{s['ad']}: kaynak {s['kaynak']!r}"
            assert len(s["gerekce"]) > 40, f"{s['ad']}: gerekçe yok"

    def test_karar_kararlar_md_de_var(self, kayit, karar_basliklari):
        for s in kayit["kapilar"] + kayit["girdiler"]:
            assert re.fullmatch(r"K-\d{3}", s["karar"]), s["ad"]
            assert s["karar"] in karar_basliklari, f"{s['ad']}: {s['karar']} Kararlar.md'de yok"
        assert kayit["politika"]["kabul_karari"] in karar_basliklari

    def test_olculmus_satir_kanit_dosyasi_tasiyor(self, kayit):
        for s in kayit["kapilar"]:
            if s["kaynak"] in ("olculdu", "null-kalibre"):
                assert s.get("kayit"), f"{s['ad']}: ölçülmüş eşiğin kanıt dosyası yok"
                assert (KOK / s["kayit"]).exists(), f"{s['ad']}: {s['kayit']} yok"
                assert s.get("olcum_tarihi"), s["ad"]
            if s["kaynak"] == "istah":
                assert s.get("gozden_gecirme"), f"{s['ad']}: iştah eşiğinin koşulu yok"

    def test_karar_verilmemis_kalem_kayitta_yok(self, kayit):
        """DECISION REQUIRED bir sayı eşik değildir; kayıtta yalnız kabul edilmiş satır durur."""
        for s in kayit["kapilar"] + kayit["girdiler"]:
            assert isinstance(s["deger"], int | float)
            assert not isinstance(s["deger"], bool), s["ad"]
            assert "DECISION" not in s["kaynak"] and "DECISION" not in s["karar"], s["ad"]


class TestOosSuresiEsigiOlcumdenGeliyor:
    def test_asgari_oos_gun_fotograftaki_en_kisa_oos(self):
        """Sınır, fotoğraftaki 48 çekilişin en kısa OOS'unun kendisi — elle değil, yuvarlanmadan."""
        kayit = json.loads(OOS_SURESI_KAYDI.read_text(encoding="utf-8"))
        assert kayit["cekilis_sayisi"] == kapilar.COKLU_TEST_CEKILIS_SAYISI
        assert kayit["asgari_oos_gun"] == kapilar.ASGARI_OOS_GUN
        assert min(c["oos_gun"] for c in kayit["cekilisler"]) == kapilar.ASGARI_OOS_GUN
        tf_ms = timeframe_ms(kayit["asgari_oos_timeframe"])
        assert kapilar.oos_suresi_gun(kayit["asgari_oos_bar"], tf_ms) == kapilar.ASGARI_OOS_GUN

    def test_kalibrasyon_uyeleri_kendi_kapisindan_geciyor(self):
        """Eşiğin ölçüldüğü her çekiliş `oos_suresi`den geçer: eşik kendi kaynağını eleyemez."""
        kayit = json.loads(OOS_SURESI_KAYDI.read_text(encoding="utf-8"))
        esik = next(e for e in kapilar.ESIKLER if e.ad == "oos_suresi")
        for c in kayit["cekilisler"]:
            assert esik.gecti_mi(c["oos_gun"]) is True, c["kimlik"][:12]
        for c in kayit["olculemez_cekilisler"]:
            assert esik.gecti_mi(c["oos_gun"]) is False, c["kimlik"][:12]

    def test_kayit_fotografla_ayni_defter_halini_gosteriyor(self):
        """Fotoğraf değişirse (yeni çekiliş) OOS süresi ölçümü de bayattır."""
        from scryne_quant.research import coklu_test_fotograf as f

        kayit = json.loads(OOS_SURESI_KAYDI.read_text(encoding="utf-8"))
        fotograf = f.oku(KOK / f.VARSAYILAN_YOL)
        assert kayit["fotograf"]["olculebilir"] == fotograf["olculebilir"]
        assert kayit["fotograf"]["defter_sayisi"] == fotograf["defter_sayisi"]
        assert set(c["kimlik"] for c in kayit["cekilisler"]) == set(fotograf["cekilis_kimlikleri"])

    def test_olculemez_cekilisler_esige_girmiyor(self):
        """FX çekilişleri (21,5 gün) fotoğrafta ölçülemez; en kısa OOS onlardan gelmez."""
        kayit = json.loads(OOS_SURESI_KAYDI.read_text(encoding="utf-8"))
        for c in kayit["olculemez_cekilisler"]:
            assert c["kimlik"] not in {x["kimlik"] for x in kayit["cekilisler"]}
        assert kayit["asgari_oos_gun"] > 500
