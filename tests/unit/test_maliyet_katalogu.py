"""Enstrüman-başı maliyet: katalog + çözümleyici, çok modelli motor, kayıt/paper kimliği. (K-084)

Birincil değişmez: **tek model = bugünkü Binance spot yolu, bit-aynı.** `maliyetler=None`
verildiğinde fill'ler, `Sonuc` alanları ve `config_hash` formülü Paket 3 öncesiyle aynı; çok
modelli blok kayda **yalnız gerçekten çok model varsa** girer.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from scryne_quant.backtest.coklu_motor import CokluBacktest, CokluBacktestHatasi
from scryne_quant.backtest.sonuc import Sonuc
from scryne_quant.cli.main import _maliyet_govdesi
from scryne_quant.common import maliyet as maliyet_mod
from scryne_quant.common.hash import nesne_hash
from scryne_quant.common.maliyet import (
    MaliyetHatasi,
    MaliyetKatalogu,
    MaliyetModeli,
    SembolMaliyeti,
    gecici_mi,
    govde,
    govdeden,
    maliyetler_govdeden,
    maliyetler_govdesi,
)
from scryne_quant.data.kimlik import Enstruman, kanonik_kimlik
from scryne_quant.live.evren_kurulum import KurulumUyusmazligi, evren_kurulum_kimlikten
from scryne_quant.research import evren_kosu as evren_kosu_mod
from scryne_quant.research import tekrar as tekrar_mod
from scryne_quant.risk import limitler as limit_mod
from scryne_quant.strategy.kosu import evren_gorunum_kur
from scryne_quant.strategy.kutuphane import EVREN_KIYAS
from tests.conftest import PlanliHedef

KOK = Path(__file__).resolve().parents[2]
REFERANS = json.loads((KOK / "tests/fixtures/coklu_referans.json").read_text(encoding="utf-8"))
SENARYO = {s["ad"]: s for s in REFERANS["senaryolar"]}["eszamanli_dengeleme"]
SEMBOLLER = tuple(REFERANS["semboller"])  # ("AAAUSDT", "BBBUSDT")
A, B = SEMBOLLER

DUSUK = MaliyetModeli(fee_taker_bps=10.0, slippage_bps=1.0)
YUKSEK = MaliyetModeli(fee_taker_bps=10.0, slippage_bps=50.0)


def _bar_dizileri(barlar):
    diziler = {
        "open_time": np.array([b["open_time"] for b in barlar], dtype="int64"),
        "trades": np.array([b["trades"] for b in barlar], dtype="int64"),
        "quality_status": np.array([b["quality_status"] for b in barlar], dtype=object),
    }
    for alan in ("open", "high", "low", "close", "volume", "quote_volume"):
        diziler[alan] = np.array([float(b[alan]) for b in barlar], dtype="float64")
    for d in diziler.values():
        d.flags.writeable = False
    return diziler


def _kosu(maliyet: MaliyetModeli, maliyetler=None) -> Sonuc:
    strateji = PlanliHedef(
        {h["bar"]: {s: float(a) for s, a in h["agirliklar"].items()} for h in SENARYO["hedefler"]}
    )
    diziler = {s: _bar_dizileri(SENARYO["barlar"][s]) for s in SEMBOLLER}
    n = len(diziler[A]["open_time"])
    gorunum = evren_gorunum_kur(
        "1h", diziler, {s: np.ones(n, dtype=bool) for s in SEMBOLLER}, strateji
    )
    return CokluBacktest(strateji, maliyet, maliyetler=maliyetler).calistir(gorunum)


def _katalog(tmp_path: Path, **modeller: MaliyetModeli) -> MaliyetKatalogu:
    """Geçici katalog: global = yürürlükteki dosya, diğerleri `tmp/<id>.json`."""
    dizin = tmp_path / "maliyet"
    for kimlik, model in modeller.items():
        maliyet_mod.yaz(model, dizin / f"{kimlik}.json")
    return MaliyetKatalogu(global_yol=KOK / "config" / "maliyet.json", dizin=dizin)


def _enstruman(sembol: str, **ek) -> Enstruman:
    venue = ek.pop("venue", "binance-spot")
    tip = ek.pop("instrument_type", "spot")
    return Enstruman(
        kanonik_id=kanonik_kimlik(venue, tip, sembol, "2024-01-01"),
        venue=venue,
        sembol=sembol,
        gecerli_baslangic_ms=1704067200000,
        gecerli_bitis_ms=1704070800000,
        bar_sayisi=1,
        kirilma_ile_basladi=False,
        instrument_type=tip,
        **ek,
    )


# ------------------------------------------------------------------ çözümleyici


class TestKatalog:
    def test_global_yurulukteki_model(self):
        k = MaliyetKatalogu()
        assert k.coz("global", binance_spot_kripto=True) == maliyet_mod.yukle()
        assert k.yol("global") == maliyet_mod.VARSAYILAN_YOL

    def test_gecerli_kimlik_dogru_dosya(self, tmp_path):
        k = _katalog(tmp_path, test_dusuk=DUSUK)
        assert k.yol("test_dusuk") == tmp_path / "maliyet" / "test_dusuk.json"
        assert k.coz("test_dusuk", binance_spot_kripto=False) == DUSUK

    def test_eksik_kimlik_fail_closed(self, tmp_path):
        k = _katalog(tmp_path)
        with pytest.raises(MaliyetHatasi, match="dosya yok"):
            k.coz("yok", binance_spot_kripto=False)

    def test_bozuk_dosya_fail_closed(self, tmp_path):
        dizin = tmp_path / "maliyet"
        dizin.mkdir()
        (dizin / "bozuk_json.json").write_text("{not json", encoding="utf-8")
        (dizin / "bozuk_sema.json").write_text(
            json.dumps({"fee_taker_bps": 10.0, "slippage_bps": 5.0, "spread_bps": 1.0}),
            encoding="utf-8",
        )
        (dizin / "negatif.json").write_text(
            json.dumps({"fee_taker_bps": -1.0, "slippage_bps": 5.0}), encoding="utf-8"
        )
        k = MaliyetKatalogu(global_yol=KOK / "config" / "maliyet.json", dizin=dizin)
        for kimlik in ("bozuk_json", "bozuk_sema", "negatif"):
            with pytest.raises(MaliyetHatasi, match="bozuk"):
                k.coz(kimlik, binance_spot_kripto=False)

    def test_global_binance_spot_disi_red(self, tmp_path):
        with pytest.raises(MaliyetHatasi, match="yalnız Binance spot"):
            _katalog(tmp_path).coz("global", binance_spot_kripto=False)

    @pytest.mark.parametrize("kotu", ["", "../x", "a/b", "a\\b", "boş luk", ".gizli", "x" * 65])
    def test_gecersiz_kimlik_dosya_yoluna_donusmez(self, tmp_path, kotu):
        with pytest.raises(MaliyetHatasi, match="geçersiz"):
            _katalog(tmp_path).yol(kotu)

    def test_deterministik(self, tmp_path):
        k = _katalog(tmp_path, m=DUSUK)
        assert k.coz("m", binance_spot_kripto=False) == k.coz("m", binance_spot_kripto=False)
        assert nesne_hash(govde(k.coz("m", binance_spot_kripto=False))) == nesne_hash(govde(DUSUK))

    def test_ayni_govde_farkli_kimlik_iki_ayri_model(self, tmp_path):
        """Kimlik kararlı ad, içerik hash'i değil (K-084/3): aynı sayılar, iki ayrı kayıt."""
        k = _katalog(tmp_path, bir=DUSUK, iki=DUSUK)
        m = {A: SembolMaliyeti("bir", k.coz("bir", binance_spot_kripto=False)),
             B: SembolMaliyeti("iki", k.coz("iki", binance_spot_kripto=False))}
        blok = maliyetler_govdesi(m)
        assert blok[A]["govde"] == blok[B]["govde"] and blok[A]["id"] != blok[B]["id"]
        assert nesne_hash(blok) != nesne_hash(maliyetler_govdesi({A: m[A], B: m[A]}))


class TestEnstrumanCozumleme:
    def test_hepsi_global_none_ama_cozumleme_yapilir(self):
        kimlikler = {A: [_enstruman(A)], B: [_enstruman(B)]}
        assert evren_kosu_mod.enstruman_maliyetleri(MaliyetKatalogu(), kimlikler) is None
        # Global dosyası okunamıyorsa None'a düşmez: fail closed.
        k = MaliyetKatalogu(global_yol="config/yok.json")
        with pytest.raises(MaliyetHatasi, match="dosya yok"):
            evren_kosu_mod.enstruman_maliyetleri(k, kimlikler)

    def test_karisik_evrende_her_sembol_cozumlenir(self, tmp_path):
        k = _katalog(tmp_path, test_yuksek=YUKSEK)
        kimlikler = {
            A: [_enstruman(A)],
            B: [_enstruman(B, venue="test-venue", maliyet_modeli_id="test_yuksek")],
        }
        m = evren_kosu_mod.enstruman_maliyetleri(k, kimlikler)
        assert m is not None and set(m) == {A, B}
        assert m[A].kimlik == "global" and m[A].model == maliyet_mod.yukle()
        assert m[B].kimlik == "test_yuksek" and m[B].model == YUKSEK

    def test_segmentler_farkli_kimlik_tasiyamaz(self, tmp_path):
        k = _katalog(tmp_path, x=DUSUK, y=DUSUK)
        seg1 = _enstruman(A, venue="test-venue", maliyet_modeli_id="x")
        seg2 = dataclasses.replace(seg1, maliyet_modeli_id="y")
        with pytest.raises(MaliyetHatasi, match="farklı maliyet modeli"):
            evren_kosu_mod.enstruman_maliyetleri(k, {A: [seg1, seg2]})


# ------------------------------------------------------------------ geriye uyum (tek model)


class TestTekModelBitAyni:
    def test_maliyetler_none_kayit_bicimi_ve_config_hash_formulu_ayni(self):
        s = _kosu(DUSUK)
        assert s.maliyetler is None and s.gecici is None  # eski `Sonuc` biçimi aynen
        assert "maliyetler" not in s.sozluk()["config"]
        # Paket 3 öncesi `config_hash` formülü — birebir aynı sözlük.
        eski = nesne_hash({
            "strateji": s.strateji, "maliyet": s.maliyet,
            "baslangic_sermaye": s.baslangic_sermaye, "seed": s.seed,
            "sembol": s.veri.sembol, "timeframe": s.veri.timeframe,
        })
        assert s.config_hash == eski
        assert s.maliyet == DUSUK.sozluk()

    def test_tek_model_ile_ayni_modelin_haritasi_ayni_fill(self):
        """Fill aritmetiği: her sembole aynı modeli vermek tek modelle aynı işlemleri üretir."""
        tek = _kosu(DUSUK)
        cok = _kosu(DUSUK, {A: SembolMaliyeti("x", DUSUK), B: SembolMaliyeti("x", DUSUK)})
        assert tek.sonuc_hash == cok.sonuc_hash
        assert cok.maliyetler is not None and cok.config_hash != tek.config_hash  # blok var

    def test_govde_sabitleri(self):
        m = maliyet_mod.yukle()
        assert govde(m) == _maliyet_govdesi(m)
        assert govdeden(govde(m)) == m and tekrar_mod._maliyet(govde(m)) == m
        # Paket 1 sabiti (test_enstruman_v2) ile aynı sayı; ikisi birden kırılmalı.
        ham = json.dumps(govde(m), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        assert hashlib.sha256(ham.encode()).hexdigest() == (
            "fe9f73bb70ced67217b937ed14ec6368004af6036edb17cbb3a4e755e1979ab5"
        )
        assert nesne_hash(m.sozluk()) == (
            "5022dec95569f39bcc620cfacb5b330c6d5f524ff5e3383b880de62a45ecf2a1"
        )


# ------------------------------------------------------------------ çok model


class TestCokModel:
    def test_fill_fiyatlari_model_bazinda(self):
        dusuk = _kosu(DUSUK)
        karisik = _kosu(DUSUK, {A: SembolMaliyeti("d", DUSUK), B: SembolMaliyeti("y", YUKSEK)})
        # A'nın fill'leri aynı model → aynı; B'ninkiler yüksek slippage → farklı.
        def turlar(s: Sonuc, sembol: str):
            return [(i.acilis_ms, i.giris_notional, i.komisyon) for i in s.islemler
                    if i.sembol == sembol]

        assert turlar(dusuk, A) and turlar(dusuk, B)
        assert turlar(karisik, B) != turlar(dusuk, B)
        # Sıra ve sayı: aynı barlarda aynı semboller, aynı yön.
        assert [(i.sembol, i.acilis_ms) for i in karisik.islemler] == [
            (i.sembol, i.acilis_ms) for i in dusuk.islemler
        ]
        assert karisik.sonuc_hash != dusuk.sonuc_hash

    def test_ekleme_sirasi_hashi_degistirmez(self):
        m1 = {A: SembolMaliyeti("d", DUSUK), B: SembolMaliyeti("y", YUKSEK)}
        m2 = {B: SembolMaliyeti("y", YUKSEK), A: SembolMaliyeti("d", DUSUK)}
        assert list(maliyetler_govdesi(m2)) == [A, B]
        assert nesne_hash(maliyetler_govdesi(m1)) == nesne_hash(maliyetler_govdesi(m2))
        s1, s2 = _kosu(DUSUK, m1), _kosu(DUSUK, m2)
        assert (s1.config_hash, s1.sonuc_hash) == (s2.config_hash, s2.sonuc_hash)

    def test_eksik_sembol_modeli_fail_closed(self):
        with pytest.raises(CokluBacktestHatasi, match="maliyet modeli olmayan"):
            _kosu(DUSUK, {A: SembolMaliyeti("d", DUSUK)})

    def test_cok_modelli_kayit_gidis_donus(self):
        m = {A: SembolMaliyeti("d", DUSUK), B: SembolMaliyeti("y", YUKSEK)}
        s = _kosu(DUSUK, m)
        blok = s.sozluk()["config"]["maliyetler"]
        assert blok == maliyetler_govdesi(m)
        geri = maliyetler_govdeden(json.loads(json.dumps(blok)))
        assert geri == dict(m)
        with pytest.raises(MaliyetHatasi):
            maliyetler_govdeden({A: {"id": "d"}})  # govde yok
        with pytest.raises(MaliyetHatasi):
            maliyetler_govdeden({A: {"id": "d", "govde": {"fee_taker_bps": "x"}}})

    def test_tek_sembollu_tekrar_cok_modelli_kaydi_reddeder(self):
        kayit = {
            "tip": "tarama",
            "kimlik": {"veri_sha256": "a"},
            "strateji": "sma_kesisim",
            "girdi": {
                "maliyet": govde(DUSUK),
                "maliyetler": maliyetler_govdesi({A: SembolMaliyeti("d", DUSUK)}),
                "sembol": A, "timeframe": "1h", "baslangic_sermaye": 10_000.0,
            },
        }
        with pytest.raises(tekrar_mod.TekrarHatasi, match="enstrüman-başı maliyet"):
            tekrar_mod.tekrar_uret(kayit, {}, "a")
        kayit["girdi"]["maliyetler"] = {A: {"id": "d"}}  # bozuk blok da açıkça hata
        with pytest.raises(MaliyetHatasi):
            tekrar_mod.tekrar_uret(kayit, {}, "a")


# ------------------------------------------------------------------ geçici


class TestGecici:
    def test_biri_gecici_kosu_gecici(self):
        gecici = MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0)  # kalibrasyon yok
        kalibre = maliyet_mod.yukle()
        assert not kalibre.gecici and gecici.gecici
        assert gecici_mi(kalibre, None) is False and gecici_mi(gecici, None) is True
        assert gecici_mi(kalibre, {A: SembolMaliyeti("k", kalibre), B: SembolMaliyeti("g", gecici)})
        hepsi_kalibre = {A: SembolMaliyeti("k", kalibre), B: SembolMaliyeti("k", kalibre)}
        assert not gecici_mi(gecici, hepsi_kalibre)

    def test_promotion_engeli_cok_modelde(self):
        kalibre = maliyet_mod.yukle()
        gecici = MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0)
        s = _kosu(kalibre, {A: SembolMaliyeti("k", kalibre), B: SembolMaliyeti("g", gecici)})
        assert s.gecici is True and "gecici_maliyet_modeli" in s.promotion_engelleri
        s2 = _kosu(kalibre, {A: SembolMaliyeti("k", kalibre), B: SembolMaliyeti("k", kalibre)})
        assert s2.gecici is False and "gecici_maliyet_modeli" not in s2.promotion_engelleri
        # Eski kayıt biçimi: `gecici=None` → `maliyet["gecici"]` okunur (K-021, değişmedi).
        assert "gecici_maliyet_modeli" in _kosu(gecici).promotion_engelleri


# ------------------------------------------------------------------ paper / toparlanma


def _gozlem_kimligi(**ek) -> dict:
    return {
        "kosu_adi": "t", "mod": "gozlem", "timeframe": "1h",
        "strateji": EVREN_KIYAS["evren_esit_agirlik"]().sozluk(),
        "maliyet": maliyet_mod.yukle().sozluk(),
        "limit_kimligi": limit_mod.yukle().kimlik(),
        "baslangic_sermaye": 10_000.0, "sifira_yaz_bar": 48, "evren_kural_kimlik": "x",
        **ek,
    }


class TestPaperToparlanma:
    def test_tek_modelli_gozlem_kimligi_dogrulaniyor(self):
        kurulum = evren_kurulum_kimlikten(_gozlem_kimligi())
        assert kurulum["maliyet"] == maliyet_mod.yukle() and "maliyetler" not in kurulum

    def test_cok_modelli_kimlik_katalogla_dogrulaniyor(self, tmp_path, monkeypatch):
        monkeypatch.setattr(maliyet_mod, "VARSAYILAN_KATALOG_DIZINI", tmp_path / "maliyet")
        k = _katalog(tmp_path, test_y=YUKSEK)
        m = {A: SembolMaliyeti("global", maliyet_mod.yukle()), B: SembolMaliyeti("test_y", YUKSEK)}
        kurulum = evren_kurulum_kimlikten(_gozlem_kimligi(maliyetler=maliyetler_govdesi(m)))
        assert kurulum["maliyetler"] == m
        # Katalogdaki dosya değişti → kayıtla uyuşmaz → fail closed.
        maliyet_mod.yaz(DUSUK, k.yol("test_y"))
        with pytest.raises(KurulumUyusmazligi, match="maliyetler"):
            evren_kurulum_kimlikten(_gozlem_kimligi(maliyetler=maliyetler_govdesi(m)))

    def test_eksik_model_fail_closed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(maliyet_mod, "VARSAYILAN_KATALOG_DIZINI", tmp_path / "bos")
        m = {A: SembolMaliyeti("yok", YUKSEK)}
        with pytest.raises(KurulumUyusmazligi, match="dosya yok") as h:
            evren_kurulum_kimlikten(_gozlem_kimligi(maliyetler=maliyetler_govdesi(m)))
        assert isinstance(h.value.__cause__, MaliyetHatasi)
        monkeypatch.setattr(maliyet_mod, "VARSAYILAN_YOL", tmp_path / "yok.json")
        with pytest.raises(KurulumUyusmazligi, match="dosya yok"):
            evren_kurulum_kimlikten(_gozlem_kimligi())

    @pytest.mark.skipif(
        not (KOK / "runs" / "paper" / "gozlem-1.sqlite").exists(), reason="yerel gözlem koşusu yok"
    )
    def test_gercek_gozlem_kosulari_ayni_maliyet_kimligi(self):
        """host-1'in tek sembollü gözlem koşuları: kayıtlı `maliyet` bloğu bugünkü modelle aynı."""
        import sqlite3

        beklenen = json.loads(json.dumps(maliyet_mod.yukle().sozluk()))
        for ad in ("gozlem-1", "gozlem-2"):
            yol = KOK / "runs" / "paper" / f"{ad}.sqlite"
            if not yol.exists():
                continue
            with sqlite3.connect(f"file:{yol.as_posix()}?mode=ro", uri=True) as b:
                (kayit,) = b.execute("SELECT maliyet FROM kosu WHERE id = 1").fetchone()
            assert json.loads(kayit) == beklenen, ad
