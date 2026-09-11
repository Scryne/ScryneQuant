"""Emir state machine, idempotency ve defter. (§33, §25, Faz 7)

Faz 7'nin bitti kriterlerinden biri: *"Aynı intent iki kez gönderildiğinde tek emir
oluşuyor (duplicate order üretilemiyor)."* Bu dosya o kriterin **ağsız** yarısı — testnet
gerektiren yarısı (≥100 emir) API anahtarıyla gelecek.

Ölçülen şey "kod duplicate üretmiyor" değil, **üretemiyor**: kimlik içerikten türüyor,
defterde birincil anahtar, ve state machine'de `UNKNOWN → SUBMITTED` diye bir geçiş yok.
Üçü de yapısal; hiçbiri bir dikkate bağlı değil.
"""

from __future__ import annotations

import pytest

from scryne_quant.oms.defter import DefterHatasi, EmirDefteri
from scryne_quant.oms.emir import (
    ACIK,
    GECISLER,
    KIMLIK_UZUNLUGU,
    NIHAI,
    Emir,
    EmirDurumu,
    EmirHatasi,
    GecersizGecis,
    emir_kur,
    gecis_yasal_mi,
    istemci_kimligi,
)
from scryne_quant.risk.niyet import onayla
from scryne_quant.strategy.sinyal import Sinyal, Yon

T0 = 1_700_000_000_000


def sinyal(hedef: float = 0.20, yon: Yon = Yon.BUY, zaman: int = T0) -> Sinyal:
    return Sinyal(
        symbol="BTCUSDT",
        side=yon,
        target_exposure=hedef,
        confidence=0.9,
        reason="TEST_GIRIS",
        timestamp=zaman,
    )


def niyet(**degisiklik):
    alanlar = {
        "sinyal": sinyal(),
        "onayli_maruziyet": 0.20,
        "limit_kimligi": "k" * 64,
        "karar_ms": T0,
    }
    alanlar |= degisiklik
    return onayla(**alanlar)


class TestIdempotencyKimligi:
    """Kimlik **içerikten** türüyor. Duplicate korumasının birinci katmanı."""

    def test_ayni_niyet_ayni_kimlik(self) -> None:
        assert istemci_kimligi(niyet()) == istemci_kimligi(niyet())

    def test_muhur_kimlige_girmiyor(self, monkeypatch) -> None:
        """Mühür süreç başına rastgele (K-032); kimliğe girseydi restart'ta koruma çökerdi.

        Test bunu **gerçekten** ölçüyor: mühür anahtarı döndürülüyor (yeni bir sürecin
        taklidi), aynı içerikli niyet yeniden mühürleniyor, ve kimlik değişmiyor.
        Yalnızca "aynı süreçte aynı kimlik" demek bu iddiayı ölçmezdi — orada mühür de
        zaten aynı olurdu.
        """
        from scryne_quant.risk import muhur as muhur_mod

        oncesi = niyet()
        kimlik_oncesi = istemci_kimligi(oncesi)

        # Yeni süreç taklidi: anahtar yenileniyor, yani aynı içerik farklı mühür veriyor.
        yeni_imzala, yeni_dogrula = muhur_mod._kur()
        monkeypatch.setattr(muhur_mod, "_imzala", yeni_imzala)
        monkeypatch.setattr(muhur_mod, "_dogrula", yeni_dogrula)

        sonrasi = niyet()
        assert sonrasi.muhur != oncesi.muhur, "anahtar dönmedi; test bir şey ölçmüyor"
        assert istemci_kimligi(sonrasi) == kimlik_oncesi

    @pytest.mark.parametrize(
        "degisiklik",
        [
            {"onayli_maruziyet": 0.10},
            {"limit_kimligi": "z" * 64},
            {"karar_ms": T0 + 3_600_000},
            {"sinyal": sinyal(hedef=0.30)},
            {"sinyal": sinyal(yon=Yon.SELL)},
            {"sinyal": sinyal(zaman=T0 + 3_600_000)},
        ],
    )
    def test_farkli_niyet_farkli_kimlik(self, degisiklik) -> None:
        assert istemci_kimligi(niyet()) != istemci_kimligi(niyet(**degisiklik))

    def test_kimlik_borsa_sinirina_siginiyor(self) -> None:
        # Binance `newClientOrderId`: 36 karakter, [A-Za-z0-9_-].
        k = istemci_kimligi(niyet())
        assert len(k) <= 36
        assert k.replace("-", "").replace("_", "").isalnum()

    def test_muhursuz_nesneden_kimlik_uretilmiyor(self) -> None:
        # Risk motorundan geçmemiş bir şeye emir kimliği vermek, kapıyı atlamak olurdu.
        from scryne_quant.risk.muhur import MuhurGecersiz

        with pytest.raises(MuhurGecersiz):
            istemci_kimligi({"sinyal": "sahte"})  # type: ignore[arg-type]


class TestStateMachine:
    def test_mutlu_yol(self) -> None:
        e = emir_kur(niyet(), 0.05, zaman_ms=1)
        for durum in (
            EmirDurumu.VALIDATED,
            EmirDurumu.SUBMITTED,
            EmirDurumu.ACKNOWLEDGED,
            EmirDurumu.PARTIALLY_FILLED,
            EmirDurumu.FILLED,
        ):
            e = e.gecir(durum, zaman_ms=2)
        assert e.nihai and not e.acik
        assert e.gecmis[0] == "CREATED" and e.gecmis[-1] == "FILLED"

    def test_unknown_yeniden_gonderilemiyor(self) -> None:
        """En kritik tek kural. `UNKNOWN → SUBMITTED` diye bir geçiş **yok**.

        `UNKNOWN` "başarısız" değil "bilinmiyor" demek: gönderim yapıldı ama yanıt
        kayboldu, emir borsada olabilir de olmayabilir de. Yeniden göndermek duplicate
        üretmenin en kısa yolu — ve burada state machine düzeyinde imkânsız.
        """
        assert not gecis_yasal_mi(EmirDurumu.UNKNOWN, EmirDurumu.SUBMITTED)
        assert not gecis_yasal_mi(EmirDurumu.UNKNOWN, EmirDurumu.CREATED)
        assert not gecis_yasal_mi(EmirDurumu.UNKNOWN, EmirDurumu.VALIDATED)

        e = emir_kur(niyet(), 0.05, zaman_ms=1)
        e = e.gecir(EmirDurumu.VALIDATED, zaman_ms=2).gecir(EmirDurumu.SUBMITTED, zaman_ms=3)
        e = e.gecir(EmirDurumu.UNKNOWN, zaman_ms=4)
        with pytest.raises(GecersizGecis):
            e.gecir(EmirDurumu.SUBMITTED, zaman_ms=5)

    def test_unknown_acik_kumesinde(self) -> None:
        # Bilinmezlik, yokluk değil: reconciliation bu emri sormak zorunda.
        assert EmirDurumu.UNKNOWN in ACIK
        assert EmirDurumu.UNKNOWN not in NIHAI

    def test_failed_ile_unknown_ayri(self) -> None:
        # `FAILED` = gönderilemedi, yani borsada olmadığı **biliniyor**.
        assert EmirDurumu.FAILED in NIHAI
        assert EmirDurumu.FAILED not in ACIK

    def test_nihai_durumdan_cikis_yok(self) -> None:
        for durum in NIHAI:
            assert GECISLER[durum] == frozenset(), durum

    def test_geri_donus_yok(self) -> None:
        e = emir_kur(niyet(), 0.05, zaman_ms=1)
        e = e.gecir(EmirDurumu.VALIDATED, zaman_ms=2).gecir(EmirDurumu.SUBMITTED, zaman_ms=3)
        e = e.gecir(EmirDurumu.ACKNOWLEDGED, zaman_ms=4).gecir(EmirDurumu.FILLED, zaman_ms=5)
        with pytest.raises(GecersizGecis, match="yasal olmayan geçiş"):
            e.gecir(EmirDurumu.SUBMITTED, zaman_ms=6)

    def test_her_durum_gecis_tablosunda(self) -> None:
        # Tabloda olmayan bir durum `GECISLER[durum]` ile KeyError verirdi — yani yeni bir
        # durum eklemek, geçişlerini yazmayı **zorunlu** kılıyor.
        assert set(GECISLER) == set(EmirDurumu)

    def test_gecmis_yolu_tutuyor(self) -> None:
        # "Bu emir hangi yoldan buraya geldi" bir uyuşmazlık araştırmasının ilk sorusu.
        e = emir_kur(niyet(), 0.05, zaman_ms=1)
        e = e.gecir(EmirDurumu.VALIDATED, zaman_ms=2).gecir(EmirDurumu.SUBMITTED, zaman_ms=3)
        e = e.gecir(EmirDurumu.UNKNOWN, zaman_ms=4).gecir(EmirDurumu.FILLED, zaman_ms=5)
        assert list(e.gecmis) == [
            "CREATED", "VALIDATED", "SUBMITTED", "UNKNOWN", "FILLED",
        ]

    def test_gecersiz_miktar(self) -> None:
        with pytest.raises(EmirHatasi):
            Emir(istemci_kimligi="x", sembol="BTCUSDT", yon="BUY", miktar=0.0)

    def test_dolan_miktar_siniri(self) -> None:
        with pytest.raises(EmirHatasi):
            Emir(
                istemci_kimligi="x", sembol="BTCUSDT", yon="BUY",
                miktar=1.0, dolan_miktar=1.5,
            )

    def test_kalan_hesabi(self) -> None:
        e = emir_kur(niyet(), 1.0, zaman_ms=1)
        e = e.gecir(EmirDurumu.VALIDATED, zaman_ms=2).gecir(EmirDurumu.SUBMITTED, zaman_ms=3)
        e = e.gecir(EmirDurumu.ACKNOWLEDGED, zaman_ms=4)
        e = e.gecir(EmirDurumu.PARTIALLY_FILLED, zaman_ms=5, dolan_miktar=0.4)
        assert e.kalan == pytest.approx(0.6)


class TestDefterDuplicateKorumasi:
    """Faz 7 bitti kriteri: *aynı intent iki kez gönderildiğinde tek emir oluşuyor.*"""

    def test_ayni_niyet_ikinci_kez_yeni_emir_acmiyor(self, tmp_path) -> None:
        d = EmirDefteri(tmp_path / "o.sqlite")
        birinci, yeni1 = d.yer_ac(emir_kur(niyet(), 0.05, zaman_ms=1))
        ikinci, yeni2 = d.yer_ac(emir_kur(niyet(), 0.05, zaman_ms=2))

        assert yeni1 is True
        assert yeni2 is False  # çağıran göndermemek zorunda
        assert ikinci.istemci_kimligi == birinci.istemci_kimligi
        assert len(d.tumu()) == 1

    def test_ikinci_cagri_mevcut_emrin_durumunu_veriyor(self, tmp_path) -> None:
        # `None` dönmek mevcut emrin durumunu gizlerdi; oysa çağıranın öğrenmesi gereken
        # tam olarak o.
        d = EmirDefteri(tmp_path / "o.sqlite")
        e, _ = d.yer_ac(emir_kur(niyet(), 0.05, zaman_ms=1))
        d.gecir(e.istemci_kimligi, EmirDurumu.VALIDATED, zaman_ms=2)
        d.gecir(e.istemci_kimligi, EmirDurumu.SUBMITTED, zaman_ms=3)

        mevcut, yeni = d.yer_ac(emir_kur(niyet(), 0.05, zaman_ms=4))
        assert yeni is False
        assert mevcut.durum is EmirDurumu.SUBMITTED

    def test_surec_olse_de_tek_emir(self, tmp_path) -> None:
        """Asıl senaryo: süreç emir gönderiminin ortasında ölüyor ve yeniden başlıyor.

        Faz 6'nın toparlanması (K-038) aynı niyeti **yeniden üretiyor** — ve yeniden
        üretilen niyet aynı kimliği veriyor, defter de onu tanıyor. Üç mekanizma (mühürsüz
        deterministik kimlik, yeniden üretim, defter) bu testte birleşiyor.
        """
        yol = tmp_path / "o.sqlite"
        d1 = EmirDefteri(yol)
        e, _ = d1.yer_ac(emir_kur(niyet(), 0.05, zaman_ms=1))
        d1.gecir(e.istemci_kimligi, EmirDurumu.VALIDATED, zaman_ms=2)
        d1.gecir(e.istemci_kimligi, EmirDurumu.SUBMITTED, zaman_ms=3)
        d1.kapat()  # süreç öldü — gönderim yapıldı mı bilinmiyor

        d2 = EmirDefteri(yol)
        _, yeni = d2.yer_ac(emir_kur(niyet(), 0.05, zaman_ms=10))
        assert yeni is False
        assert len(d2.tumu()) == 1

    def test_farkli_niyet_ayri_emir(self, tmp_path) -> None:
        d = EmirDefteri(tmp_path / "o.sqlite")
        d.yer_ac(emir_kur(niyet(), 0.05, zaman_ms=1))
        _, yeni = d.yer_ac(
            emir_kur(niyet(karar_ms=T0 + 3_600_000), 0.05, zaman_ms=2)
        )
        assert yeni is True
        assert len(d.tumu()) == 2


class TestDefterDayanikliligi:
    def test_emir_silinemiyor(self, tmp_path) -> None:
        # Bir emri silmek, reconciliation'ın karşılaştıracağı iki taraftan birini yok
        # etmek demek (§25).
        d = EmirDefteri(tmp_path / "o.sqlite")
        e, _ = d.yer_ac(emir_kur(niyet(), 0.05, zaman_ms=1))
        with pytest.raises(Exception, match="silinemez"):
            d._baglanti.execute("DELETE FROM emir WHERE istemci_kimligi = ?", (e.istemci_kimligi,))

    def test_kimlik_degistirilemiyor(self, tmp_path) -> None:
        d = EmirDefteri(tmp_path / "o.sqlite")
        e, _ = d.yer_ac(emir_kur(niyet(), 0.05, zaman_ms=1))
        with pytest.raises(Exception, match="değişmez"):
            d._baglanti.execute(
                "UPDATE emir SET istemci_kimligi = 'x' WHERE istemci_kimligi = ?",
                (e.istemci_kimligi,),
            )

    def test_yasadisi_gecis_diske_yazilmiyor(self, tmp_path) -> None:
        d = EmirDefteri(tmp_path / "o.sqlite")
        e, _ = d.yer_ac(emir_kur(niyet(), 0.05, zaman_ms=1))
        with pytest.raises(GecersizGecis):
            d.gecir(e.istemci_kimligi, EmirDurumu.FILLED, zaman_ms=2)
        assert d.al(e.istemci_kimligi).durum is EmirDurumu.CREATED

    def test_olmayan_emir_gecirilemiyor(self, tmp_path) -> None:
        d = EmirDefteri(tmp_path / "o.sqlite")
        with pytest.raises(DefterHatasi, match="defterde yok"):
            d.gecir("sqyok", EmirDurumu.VALIDATED, zaman_ms=1)

    def test_acik_emirler_unknown_iceriyor(self, tmp_path) -> None:
        d = EmirDefteri(tmp_path / "o.sqlite")
        e, _ = d.yer_ac(emir_kur(niyet(), 0.05, zaman_ms=1))
        d.gecir(e.istemci_kimligi, EmirDurumu.VALIDATED, zaman_ms=2)
        d.gecir(e.istemci_kimligi, EmirDurumu.SUBMITTED, zaman_ms=3)
        d.gecir(e.istemci_kimligi, EmirDurumu.UNKNOWN, zaman_ms=4)
        assert [x.istemci_kimligi for x in d.acik_emirler()] == [e.istemci_kimligi]

    def test_nihai_emir_acik_kumesinde_degil(self, tmp_path) -> None:
        d = EmirDefteri(tmp_path / "o.sqlite")
        e, _ = d.yer_ac(emir_kur(niyet(), 0.05, zaman_ms=1))
        for durum in (EmirDurumu.VALIDATED, EmirDurumu.SUBMITTED, EmirDurumu.REJECTED):
            d.gecir(e.istemci_kimligi, durum, zaman_ms=2)
        assert d.acik_emirler() == []
        assert d.sayim() == {"REJECTED": 1}

    def test_gecis_diskten_okununca_korunuyor(self, tmp_path) -> None:
        yol = tmp_path / "o.sqlite"
        d1 = EmirDefteri(yol)
        e, _ = d1.yer_ac(emir_kur(niyet(), 1.0, zaman_ms=1))
        d1.gecir(e.istemci_kimligi, EmirDurumu.VALIDATED, zaman_ms=2)
        d1.gecir(e.istemci_kimligi, EmirDurumu.SUBMITTED, zaman_ms=3)
        d1.gecir(
            e.istemci_kimligi, EmirDurumu.ACKNOWLEDGED, zaman_ms=4, borsa_kimligi="99"
        )
        d1.gecir(
            e.istemci_kimligi, EmirDurumu.PARTIALLY_FILLED, zaman_ms=5,
            dolan_miktar=0.4, ortalama_fiyat=70_000.0,
        )
        d1.kapat()

        okunan = EmirDefteri(yol).al(e.istemci_kimligi)
        assert okunan.durum is EmirDurumu.PARTIALLY_FILLED
        assert okunan.borsa_kimligi == "99"
        assert okunan.dolan_miktar == pytest.approx(0.4)
        assert okunan.kalan == pytest.approx(0.6)
        assert list(okunan.gecmis)[-1] == "PARTIALLY_FILLED"


class TestKimlikSinirlari:
    def test_kimlik_uzunlugu_sabiti_borsa_siniri_icinde(self) -> None:
        # Ön ek + hash, 36 karakterlik Binance sınırına sığmak zorunda.
        assert KIMLIK_UZUNLUGU + 2 <= 36
