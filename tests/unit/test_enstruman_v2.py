"""Enstrüman v2 alan ayrıştırması ve bayt/kimlik değişmezliği bekçileri. (R2, K-083 taslağı)

R2'nin ilk paketi `Enstruman`'a sözleşme alanları ekler ama **hiçbir kimliği değiştirmez**.
Bu dosya dört şeyi sabitler:

A) v1 anahtarları aynı sırada, aynı isimle, aynı değerle (altın hash HEAD `dbe29ba`'da ölçüldü);
B) v2 alanları beklenen isim/tip/varsayılanla var ve varsayılanlar bugünkü tek gerçeği kodluyor;
C) katalog kaydı deterministik; şema değişimi **beklenen** değişim (yalnız v2 anahtarları eklendi);
D) v2 alanları hiçbir deney/sonuç hash'ine girmiyor — statik (kaynak taraması) + davranışsal
   (`tablo_hash`, üyelik matrisi) + `_maliyet_govdesi` bayt sabiti.

Altın değerler `tools/`da değil burada: değişmeleri gereken gün bir K ile değişirler.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from scryne_quant.cli.main import _maliyet_govdesi
from scryne_quant.common import maliyet as maliyet_mod
from scryne_quant.common.hash import nesne_hash
from scryne_quant.common.maliyet import MaliyetModeli, SlippageKalibrasyonu
from scryne_quant.data.evren import EvrenHatasi, EvrenKurali, aylik_ozet, evren_tablosu, tablo_hash
from scryne_quant.data.izgara import uyelik_matrisi
from scryne_quant.data.kimlik import (
    ENSTRUMAN_TIPLERI,
    FINANSMANLI_TIPLER,
    KIRILMA_ASGARI_EKSIK_BAR,
    KIRILMA_ASGARI_LOG_ORAN,
    MALIYET_MODELI_GLOBAL,
    TAKVIM_24X7,
    TIP_SPOT,
    VARLIK_KRIPTO,
    VARLIK_SINIFLARI,
    VENUE_TIPLERI,
    Enstruman,
    KimlikHatasi,
    kanonik_kimlik,
    kimlikleri_kur,
    kirilmalar,
)
from scryne_quant.research.tekrar import _maliyet as tekrar_maliyet
from tests.conftest import bar_uret

KOK = Path(__file__).resolve().parents[2]
ESIK = {"asgari_eksik_bar": KIRILMA_ASGARI_EKSIK_BAR, "asgari_log_oran": KIRILMA_ASGARI_LOG_ORAN}
SRC = KOK / "src" / "scryne_quant"

#: v1 katalog anahtarları — HEAD `dbe29ba`'daki `Enstruman.sozluk()` sırası (ölçüldü, 2026-09-20).
V1_ANAHTARLAR = (
    "kanonik_id",
    "venue",
    "sembol",
    "gecerli_baslangic_ms",
    "gecerli_bitis_ms",
    "gecerli_baslangic",
    "gecerli_bitis",
    "bar_sayisi",
    "kirilma_ile_basladi",
)
#: v2 alanları: (ad, varsayılan). Sıra `sozluk()` sırası.
V2_ALANLAR = (
    ("asset_class", VARLIK_KRIPTO),
    ("instrument_type", TIP_SPOT),
    ("takvim_id", TAKVIM_24X7),
    ("tick_size", None),
    ("lot_size", None),
    ("contract_size", None),
    ("maliyet_modeli_id", MALIYET_MODELI_GLOBAL),
    ("finansman_modeli_id", None),
)
#: `nesne_hash(v1 sozluk)` — aynı fixture değerleriyle HEAD `dbe29ba`'da ölçüldü.
V1_SOZLUK_ALTIN_HASH = "4cd3052c072da440f5b890578ea2310e0a04c580a102999a4e03fe5489050135"


def _v1() -> Enstruman:
    return Enstruman(
        kanonik_id="binance-spot:BTCUSDT@2017-08-17",
        venue="binance-spot",
        sembol="BTCUSDT",
        gecerli_baslangic_ms=1502942400000,
        gecerli_bitis_ms=1502946000000,
        bar_sayisi=1,
        kirilma_ile_basladi=False,
    )


#: Bilinmeyen (tip kısıtı olmayan) test venue'su — `VENUE_TIPLERI`de yok, uydurma sözleşmeler için.
TEST_VENUE = "test-venue"
TARIH = "2017-08-17"  # `_v1()` başlangıcının UTC günü


def _kur(tip: str, venue: str = TEST_VENUE, **ek) -> Enstruman:
    """Alanlardan **tutarlı** kanonik kimlikle enstrüman; U17 tip-koşullu zorunlulukları dolu."""
    alanlar = dict(
        kanonik_id=kanonik_kimlik(venue, tip, "BTCUSDT", TARIH),
        venue=venue,
        sembol="BTCUSDT",
        gecerli_baslangic_ms=1502942400000,
        gecerli_bitis_ms=1502946000000,
        bar_sayisi=1,
        kirilma_ile_basladi=False,
        instrument_type=tip,
        maliyet_modeli_id="test-maliyet",
        finansman_modeli_id="test-finansman" if tip in FINANSMANLI_TIPLER else None,
    )
    alanlar.update(ek)
    return Enstruman(**alanlar)


def _v2_acik() -> Enstruman:
    """Varsayılan olmayan v2 değerleri — geçerli ama bugünkü depoda **olmayan** bir sözleşme."""
    return _kur(
        "vadeli",
        takvim_id="test-takvim",
        tick_size=0.1,
        lot_size=0.001,
        contract_size=100.0,
    )


# ------------------------------------------------------------------ varsayılan / açık


class TestVarsayilan:
    def test_v2_alanlari_bugunku_tek_gercegi_kodluyor(self):
        e = _v1()
        for ad, varsayilan in V2_ALANLAR:
            assert getattr(e, ad) == varsayilan, ad
        assert e.asset_class == "kripto" and e.instrument_type == "spot"
        assert e.takvim_id == "24x7" and e.maliyet_modeli_id == "global"

    def test_kimlikleri_kur_yalniz_v1_verir_v2_varsayilanda_kalir(self):
        df = bar_uret(200)
        (e,) = kimlikleri_kur(df, "1h", "btcusdt", kirilmalar(df, "1h", **ESIK))
        assert e.kanonik_id == "binance-spot:BTCUSDT@2023-11-14"
        assert {ad: getattr(e, ad) for ad, _ in V2_ALANLAR} == dict(V2_ALANLAR)

    def test_bilinmeyen_degerler_none_sifir_degil(self):
        """tick/lot/kontrat için güvenilir kaynak yok: `None`, uydurma bir sayı değil."""
        e = _v1()
        assert e.tick_size is None and e.lot_size is None and e.contract_size is None
        assert e.finansman_modeli_id is None

    def test_kumeler_bugunku_gercekle_sinirli(self):
        assert frozenset({"kripto"}) == VARLIK_SINIFLARI
        assert ENSTRUMAN_TIPLERI == ("spot", "vadeli", "cfd", "etf")


class TestAcik:
    def test_acik_degerler_korunuyor(self):
        e = _v2_acik()
        assert e.instrument_type == "vadeli" and e.takvim_id == "test-takvim"
        assert (e.tick_size, e.lot_size, e.contract_size) == (0.1, 0.001, 100.0)
        assert e.maliyet_modeli_id == "test-maliyet"
        assert e.finansman_modeli_id == "test-finansman"

    def test_donmus(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            _v1().instrument_type = "vadeli"  # type: ignore[misc]

    @pytest.mark.parametrize("ad", ["tick_size", "lot_size", "contract_size"])
    @pytest.mark.parametrize(
        "kotu", [0, -1.0, True, "0.1", float("nan"), float("inf"), -float("inf")]
    )
    def test_sonlu_pozitif_olmayan_buyukluk_reddediliyor(self, ad, kotu):
        with pytest.raises(KimlikHatasi, match=ad):
            dataclasses.replace(_v1(), **{ad: kotu})

    @pytest.mark.parametrize("ad", ["tick_size", "lot_size", "contract_size"])
    @pytest.mark.parametrize("iyi", [1e-9, 0.01, 1, 100.0])
    def test_sonlu_pozitif_buyukluk_kabul_ve_json_sonlu(self, ad, iyi):
        # `contract_size` spot'ta tanımsız (U17) — dolu değer için finansmanlı tip gerekir.
        taban = _kur("vadeli") if ad == "contract_size" else _v1()
        e = dataclasses.replace(taban, **{ad: iyi})
        assert getattr(e, ad) == iyi
        json.dumps(e.sozluk(), allow_nan=False)  # NaN/Infinity üretemez

    @pytest.mark.parametrize("ad", ["takvim_id", "maliyet_modeli_id"])
    def test_bos_kimlik_reddediliyor(self, ad):
        with pytest.raises(KimlikHatasi, match="boş olamaz"):
            dataclasses.replace(_v1(), **{ad: ""})


# ------------------------------------------------------------------ tip kümesi


class TestEnstrumanTipi:
    @pytest.mark.parametrize("tip", ENSTRUMAN_TIPLERI)
    def test_gecerli_tipler_kabul(self, tip):
        assert _kur(tip).instrument_type == tip

    @pytest.mark.parametrize("tip", ["perp", "SPOT", "futures", "", "option", None])
    def test_bilinmeyen_tip_red(self, tip):
        with pytest.raises(KimlikHatasi, match="bilinmeyen enstrüman tipi"):
            dataclasses.replace(_v1(), instrument_type=tip)

    @pytest.mark.parametrize(
        ("a", "b"), [("spot", "vadeli"), ("vadeli", "cfd"), ("cfd", "etf"), ("spot", "etf")]
    )
    def test_tipler_ayni_dayanakta_farkli_enstruman(self, a, b):
        """Aynı venue + sembol + tarih, farklı tip → farklı **kanonik kimlik** (K-083/U13)."""
        ea, eb = _kur(a), _kur(b)
        assert ea.kanonik_id != eb.kanonik_id
        assert ea != eb
        assert nesne_hash(ea.sozluk()) != nesne_hash(eb.sozluk())

    def test_sinif_ve_tip_ayri_eksen(self):
        """Kripto her tiple birleşebilir; bilinmeyen sınıf geçerli tiple de reddedilir."""
        for tip in ENSTRUMAN_TIPLERI:
            assert _kur(tip, asset_class="kripto")
        with pytest.raises(KimlikHatasi, match="bilinmeyen varlık sınıfı"):
            _kur("spot", asset_class="fx")
        with pytest.raises(KimlikHatasi, match="bilinmeyen varlık sınıfı"):
            dataclasses.replace(_v1(), asset_class="spot")  # tip adı sınıf değil


# ------------------------------------------------------------------ kanonik kimlik (U13)


class TestKanonikKimlik:
    def test_spot_kodlamasi_faz9_ile_ayni(self):
        """Altın: 761 gerçek kimlik bu biçimde; `kanonik_kimlik` spot için onu üretmek zorunda."""
        assert kanonik_kimlik("binance-spot", "spot", "btcusdt", "2017-08-17") == (
            "binance-spot:BTCUSDT@2017-08-17"
        )
        assert _v1().kanonik_id == kanonik_kimlik("binance-spot", "spot", "BTCUSDT", TARIH)

    @pytest.mark.parametrize("tip", ["vadeli", "cfd", "etf"])
    def test_spot_disi_kodlama_tip_tasiyor(self, tip):
        beklenen = f"{TEST_VENUE}:{tip}:BTCUSDT@{TARIH}"
        assert kanonik_kimlik(TEST_VENUE, tip, "btcusdt", TARIH) == beklenen
        assert _kur(tip).kanonik_id == beklenen

    def test_tum_tipler_ayni_venue_sembol_tarihte_birbirinden_farkli(self):
        kimlikler = {kanonik_kimlik(TEST_VENUE, t, "BTCUSDT", TARIH) for t in ENSTRUMAN_TIPLERI}
        assert len(kimlikler) == len(ENSTRUMAN_TIPLERI)

    @pytest.mark.parametrize(
        "kotu_kimlik",
        ["binance-spot:BTCUSDT@2017-08-18", "binance-spot:ETHUSDT@2017-08-17",
         "binance:BTCUSDT@2017-08-17", "binance-spot:vadeli:BTCUSDT@2017-08-17", "BTCUSDT"],
    )
    def test_alanlarla_tutarsiz_kimlik_red(self, kotu_kimlik):
        with pytest.raises(KimlikHatasi, match="tutarsız"):
            dataclasses.replace(_v1(), kanonik_id=kotu_kimlik)

    def test_tip_degisince_eski_kimlik_gecersiz(self):
        """Paket 1'in gizli çakışması kapandı: tipi değiştirip kimliği tutmak reddedilir."""
        with pytest.raises(KimlikHatasi):
            dataclasses.replace(_kur("spot"), instrument_type="etf")

    @pytest.mark.parametrize("tip", ["vadeli", "cfd", "etf"])
    def test_binance_spot_venue_yalniz_spot(self, tip):
        assert VENUE_TIPLERI == {"binance-spot": "spot"}
        with pytest.raises(KimlikHatasi, match="yalnız 'spot' taşır"):
            _kur(tip, venue="binance-spot")

    def test_kimlikleri_kur_tip_aliyor_spot_varsayilan_bayt_ayni(self):
        df = bar_uret(200)
        kir = kirilmalar(df, "1h", **ESIK)
        (spot,) = kimlikleri_kur(df, "1h", "btcusdt", kir)
        (acik,) = kimlikleri_kur(df, "1h", "btcusdt", kir, instrument_type="spot")
        assert spot == acik and spot.kanonik_id == "binance-spot:BTCUSDT@2023-11-14"
        # Spot dışı: kimlik segmenti üretilir ama sözleşme (global maliyet) U17'de reddedilir —
        # `kimlikleri_kur` maliyet/finansman uydurmaz.
        with pytest.raises(KimlikHatasi, match="global maliyet"):
            kimlikleri_kur(df, "1h", "btcusdt", kir, venue=TEST_VENUE, instrument_type="etf")
        with pytest.raises(KimlikHatasi, match="yalnız 'spot' taşır"):
            kimlikleri_kur(df, "1h", "btcusdt", kir, instrument_type="vadeli")


# ------------------------------------------------------------------ U17 sözleşme kuralları


class TestU17Sozlesme:
    @pytest.mark.parametrize("tip", sorted(FINANSMANLI_TIPLER))
    def test_finansmanli_tipte_finansman_zorunlu(self, tip):
        with pytest.raises(KimlikHatasi, match="finansman_modeli_id zorunlu"):
            _kur(tip, finansman_modeli_id=None)
        assert _kur(tip).finansman_modeli_id == "test-finansman"

    @pytest.mark.parametrize("tip", ["spot", "etf"])
    def test_finansmansiz_tipte_finansman_none_olabilir(self, tip):
        assert _kur(tip).finansman_modeli_id is None
        assert _kur(tip, finansman_modeli_id="opsiyonel").finansman_modeli_id == "opsiyonel"

    @pytest.mark.parametrize("tip", ["spot", "etf"])
    def test_contract_size_spot_ve_etfte_dolu_olamaz(self, tip):
        with pytest.raises(KimlikHatasi, match="contract_size tanımsız"):
            _kur(tip, contract_size=1.0)

    @pytest.mark.parametrize("tip", sorted(FINANSMANLI_TIPLER))
    def test_contract_size_finansmanli_tipte_none_bilinmiyor_ya_da_dolu(self, tip):
        assert _kur(tip).contract_size is None
        assert _kur(tip, contract_size=10.0).contract_size == 10.0

    def test_global_maliyet_yalniz_binance_spot_kripto(self):
        assert _v1().binance_spot_kripto and _v1().maliyet_modeli_id == "global"
        with pytest.raises(KimlikHatasi, match="global maliyet"):
            _kur("spot", maliyet_modeli_id="global")  # venue farklı → enstrüman-başı model şart
        with pytest.raises(KimlikHatasi, match="global maliyet"):
            _kur("etf", maliyet_modeli_id="global")
        assert not _kur("spot").binance_spot_kripto

    def test_islem_icin_dogrula_fail_closed(self):
        """None = bilinmiyor araştırmada geçer; paper/live ön koşulunda reddedilir."""
        with pytest.raises(KimlikHatasi, match=r"\['tick_size', 'lot_size'\]"):
            _v1().islem_icin_dogrula()
        dataclasses.replace(_v1(), tick_size=0.01, lot_size=0.001).islem_icin_dogrula()
        with pytest.raises(KimlikHatasi, match=r"\['contract_size'\]"):
            _kur("vadeli", tick_size=0.1, lot_size=1.0).islem_icin_dogrula()
        _kur("vadeli", tick_size=0.1, lot_size=1.0, contract_size=100.0).islem_icin_dogrula()
        _kur("etf", tick_size=0.01, lot_size=1.0).islem_icin_dogrula()  # kontrat tanımsız, istenmez


# ------------------------------------------------------------------ serileştirme


class TestSerilestirme:
    def test_a_v1_anahtarlari_ayni_sira_ayni_deger(self):
        s = _v1().sozluk()
        assert tuple(s)[: len(V1_ANAHTARLAR)] == V1_ANAHTARLAR
        v1 = {k: s[k] for k in V1_ANAHTARLAR}
        assert nesne_hash(v1) == V1_SOZLUK_ALTIN_HASH

    def test_b_v2_anahtarlari_beklenen_isim_ve_varsayilan(self):
        s = _v1().sozluk()
        assert tuple(s)[len(V1_ANAHTARLAR):] == tuple(ad for ad, _ in V2_ALANLAR)
        assert {ad: s[ad] for ad, _ in V2_ALANLAR} == dict(V2_ALANLAR)

    def test_b_sema_tam_olarak_v1_arti_v2(self):
        """Fazladan ya da eksik anahtar = beklenmeyen şema değişimi."""
        s = _v1().sozluk()
        assert tuple(s) == V1_ANAHTARLAR + tuple(ad for ad, _ in V2_ALANLAR)
        alanlar = tuple(f.name for f in dataclasses.fields(Enstruman))
        assert set(alanlar) <= set(s), "her alan katalogda"
        assert set(s) - set(alanlar) == {"gecerli_baslangic", "gecerli_bitis"}

    def test_c_katalog_kaydi_deterministik(self):
        def kayit(e: Enstruman) -> str:
            # `sq evren tablo`nun katalog yazımıyla aynı serileştirme (cli/main.py).
            return json.dumps(e.sozluk(), ensure_ascii=False, indent=2, sort_keys=True)

        assert kayit(_v1()) == kayit(_v1())
        assert kayit(_v2_acik()) == kayit(_v2_acik())
        assert kayit(_v1()) != kayit(_v2_acik())
        json.loads(kayit(_v2_acik()))  # JSON'a çevrilebilir (None → null, float → sayı)

    def test_c_v1_kayit_eski_kataloga_gore_yalniz_v2_ekliyor(self):
        """Şema değişimi beklenen değişim: eski kayıt ⊂ yeni kayıt, fark = tam v2 kümesi."""
        yeni = _v1().sozluk()
        eski = {k: yeni[k] for k in V1_ANAHTARLAR}
        assert {k: v for k, v in yeni.items() if k in eski} == eski
        assert set(yeni) - set(eski) == {ad for ad, _ in V2_ALANLAR}


# ------------------------------------------------------------------ hash sınırı


#: Kimlik/hash üreten modüller: `Enstruman`'ı ne import etmeli ne de v2 alan adlarını anmalı.
HASH_MODULLERI = (
    "backtest/sonuc.py",  # sonuc_hash, config_hash
    "research/deney.py",  # girdi_hash, cikti_hash, kimlik
    "common/hash.py",  # nesne_hash, veri hash'i
    "common/maliyet.py",  # MaliyetModeli.sozluk
    "research/tekrar.py",  # kayıt → model yeniden kurma
)
V2_ADLAR = tuple(ad for ad, _ in V2_ALANLAR) + ("Enstruman",)


class TestHashSiniri:
    @pytest.mark.parametrize("yol", HASH_MODULLERI)
    def test_d_statik_hash_modulleri_kimlige_bagli_degil(self, yol):
        kaynak = (SRC / yol).read_text(encoding="utf-8")
        for dugum in ast.walk(ast.parse(kaynak)):
            if isinstance(dugum, ast.ImportFrom):
                assert dugum.module != "scryne_quant.data.kimlik", yol
            if isinstance(dugum, ast.Import):
                assert all(a.name != "scryne_quant.data.kimlik" for a in dugum.names), yol
        for ad in V2_ADLAR:
            assert ad not in kaynak, f"{yol}: {ad!r} kaynakta geçiyor"

    def test_d_tablo_hash_v2_alanlarindan_bagimsiz(self):
        """`sonuc_hash`in evren bloğu `tablo_hash + kural`dan geliyor; ikisi de v2'yi görmüyor."""
        df = bar_uret(24 * 31 * 3, baslangic_ms=1_704_067_200_000)  # 2024-01-01, 3 ay
        kir = kirilmalar(df, "1h", **ESIK)
        v1 = kimlikleri_kur(df, "1h", "AAAUSDT", kir)
        # Kimliğe girmeyen v2 alanları değiştirilir (tip kimliğe girer — U13, o ayrı test).
        v2 = [
            dataclasses.replace(
                e, takvim_id="x", tick_size=1.0, lot_size=1.0, maliyet_modeli_id="m",
                finansman_modeli_id="f",
            )
            for e in v1
        ]
        kural = EvrenKurali(ust_n=5, asgari_quote_hacim=0.0)
        t1 = evren_tablosu(aylik_ozet(df, v1), kural, son_uye_ay="2024-03")
        t2 = evren_tablosu(aylik_ozet(df, v2), kural, son_uye_ay="2024-03")
        assert not t1.empty
        assert tablo_hash(t1) == tablo_hash(t2)
        assert kural.kimlik == nesne_hash(kural.sozluk())  # kural da v2 bilmiyor

        zamanlar = df["open_time"].to_numpy(dtype="int64")
        u1 = uyelik_matrisi(t1, zamanlar, {"AAAUSDT": v1})
        u2 = uyelik_matrisi(t2, zamanlar, {"AAAUSDT": v2})
        assert np.array_equal(u1["AAAUSDT"], u2["AAAUSDT"]) and u1["AAAUSDT"].any()

    def test_d_backtest_sonucu_alanlarinda_v2_yok(self):
        from scryne_quant.backtest.sonuc import Sonuc

        alanlar = {f.name for f in dataclasses.fields(Sonuc)}
        assert not alanlar & set(V2_ADLAR)


# ------------------------------------------------------------------ maliyet gövdesi sabiti


#: `_maliyet_govdesi(yukle("config/maliyet.json"))` kanonik JSON'unun SHA-256'sı ve
#: `MaliyetModeli.sozluk()` `nesne_hash`i — HEAD `dbe29ba`, 2026-09-20. Bu iki sayı deney
#: kayıtlarının `girdi_hash`/`config_hash`ine giriyor; değişmesi R1(b)'nin yeniden üretilebilir
#: kayıtlarını `semantik`e düşürür. Enstrüman-başı maliyet (R2 sonraki paket) bunları
#: **bilerek** ve bir K ile değiştirebilir, istemeden değil.
MALIYET_GOVDESI_SHA256 = "fe9f73bb70ced67217b937ed14ec6368004af6036edb17cbb3a4e755e1979ab5"
MALIYET_SOZLUK_HASH = "5022dec95569f39bcc620cfacb5b330c6d5f524ff5e3383b880de62a45ecf2a1"


def _kanonik(nesne) -> str:
    return json.dumps(nesne, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


class TestMaliyetGovdesiSabiti:
    def test_yurulukteki_model_bayt_duzeyinde_ayni(self):
        model = maliyet_mod.yukle(KOK / "config" / "maliyet.json")
        ham = _kanonik(_maliyet_govdesi(model))
        assert hashlib.sha256(ham.encode("utf-8")).hexdigest() == MALIYET_GOVDESI_SHA256
        assert nesne_hash(model.sozluk()) == MALIYET_SOZLUK_HASH

    def test_sentetik_model_govdesi_literal(self):
        """Dosyaya bağlı olmayan sabit: gövdenin anahtar kümesi ve biçimi."""
        model = MaliyetModeli(
            fee_taker_bps=10.0,
            slippage_bps=5.0,
            kalibrasyon=SlippageKalibrasyonu(
                yontem="test", persentil=75.0, deger_bps=5.0, sembol="BTCUSDT",
                timeframe="1m", aralik_baslangic_ms=0, aralik_bitis_ms=60_000, bar_sayisi=1,
                veri_sha256="0" * 64, dagilim_bps={"p75": 5.0}, tarih="2026-01-01",
                gerekce="test",
            ),
        )
        govde = _maliyet_govdesi(model)
        assert tuple(govde) == ("fee_taker_bps", "slippage_bps", "kalibrasyon")
        assert _kanonik(govde) == (
            '{"fee_taker_bps":10.0,"kalibrasyon":{"aralik_baslangic_ms":0,'
            '"aralik_bitis_ms":60000,"bar_sayisi":1,"dagilim_bps":{"p75":5.0},'
            '"deger_bps":5.0,"gerekce":"test","persentil":75.0,"sembol":"BTCUSDT",'
            '"tarih":"2026-01-01","timeframe":"1m","veri_sha256":"' + "0" * 64 + '",'
            '"yontem":"test"},"slippage_bps":5.0}'
        )
        assert tekrar_maliyet(govde) == model  # kayıt → model yeniden kurulabiliyor

    def test_gecici_model_govdesi(self):
        govde = _maliyet_govdesi(MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0))
        assert _kanonik(govde) == '{"fee_taker_bps":10.0,"kalibrasyon":null,"slippage_bps":5.0}'


# ------------------------------------------------------------ evren kuralı + regresyon (U13/U17)

#: `data/evren/_evren/27b7a16ed0ed.json` → `kural` (gerçek Faz 9 kuralı, 14 evren çekilişinin
#: `evren` alanı). Kimliği aşağıdaki literal; `venue`/`instrument_type` eklenmesi bunu değiştirmez.
GERCEK_KURAL = {
    "asgari_quote_hacim": 30000000.0,
    "ay_sonu_tolerans_saat": 24,
    "haric_desenler": ["(UP|DOWN|BULL|BEAR)USDT$"],
    "haric_tabanlar": [
        "AEUR", "AUD", "BIDR", "BRL", "BUSD", "BVND", "DAI", "EUR", "EURI", "FDUSD", "GBP",
        "IDRT", "NGN", "PAX", "RUB", "SUSD", "TRY", "TUSD", "UAH", "USD1", "USDC", "USDP",
        "USDS", "USDSB", "UST", "ZAR",
    ],
    "kote": "USDT",
    "ust_n": 50,
}
GERCEK_KURAL_KIMLIK = "27b7a16ed0ed972580af62eee34c145387d74260c7e4bc79d505cf59335d2ac0"
EVREN_META = KOK / "data" / "evren" / "_evren" / "27b7a16ed0ed.json"
KATALOG_YOLU = KOK / "data" / "evren" / "_evren" / "kimlik-katalogu.json"


class TestEvrenKuraliKimligi:
    def test_gercek_spot_kurali_ayni_kimlik(self):
        kural = EvrenKurali(**GERCEK_KURAL)
        assert kural.kimlik == GERCEK_KURAL_KIMLIK
        assert "venue" not in kural.sozluk() and "instrument_type" not in kural.sozluk()
        assert (kural.venue, kural.instrument_type) == ("binance-spot", "spot")

    def test_spot_disi_evren_ayni_sembollerle_farkli_kimlik(self):
        spot = EvrenKurali(**GERCEK_KURAL)
        vadeli = EvrenKurali(**GERCEK_KURAL, venue=TEST_VENUE, instrument_type="vadeli")
        assert vadeli.kimlik != spot.kimlik
        assert vadeli.sozluk()["venue"] == TEST_VENUE
        assert vadeli.sozluk()["instrument_type"] == "vadeli"
        # Sözlük → kural gidiş-dönüş (canlı yenileme `EvrenKurali(**meta["kural"])` yapıyor).
        assert EvrenKurali(**vadeli.sozluk()).kimlik == vadeli.kimlik
        assert EvrenKurali(**spot.sozluk()).kimlik == spot.kimlik

    def test_evren_kurali_venue_tip_tutarsizligi_red(self):
        with pytest.raises(EvrenHatasi, match="yalnız 'spot' taşır"):
            EvrenKurali(ust_n=5, asgari_quote_hacim=0.0, instrument_type="vadeli")
        with pytest.raises(EvrenHatasi, match="bilinmeyen enstrüman tipi"):
            EvrenKurali(ust_n=5, asgari_quote_hacim=0.0, venue=TEST_VENUE, instrument_type="perp")

    def test_farkli_venue_ayni_tip_farkli_kimlik(self):
        a = EvrenKurali(ust_n=5, asgari_quote_hacim=0.0)
        b = EvrenKurali(ust_n=5, asgari_quote_hacim=0.0, venue=TEST_VENUE, instrument_type="spot")
        assert a.kimlik != b.kimlik


@pytest.mark.skipif(not EVREN_META.exists(), reason="gerçek evren deposu yok (gitignore)")
class TestGercekDepoRegresyonu:
    """Yerel çapalar: PIT tablo hash'i ve katalog v1 alt kümesi. CI'da veri yok → atlanır."""

    def test_meta_kural_kimligi_ve_tablo_hash(self):
        import pandas as pd

        meta = json.loads(EVREN_META.read_text(encoding="utf-8"))
        assert EvrenKurali(**meta["kural"]).kimlik == meta["kural_kimlik"] == GERCEK_KURAL_KIMLIK
        tablo = pd.read_parquet(EVREN_META.with_suffix(".parquet"))
        assert tablo_hash(tablo) == meta["tablo_hash"]

    def test_katalog_v1_alt_kumesi_v2_modeliyle_bayt_ayni(self):
        kat = json.loads(KATALOG_YOLU.read_text(encoding="utf-8"))["enstrumanlar"]
        v1_alan = [k for k in V1_ANAHTARLAR if k not in ("gecerli_baslangic", "gecerli_bitis")]
        yeniden = [Enstruman(**{k: e[k] for k in v1_alan}).sozluk() for e in kat]
        assert [{k: s[k] for k in V1_ANAHTARLAR} for s in yeniden] == [
            {k: e[k] for k in V1_ANAHTARLAR} for e in kat
        ]
        assert all(s["instrument_type"] == "spot" and s["venue"] == "binance-spot" for s in yeniden)
        assert len(yeniden) == 761
