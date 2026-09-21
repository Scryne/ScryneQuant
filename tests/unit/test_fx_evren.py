"""FX PIT evren tablosu ve hayatta kalma yanlılığı. (K-090, R3 Paket 1(e))

Kanıt sentetik `kesif-*.json` / manifesto dosyalarıyla verilir; ölçüm yalnız tam kanıtlı
haftalarda yapılır, eksik kanıt "yok" sayılmaz, kaynak çelişkisi hata.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from scryne_quant.data import fx, fx_evren
from scryne_quant.data.fx import FxDepo
from scryne_quant.data.fx_evren import (
    FxEvrenHatasi,
    FxEvrenKurali,
    evren_kur,
    hayatta_kalma,
    kanit_topla,
    kapsam,
    pit_tablo,
    tablo_hash,
)

KOK = Path(__file__).resolve().parents[2]
UC = ("EURUSD", "GBPUSD", "USDJPY")
HAFTALAR = ("2024-2", "2024-3", "2024-4", "2024-5")


def _kesif_yaz(depo: FxDepo, pair: str, haftalar: dict[str, bool], ad: str = "kesif-t.json"):
    yol = depo.kok / fx.GELEN_DIZINI / pair / ad
    yol.parent.mkdir(parents=True, exist_ok=True)
    pazar = {"2024-2": "2024-01-07", "2024-3": "2024-01-14", "2024-4": "2024-01-21",
             "2024-5": "2024-01-28"}
    yol.write_text(json.dumps({"pair": pair, "haftalar": {
        h: {"pazar": pazar[h], "var": v} for h, v in haftalar.items()}}), encoding="utf-8")


def _manifesto_yaz(depo: FxDepo, pair: str, haftalar: dict[str, bool]):
    yol = depo.manifesto_yolu(pair)
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps({"pair": pair, "sha256": "x", "haftalar": {
        h: {"durum": "var" if v else "yok", "pazar": "2024-01-07"} for h, v in haftalar.items()}}),
        encoding="utf-8")


class TestKural:
    def test_kimlik_icerik_hashli_ve_sozlesme_disi_cift_red(self):
        k = FxEvrenKurali(ciftler=UC)
        assert k.kimlik == fx_evren.nesne_hash(k.sozluk())
        assert k.sozluk()["kural"] == "dosya-var" and k.sozluk()["takvim"] == "fx-5x24"
        karisik = FxEvrenKurali(ciftler=("USDJPY", "EURUSD", "GBPUSD"))
        assert karisik.kimlik == k.kimlik  # sıra bağımsız
        with pytest.raises(FxEvrenHatasi, match="sözleşme dışı"):
            FxEvrenKurali(ciftler=("EURUSD", "ABCDEF"))
        assert FxEvrenKurali().ciftler == fx.FXCM_CIFTLER  # 21 çift


class TestHaftaAnahtari:
    @pytest.mark.parametrize("hafta,pazar", [("2023-53", "2023-12-31"), ("2024-2", "2024-01-07"),
                                             ("2012-1", "2012-01-01"), ("2026-37", "2026-09-13"),
                                             ("2016-1", "2016-01-03"), ("2015-52", "2015-12-27")])
    def test_pazar_cozumu(self, hafta, pazar):
        assert fx_evren._pazar(hafta) == dt.date.fromisoformat(pazar)

    def test_olmayan_anahtar(self):
        with pytest.raises(FxEvrenHatasi, match="çözülemedi"):
            fx_evren._pazar("2024-1")  # 2024/1 yok (1 Ocak haftası 2023/53)
        with pytest.raises(FxEvrenHatasi, match="çözülemedi"):
            fx_evren._pazar("2015-53")  # kayma 0 yılında 53 yok (K-091)


class TestKanitVeTablo:
    def test_kesif_ve_manifesto_birlesir_celiski_hata(self, tmp_path):
        depo = FxDepo(tmp_path)
        _kesif_yaz(depo, "EURUSD", {"2024-2": True, "2024-3": False})
        _manifesto_yaz(depo, "EURUSD", {"2024-3": False, "2024-4": True})
        varlik, kaynaklar = kanit_topla(depo, UC)
        assert varlik == {"EURUSD": {"2024-2": True, "2024-3": False, "2024-4": True}}
        assert kaynaklar == {"EURUSD": {"hafta": 3, "var": 2}}
        _manifesto_yaz(depo, "EURUSD", {"2024-3": True})  # kesif yok diyor, manifesto var
        with pytest.raises(FxEvrenHatasi, match="kanıt çelişkisi"):
            kanit_topla(depo, UC)

    def test_tablo_yalniz_kanitli_hucreler_deterministik(self):
        k = FxEvrenKurali(ciftler=UC)
        varlik = {
            "GBPUSD": {"2024-3": True, "2024-2": True},
            "EURUSD": {"2024-2": True, "2024-3": False},
        }
        t = pit_tablo(k, varlik)
        assert len(t) == 4
        assert list(t.columns) == ["hafta", "pazar", "kanonik_id", "sembol", "uye", "kanit"]
        assert t.iloc[0].to_dict() == {
            "hafta": "2024-2", "pazar": "2024-01-07", "kanonik_id": "fxcm-fx:cfd:EURUSD@2012-01-01",
            "sembol": "EURUSD", "uye": True, "kanit": "var",
        }
        assert list(t["sembol"]) == ["EURUSD", "GBPUSD", "EURUSD", "GBPUSD"]
        assert "USDJPY" not in set(t["sembol"])  # kanıt yok → satır yok (bilinmiyor)
        ters = {"EURUSD": varlik["EURUSD"], "GBPUSD": varlik["GBPUSD"]}
        assert tablo_hash(t) == tablo_hash(pit_tablo(k, ters))
        assert pit_tablo(k, {}).empty


class TestHayattaKalma:
    def _varlik(self, **ozel):
        v = {p: dict.fromkeys(HAFTALAR, True) for p in UC}
        for p, h in ozel.items():
            v[p].update(h)
        return v

    def test_tekduze_kanit_sifir_yanlilik(self):
        k = FxEvrenKurali(ciftler=UC)
        h = hayatta_kalma(pit_tablo(k, self._varlik()), k)
        assert (h["olculen_hafta"], h["kismi_kanit_hafta"]) == (4, 0)
        assert (h["medyan"], h["azami"], h["sifir_olmayan_hafta"]) == (0.0, 0.0, 0)
        assert h["haftalar"] == {} and h["saglayici_boslugu"] == []

    def test_bir_ciftin_eksik_haftasi_olculur(self):
        k = FxEvrenKurali(ciftler=UC)
        h = hayatta_kalma(pit_tablo(k, self._varlik(USDJPY={"2024-2": False, "2024-3": False})), k)
        assert h["olculen_hafta"] == 4 and h["sifir_olmayan_hafta"] == 2
        assert h["medyan"] == pytest.approx(1 / 6) and h["azami"] == pytest.approx(1 / 3)
        assert h["haftalar"]["2024-2"]["bugun_olup_pit_olmayan"] == ["USDJPY"]
        assert h["haftalar"]["2024-2"]["pit_uye"] == 2

    def test_saglayici_boslugu_yanlilik_degil(self):
        k = FxEvrenKurali(ciftler=UC)
        v = self._varlik(**{p: {"2024-4": False} for p in UC})
        h = hayatta_kalma(pit_tablo(k, v), k)
        assert h["saglayici_boslugu"] == ["2024-4"]
        assert h["olculen_hafta"] == 3 and h["azami"] == 0.0

    def test_kismi_kanit_olcume_girmez(self):
        k = FxEvrenKurali(ciftler=UC)
        v = self._varlik()
        del v["USDJPY"]["2024-5"]  # o hafta USDJPY için kanıt yok
        h = hayatta_kalma(pit_tablo(k, v), k)
        assert h["olculen_hafta"] == 3 and h["kismi_kanit_hafta"] == 1


class TestKapsamVeYazma:
    def test_kapsam_tam_ve_kismi(self, tmp_path):
        k = FxEvrenKurali(ciftler=UC)
        depo = FxDepo(tmp_path)
        for p in UC:
            _kesif_yaz(depo, p, dict.fromkeys(HAFTALAR, True))
        varlik, _ = kanit_topla(depo, UC)
        assert kapsam(varlik, k)["durum"] == "tam"
        _kesif_yaz(depo, "EURUSD", {"2024-2": True}, ad="kesif-b.json")
        del varlik["USDJPY"]["2024-5"]
        kp = kapsam(varlik, k)
        assert kp["durum"] == "kismi" and kp["tam_kanitli_cift"] == ["EURUSD", "GBPUSD"]
        assert (kp["ilk_hafta"], kp["son_hafta"]) == ("2024-2", "2024-5")

    def test_evren_kur_yazar_ve_deterministik(self, tmp_path):
        k = FxEvrenKurali(ciftler=UC)
        depo = FxDepo(tmp_path)
        for p in UC:
            _kesif_yaz(depo, p, dict.fromkeys(HAFTALAR, True))
        m1 = evren_kur(depo, k)
        m2 = evren_kur(depo, k)
        assert m1 == m2 and m1["kural_kimlik"] == k.kimlik and m1["satir"] == 12
        assert m1["hayatta_kalma"]["medyan"] == 0.0 and m1["kapsam"]["durum"] == "tam"
        meta_yol = tmp_path / "_evren" / f"{k.kimlik[:12]}.json"
        meta = json.loads(meta_yol.read_text(encoding="utf-8"))
        assert meta["tablo_hash"] == m1["tablo_hash"]
        assert (tmp_path / "_evren" / f"{k.kimlik[:12]}.parquet").exists()


@pytest.mark.skipif(not (KOK / "data" / "fx" / "EURUSD").exists(), reason="gerçek FX deposu yok")
class TestGercekKanit:
    def test_tam_kanit_ve_olcum(self):
        """K-091 ölçümü (2026-09-21): 21 çift × 773 hafta HEAD; 2012 h1 21/21; medyan 0."""
        varlik, _ = kanit_topla(FxDepo(KOK / "data" / "fx"), fx.FXCM_CIFTLER)
        kp = kapsam(varlik, FxEvrenKurali())
        if kp["durum"] != "tam":
            pytest.skip("tam HEAD kanıtı yerelde yok")
        assert all(varlik[p]["2012-1"] for p in fx.FXCM_CIFTLER)  # varsayım değil, ölçüm
        assert all(not varlik[p]["2011-52"] for p in fx.FXCM_CIFTLER)  # kaynak öncesi
        h = hayatta_kalma(pit_tablo(FxEvrenKurali(), varlik), FxEvrenKurali())
        assert h["kismi_kanit_hafta"] == 0 and h["olculen_hafta"] >= 700
        assert h["medyan"] == 0.0 and h["sifir_olmayan_hafta"] <= 10
        assert "2011-52" in h["saglayici_boslugu"]
