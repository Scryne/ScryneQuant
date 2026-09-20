"""`JevKarari`, soru seti, ayarlar ve istemci: şema, fail-closed, sır, yetkisizlik. (K-074)

Üç şey ölçülüyor:

1. **Yetkisizlik tip düzeyinde:** miktar/fiyat/kaldıraç/stop alanı taşıyan bir karar kurulamaz.
2. **Fail-closed:** her hata sınıfı "karar yok" üretir; geçersiz kayıtta karar alanı bulunamaz;
   önceki karar hiçbir yoldan taşınmaz.
3. **Donmuşluk:** soru hash'i sabit; model uyuşmazlığı geçersiz; kesim bilinmiyorsa geriye dönük
   türetim `leak_riski`.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
from pydantic import ValidationError

from scryne_quant.jev import ayarlar as ayar_mod
from scryne_quant.jev import istemci as istemci_mod
from scryne_quant.jev import karar as karar_mod
from scryne_quant.jev import sorular
from scryne_quant.jev.karar import (
    YASAK_ALANLAR,
    JevKarari,
    KararDurumu,
    SemaHatasi,
    Yon,
    karar_kur,
    yanit_dogrula,
    yon_etiketle,
)

MODEL = "jev-1.13.0"
#: Spike 7 + Phase 6'da dondurulan hash. Değişirse soru seti değişmiş demektir: yeni çekiliş,
#: `SORU_SURUMU` artar, hipotez defterine satır ister (K-074/6, K-049/2).
SORU_SHA256_SABIT = "e6f91afbce523a1a97ac4a6078c1d970728106fba75bbbf13de2e8cf6263e43c"

SAAT = 3_600_000
KARAR_MS = 1_788_944_400_000  # 2026-09-09 09:00 UTC


def _durum(karar_ms: int = KARAR_MS) -> dict[str, Any]:
    return {
        "surum": 1,
        "sembol": "BTCUSDT",
        "karar_ms": karar_ms,
        "veri_kesimi_ms": karar_ms + SAAT,
        "1h": {"rsi_bandi": "notr"},
    }


def _yanit(
    yon: dict[str, float] | None = None, model: str = MODEL, rejim: str = "belirsiz"
) -> dict[str, Any]:
    yon = yon or {"long": 0.25, "short": 0.02, "flat": 0.73}
    return {
        "model": model,
        "usage": {"input_tokens": 2059, "output_tokens": 137},
        "answers": {
            "yon": {"choice": max(yon, key=yon.get), "confidence": 0.6, "probabilities": yon},
            "rejim": {
                "choice": rejim,
                "confidence": 0.48,
                "probabilities": {
                    "trend_yukari": 0.34,
                    "trend_asagi": 0.01,
                    "aralik": 0.07,
                    "yuksek_volatilite": 0.0,
                    "belirsiz": 0.58,
                },
            },
            "kurulum": {"score": 0.98, "confidence": 0.12},
            "cekimser": {"noul": 0.46},
        },
    }


def _kur(**degisiklik: Any) -> JevKarari:
    args: dict[str, Any] = {
        "kosu": "test",
        "durum": _durum(),
        "durum_hash": "a" * 64,
        "soru_sha256": SORU_SHA256_SABIT,
        "model_istenen": MODEL,
        "uretim_ms": KARAR_MS + SAAT + 1_000,  # kapanıştan 1 s sonra: ileriye dönük
        "bayat_ms": 2 * SAAT,
        "yon_marji": 0.2,
        "egitim_kesim_ms": None,
        "yanit": _yanit(),
        "durum_kodu": KararDurumu.GECERLI,
    }
    args.update(degisiklik)
    return karar_kur(**args)


# ------------------------------------------------------------------ soru seti


class TestSorular:
    def test_soru_hashi_donmus(self):
        assert sorular.soru_sha256(MODEL) == SORU_SHA256_SABIT

    def test_model_hashe_giriyor(self):
        assert sorular.soru_sha256("jev-9.9.9") != SORU_SHA256_SABIT

    def test_dort_soru_ve_tipleri(self):
        assert sorular.BEKLENEN == {
            "yon": "choice",
            "rejim": "choice",
            "kurulum": "score",
            "cekimser": "noul",
        }

    def test_yon_kumesi_enum_ile_ayni(self):
        assert tuple(y.value for y in Yon) == sorular.YONLER

    def test_kriterler_kumelerle_ayni(self):
        assert tuple(sorular.SORULAR["yon"]["criteria"]) == sorular.YONLER
        assert tuple(sorular.SORULAR["rejim"]["criteria"]) == sorular.REJIMLER
        seviyeler = tuple(next(iter(s)) for s in sorular.SORULAR["kurulum"]["criteria"])
        assert seviyeler == sorular.KURULUM_SEVIYELERI

    def test_sorular_sayisal_esik_icermiyor(self):
        """Spike 7(b)/2: Jev'e '%1'den yakın mı' gibi sayısal kıyas sorulmaz."""
        metin = json.dumps(sorular.SORULAR, ensure_ascii=False)
        assert "%" not in metin
        for parca in ("yakin mi", "buyuk mu", "kucuk mu", "fazla mi", "asagisinda", "yukarisinda"):
            assert parca not in metin

    def test_ufuk_config_ile_ayni(self):
        assert ayar_mod.yukle().birincil_ufuk_bar == sorular.UFUK_BAR


# ------------------------------------------------------------------ yön etiketleme


class TestYonEtiketle:
    @pytest.mark.parametrize(
        "p,marj,beklenen",
        [
            ({"long": 0.5, "short": 0.1, "flat": 0.4}, 0.2, Yon.FLAT),  # fark 0,1 < marj
            ({"long": 0.6, "short": 0.1, "flat": 0.3}, 0.2, Yon.LONG),
            ({"long": 0.1, "short": 0.65, "flat": 0.25}, 0.2, Yon.SHORT),
            ({"long": 0.45, "short": 0.1, "flat": 0.45}, 0.0, Yon.FLAT),  # eşitlikte flat
            ({"long": 0.2, "short": 0.1, "flat": 0.7}, 0.2, Yon.FLAT),
            ({"long": 0.6, "short": 0.4, "flat": 0.0}, 0.2, Yon.LONG),
        ],
    )
    def test_marj_kurali(self, p, marj, beklenen):
        assert yon_etiketle(p, marj) is beklenen

    def test_spike7_esit_olasilik_flat(self):
        """Spike 7: P(flat)=0,45, P(long)=0,44 argmax'ı flip ediyordu; marj bunu flat'e sabitler."""
        assert yon_etiketle({"long": 0.50, "short": 0.06, "flat": 0.44}, 0.2) is Yon.FLAT
        assert yon_etiketle({"long": 0.44, "short": 0.06, "flat": 0.50}, 0.2) is Yon.FLAT


# ------------------------------------------------------------------ karar şeması


class TestJevKarari:
    def test_gecerli_karar_kurulur(self):
        k = _kur()
        assert k.gecerli and k.yon is Yon.FLAT and k.rejim == "belirsiz"
        assert k.ileriye_donuk and not k.leak_riski
        assert k.model_cozulen == MODEL and k.yanit_hash and k.girdi_token == 2059
        assert k.karar_id != _kur(uretim_ms=KARAR_MS + SAAT + 2_000).karar_id

    @pytest.mark.parametrize("alan", YASAK_ALANLAR)
    def test_yetki_alanlari_reddedilir(self, alan):
        """Spec §25 / K-074/2: miktar, fiyat, kaldıraç, stop, borsa eylemi tipte yok."""
        govde = _kur().model_dump()
        govde[alan] = 1.0
        with pytest.raises(ValidationError):
            JevKarari(**govde)

    def test_degismez(self):
        k = _kur()
        with pytest.raises(ValidationError):
            k.yon = Yon.LONG  # type: ignore[misc]

    def test_sinyal_uretecek_bir_yol_yok(self):
        """K-067: `jev` paketinde `Sinyal` ya da `strategy.sinyal` adı geçmez."""
        from pathlib import Path

        kok = Path(karar_mod.__file__).parent
        for dosya in kok.rglob("*.py"):
            metin = dosya.read_text(encoding="utf-8")
            assert "strategy.sinyal" not in metin and "Sinyal(" not in metin, dosya

    def test_etiket_olasilikla_tutarsizsa_kurulamaz(self):
        govde = _kur().model_dump()
        govde["yon"] = "long"  # olasılık flat diyor
        with pytest.raises(ValidationError, match="tutarsız"):
            JevKarari(**govde)

    def test_yuvarlak_donus_json(self):
        k = _kur()
        assert JevKarari(**json.loads(json.dumps(k.sozluk()))) == k


class TestFailClosed:
    @pytest.mark.parametrize(
        "kod",
        [d for d in KararDurumu if d is not KararDurumu.GECERLI],
    )
    def test_hata_kodu_karar_yok(self, kod):
        k = _kur(durum_kodu=kod, hata="sebep", yanit=None)
        assert not k.gecerli and k.durum is kod
        assert k.yon is None and k.rejim is None and k.kurulum_skor is None and k.cekimser is None
        assert k.hata == "sebep"

    def test_gecersiz_kayda_karar_alani_konulamaz(self):
        govde = _kur().model_dump()
        govde["durum"] = "timeout"
        govde["hata"] = "x"
        with pytest.raises(ValidationError, match="fail-closed"):
            JevKarari(**govde)

    def test_gecersiz_kayit_sebepsiz_olamaz(self):
        govde = _kur(durum_kodu=KararDurumu.TIMEOUT, hata="x", yanit=None).model_dump()
        govde["hata"] = None
        with pytest.raises(ValidationError, match="sebebini"):
            JevKarari(**govde)

    def test_model_uyusmazligi_gecersiz(self):
        k = _kur(yanit=_yanit(model="jev-1.14.0"))
        assert k.durum is KararDurumu.MODEL_UYUMSUZ and k.yon is None

    def test_bayat_uretim_golgede_gecersiz(self):
        k = _kur(uretim_ms=KARAR_MS + SAAT + 2 * SAAT + 1)
        assert k.durum is KararDurumu.BAYAT_DURUM and not k.ileriye_donuk

    def test_bayat_sinir_dahil(self):
        assert _kur(uretim_ms=KARAR_MS + SAAT + 2 * SAAT).gecerli

    def test_replayde_geriye_donuk_izinli_ama_leak_riski(self):
        k = _kur(uretim_ms=KARAR_MS + 30 * 24 * SAAT, geriye_donuk=True)
        assert k.gecerli and not k.ileriye_donuk and k.leak_riski

    @pytest.mark.parametrize(
        "boz",
        [
            lambda y: y["answers"].pop("cekimser"),
            lambda y: y["answers"]["yon"]["probabilities"].pop("short"),
            lambda y: y["answers"]["yon"]["probabilities"].__setitem__("long", 1.5),
            lambda y: y["answers"]["rejim"].__setitem__("choice", "boga"),
            lambda y: y["answers"]["kurulum"].__setitem__("score", "yuksek"),
            lambda y: y["answers"]["cekimser"].__setitem__("noul", -0.1),
            lambda y: y.pop("answers"),
        ],
    )
    def test_sema_hatasi_karar_yok(self, boz):
        y = _yanit()
        boz(y)
        k = _kur(yanit=y)
        assert k.durum is KararDurumu.SEMA_HATASI and k.yon is None and k.hata

    def test_yanit_dogrula_temiz_yanit_gecer(self):
        c = yanit_dogrula(_yanit())
        assert set(c) == {"yon", "rejim", "kurulum", "cekimser"}

    def test_yanit_dogrula_fazla_soru_yok_sayilir(self):
        y = _yanit()
        y["answers"]["ekstra"] = {"noul": 0.5}
        yanit_dogrula(y)  # fazlalık şema hatası değil; eksiklik öyle

    def test_yanit_yoksa_gecerli_denemesi_api_hatasi(self):
        k = _kur(yanit=None)
        assert k.durum is KararDurumu.API_HATASI

    def test_onceki_karar_tasinmaz(self):
        """Nesnenin önceki kaydı görecek bir yolu yok: kurucu yalnızca kendi girdilerini alır."""
        import inspect

        params = inspect.signature(karar_kur).parameters
        assert not any("onceki" in p or "son_karar" in p or "previous" in p for p in params)
        with pytest.raises(SemaHatasi):
            yanit_dogrula({"answers": {}})


class TestLeakRiski:
    def test_kesim_bilinmiyorsa_geriye_donuk_her_zaman_riskli(self):
        k = _kur(uretim_ms=KARAR_MS + 10 * SAAT, geriye_donuk=True, egitim_kesim_ms=None)
        assert k.leak_riski

    def test_kesim_biliniyorsa_karsilastirilir(self):
        kesim = KARAR_MS - 24 * SAAT
        k = _kur(uretim_ms=KARAR_MS + 10 * SAAT, geriye_donuk=True, egitim_kesim_ms=kesim)
        assert not k.leak_riski
        k2 = _kur(uretim_ms=KARAR_MS + 10 * SAAT, geriye_donuk=True, egitim_kesim_ms=KARAR_MS + 1)
        assert k2.leak_riski

    def test_ileriye_donuk_kesimden_bagimsiz(self):
        assert not _kur(egitim_kesim_ms=KARAR_MS + 365 * 24 * SAAT).leak_riski

    def test_kesim_bilinmiyorsa_yayin_alt_sinirdir(self):
        """K-075: kesim ≤ yayın; karar barı yayından sonra açılıyorsa t sonrası veri
        eğitimde olamaz."""
        geriye = dict(uretim_ms=KARAR_MS + 10 * SAAT, geriye_donuk=True, egitim_kesim_ms=None)
        assert not _kur(**geriye, yayin_ms=KARAR_MS).leak_riski  # yayın = bar açılışı: sınır dahil
        assert not _kur(**geriye, yayin_ms=KARAR_MS - SAAT).leak_riski
        assert _kur(**geriye, yayin_ms=KARAR_MS + 1).leak_riski  # yayından önceki bar: temizlenmez
        assert _kur(**geriye, yayin_ms=None).leak_riski

    def test_kesim_biliniyorsa_yayin_yok_sayilir(self):
        geriye = dict(uretim_ms=KARAR_MS + 10 * SAAT, geriye_donuk=True)
        assert _kur(**geriye, egitim_kesim_ms=KARAR_MS + 1, yayin_ms=KARAR_MS - SAAT).leak_riski


# ------------------------------------------------------------------ ayarlar


class TestAyarlar:
    def _ham(self) -> dict[str, Any]:
        return json.loads(ayar_mod.VARSAYILAN_YOL.read_text(encoding="utf-8"))

    def test_repo_ayarlari_yuklenir(self):
        a = ayar_mod.yukle()
        assert a.model == MODEL and a.sembol == "BTCUSDT" and a.yon_marji == 0.2
        assert a.egitim_kesim_ms is None and a.egitim_kesim_kaynagi == "dogrulanmadi"
        assert a.yayin_ms is not None

    def test_takma_ad_reddedilir(self):
        ham = self._ham()
        ham["model"]["istenen"] = "jev-latest"
        with pytest.raises(ayar_mod.AyarHatasi, match="çözülmüş"):
            ayar_mod.ayristir(ham)

    def test_kesim_kaynaksiz_yazilamaz(self):
        ham = self._ham()
        ham["model"]["egitim_kesim_utc"] = "2026-01-01T00:00:00Z"
        with pytest.raises(ayar_mod.AyarHatasi, match="kaynağı"):
            ayar_mod.ayristir(ham)

    def test_kesim_yayindan_sonra_olamaz(self):
        ham = self._ham()
        ham["model"]["egitim_kesim_utc"] = "2026-12-01T00:00:00Z"
        ham["model"]["egitim_kesim_kaynagi"] = "TypeSafe beyanı"
        with pytest.raises(ayar_mod.AyarHatasi, match="yayından sonra"):
            ayar_mod.ayristir(ham)

    def test_marj_araligi(self):
        ham = self._ham()
        ham["karar"]["yon_marji"] = 1.5
        with pytest.raises(ayar_mod.AyarHatasi):
            ayar_mod.ayristir(ham)

    def test_eksik_alan(self):
        ham = self._ham()
        del ham["karar"]
        with pytest.raises(ayar_mod.AyarHatasi):
            ayar_mod.ayristir(ham)


# ------------------------------------------------------------------ istemci


class _Cevap:
    def __init__(self, **k: Any) -> None:
        self.__dict__.update(k)


class _Yanit:
    def __init__(self, model: str = MODEL) -> None:
        y = _yanit(model=model)
        self.model = model
        self.usage = _Cevap(input_tokens=10, output_tokens=2)
        self.answers = {
            "yon": _Cevap(**y["answers"]["yon"]),
            "rejim": _Cevap(**y["answers"]["rejim"]),
            "kurulum": _Cevap(**y["answers"]["kurulum"]),
            "cekimser": _Cevap(**y["answers"]["cekimser"]),
        }


class _SahteIstemci:
    def __init__(self, sonuc: Any) -> None:
        self.sonuc = sonuc
        self.cagri: list[tuple[Any, Any, str | None]] = []

    def system_one(self, state, questions, *, model=None):
        self.cagri.append((state, questions, model))
        if isinstance(self.sonuc, BaseException):
            raise self.sonuc
        return self.sonuc


class TestIstemci:
    def _ayar(self):
        return ayar_mod.yukle()

    def test_gecerli_yanit_duz_sozluk(self):
        s = _SahteIstemci(_Yanit())
        r = istemci_mod.sor(s, _durum(), self._ayar())
        assert r.durum is KararDurumu.GECERLI and r.hata is None
        assert r.yanit["model"] == MODEL and set(r.yanit["answers"]) == set(sorular.BEKLENEN)
        assert s.cagri[0][2] == MODEL and s.cagri[0][1] is sorular.SORULAR

    def test_sdk_hatalari_siniflandirilir(self):
        import typesafe_sdk as t

        h = t.TypeSafeAPIError.__mro__  # noqa: F841 - SDK yüklü mü
        vakalar = [
            (t.TypeSafeAPITimeoutError(5.0), KararDurumu.TIMEOUT),
            (t.TypeSafeAuthenticationError(401, {}, {}), KararDurumu.KIMLIK_HATASI),
            (t.TypeSafePermissionDeniedError(403, {}, {}), KararDurumu.KIMLIK_HATASI),
            (t.TypeSafeRateLimitError(429, {}, {}), KararDurumu.ORAN_SINIRI),
            (t.TypeSafeAPIError(500, {}, {}), KararDurumu.API_HATASI),
            (ConnectionError("dns"), KararDurumu.API_HATASI),
            (TimeoutError("socket"), KararDurumu.TIMEOUT),
        ]
        for hata, beklenen in vakalar:
            r = istemci_mod.sor(_SahteIstemci(hata), _durum(), self._ayar())
            assert r.yanit is None and r.durum is beklenen, (hata, r.durum)
            assert r.hata

    def test_hata_metninden_sir_temizlenir(self, monkeypatch):
        sir = "sk-typesafe-gizli-anahtar-123456"
        monkeypatch.setenv("TYPESAFE_API_KEY", sir)
        r = istemci_mod.sor(
            _SahteIstemci(RuntimeError(f"auth failed for {sir}")), _durum(), self._ayar()
        )
        assert sir not in (r.hata or "") and "[SIR]" in r.hata

    def test_durumda_sir_varsa_gonderilmez(self, monkeypatch):
        sir = "sk-typesafe-gizli-anahtar-123456"
        monkeypatch.setenv("TYPESAFE_API_KEY", sir)
        s = _SahteIstemci(_Yanit())
        d = _durum()
        d["not"] = f"anahtar {sir}"
        r = istemci_mod.sor(s, d, self._ayar())
        assert r.durum is KararDurumu.EKSIK_VERI and not s.cagri

    def test_kisa_sir_taranmaz(self, monkeypatch):
        monkeypatch.setenv("TYPESAFE_API_KEY", "ab")
        assert not istemci_mod.sir_var_mi({"x": "ab"})

    def test_kanonik_durum_sir_icermiyor(self, monkeypatch):
        """Gerçek durum kurucusunun çıktısında ortam sırları geçmez (spec §34, §58)."""
        from scryne_quant.features.barlar import bar_dizileri
        from scryne_quant.jev.durum import kanonik_durum
        from tests.conftest import bar_uret

        monkeypatch.setenv("TYPESAFE_API_KEY", "sk-typesafe-gizli-anahtar-123456")
        d = kanonik_durum(bar_dizileri(bar_uret(n=300)), 250, sembol="BTCUSDT")
        assert not istemci_mod.sir_var_mi(d)

    def test_yanit_sema_disi_ise_karar_yok(self):
        bozuk = _Yanit()
        del bozuk.answers["yon"]
        r = istemci_mod.sor(_SahteIstemci(bozuk), _durum(), self._ayar())
        assert r.durum is KararDurumu.GECERLI  # istemci "cevap geldi" der…
        k = _kur(yanit=r.yanit)
        assert k.durum is KararDurumu.SEMA_HATASI  # …şema karar katmanında düşer

    def test_gercek_istemci_fabrikasi_ayarlari_uygular(self, monkeypatch):
        """Gerçek SDK kurucusu; anahtar **sahte** (kurucu ağa çıkmaz, anahtarı doğrulamaz —
        iddia SDK uyumluluğu ve ayarların uygulanması, kimlik değil). Gerçek anahtar CI'da
        bilerek yok (K-074/8); `ipv4=False` süreç geneli `getaddrinfo` patch'ini oturuma
        sızdırmamak için."""
        from tenacity.stop import stop_after_attempt

        monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test-sahte-anahtar-000000")
        ayar = self._ayar()
        c = istemci_mod.typesafe_istemci(ayar, ipv4=False)
        try:
            assert hasattr(c, "system_one")
            assert c._config.timeout == ayar.timeout_s
            deneme = [s for s in c._retry.stop.stops if isinstance(s, stop_after_attempt)]
            assert deneme and deneme[0].max_attempt_number == ayar.azami_deneme
        finally:
            c.close() if hasattr(c, "close") else None


def test_kopya_bagimsizligi():
    """`karar_kur` verilen yanıtı değiştirmez (kayıt, ham yanıtı ayrıca saklayacak)."""
    y = _yanit()
    kopya = copy.deepcopy(y)
    _kur(yanit=y)
    assert y == kopya
