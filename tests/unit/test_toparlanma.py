"""Restart: *"süreç öldürülüp yeniden başlatıldığında state doğru toparlanıyor."* (Faz 6)

Bu dosya Faz 6'nın en sert bitti kriterinin kanıtı. Ölçüm yöntemi bilerek dolaylı:
"toparlanan alanlar kayıtlıyla eşit mi" diye bakmak, kaydın kendisiyle kaydı doğrulamak
olurdu. Bunun yerine **iki koşu karşılaştırılıyor** —

- A: 60 barı kesintisiz işleyen koşu,
- B: 30 barda öldürülüp yeniden başlatılan, sonra kalan 30 barı işleyen koşu,

— ve ikisinin sonundaki portföy, risk durumu ve fill defteri **birebir** aynı olmak
zorunda. Bu, restart'ı bağımsız bir referansa karşı ölçüyor: kesinti hiçbir iz
bırakmamalı.

Ayrıca üç bozma senaryosu var. Bozulmuş bir kaydın **sessizce** kabul edilmesi, bu projede
"neredeyse doğru" sonucun tam tarifi; üçünde de beklenen davranış koşunun durması.
"""

from __future__ import annotations

import json

import pytest

from scryne_quant.live.depo import KosuDeposu, KosuOlayi
from scryne_quant.live.motor import ToparlanmaAyrismasi
from scryne_quant.live.toparlanma import toparlan
from tests.unit.test_paper_dongu import barlar, kosuyu_isle, motor_kur

TAKVIM = {16: ("BUY", 0.25), 24: ("FLAT", 0.0), 34: ("BUY", 0.25), 48: ("FLAT", 0.0)}


def depo_ac(tmp_path, ad: str = "kosu") -> KosuDeposu:
    """Dosya tabanlı depo. Bellek deposu bağlantıyla birlikte ölür — restart test edilemez."""
    return KosuDeposu(tmp_path / f"{ad}.sqlite")


def kesintisiz(tmp_path, n: int = 60):
    m = motor_kur(TAKVIM, depo=depo_ac(tmp_path, "a"))
    bl = barlar(n)
    toparlan(m, [])
    kosuyu_isle(m, bl)
    return m


def kesintili(tmp_path, n: int = 60, kesme: int = 30):
    """30 barda öl, yeniden başla, kalanı işle."""
    bl = barlar(n)
    yol = tmp_path / "b.sqlite"

    depo1 = KosuDeposu(yol)
    m1 = motor_kur(TAKVIM, depo=depo1)
    toparlan(m1, [])
    kosuyu_isle(m1, bl[:kesme])
    depo1.kapat()  # süreç öldü

    depo2 = KosuDeposu(yol)
    m2 = motor_kur(TAKVIM, depo=depo2)
    sonuc = toparlan(m2, bl[:kesme])
    kosuyu_isle(m2, bl[kesme:], baslangic_ms=kesme * 1000)
    return m2, sonuc


class TestTemizBaslangic:
    def test_kayit_yoksa_temiz_baslangic(self, tmp_path) -> None:
        m = motor_kur(depo=depo_ac(tmp_path))
        sonuc = toparlan(m, barlar(10))
        assert sonuc.temiz_baslangic
        assert sonuc.son_bar_ms is None
        assert sonuc.pencere_bar == 10
        assert [o["tur"] for o in m.depo.olaylar()] == [str(KosuOlayi.BASLADI)]


class TestKesintiIzBirakmiyor:
    """Asıl kriter: kesintili koşu, kesintisiz koşuyla **birebir** aynı sonucu vermeli."""

    def test_portfoy_ayni(self, tmp_path) -> None:
        a = kesintisiz(tmp_path / "x")
        b, _ = kesintili(tmp_path / "y")
        assert b.portfoy == a.portfoy

    def test_fill_defteri_ayni(self, tmp_path) -> None:
        a = kesintisiz(tmp_path / "x")
        b, _ = kesintili(tmp_path / "y")
        alanlar = ("zaman_ms", "yon", "miktar", "fiyat", "komisyon", "gerceklesen_pnl")
        cikar = lambda d: [  # noqa: E731
            {k: f[k] for k in alanlar} for f in sorted(d.filller(), key=lambda f: f["id"])
        ]
        assert cikar(b.depo) == cikar(a.depo)

    def test_risk_durumu_ayni(self, tmp_path) -> None:
        # Günlük zarar, zirve özkaynak ve ardışık kayıp sayacı süreçten uzun yaşamalı:
        # sıfırlanan bir günlük zarar limiti, limit değildir.
        a = kesintisiz(tmp_path / "x")
        b, _ = kesintili(tmp_path / "y")
        for ad in ("zirve_ozkaynak", "son_ozkaynak", "gun_basi_ozkaynak", "gun",
                   "ardisik_kayip", "cooldown_bitis_ms", "kapanan_islem", "safe_mode"):
            assert getattr(b.risk.durum, ad) == getattr(a.risk.durum, ad), ad

    def test_acik_pozisyonla_kesilse_de_ayni(self, tmp_path) -> None:
        # 20. barda pozisyon açık (16'da onay, 17'de fill, 24'te çıkış).
        a = kesintisiz(tmp_path / "x")
        b, _ = kesintili(tmp_path / "y", kesme=20)
        assert b.portfoy == a.portfoy
        assert b.risk.durum.kapanan_islem == a.risk.durum.kapanan_islem

    def test_bekleyen_kararla_kesilse_de_ayni(self, tmp_path) -> None:
        # 17. barda kesiliyor: 16'da onaylanmış bir niyet var ama henüz dolmadı.
        a = kesintisiz(tmp_path / "x")
        b, sonuc = kesintili(tmp_path / "y", kesme=17)
        assert sonuc.bekleyen_dogrulandi is True
        assert b.portfoy == a.portfoy


class TestToparlanmaKaniti:
    def test_bekleyen_karar_yeniden_uretilip_dogrulaniyor(self, tmp_path) -> None:
        _, sonuc = kesintili(tmp_path, kesme=17)
        assert sonuc.temiz_baslangic is False
        assert sonuc.portfoy_dogrulandi is True
        assert sonuc.bekleyen_dogrulandi is True

    def test_karar_yokken_karsilastirma_yapilmiyor(self, tmp_path) -> None:
        # 30. barda strateji sinyal üretmiyor: karşılaştırılacak bir karar yok.
        _, sonuc = kesintili(tmp_path, kesme=30)
        assert sonuc.bekleyen_dogrulandi is None

    def test_toparlandi_olayi_yaziliyor(self, tmp_path) -> None:
        m, _ = kesintili(tmp_path, kesme=20)
        turler = [o["tur"] for o in m.depo.olaylar()]
        assert str(KosuOlayi.TOPARLANDI) in turler

    def test_toparlanma_kesinti_sayilmiyor(self, tmp_path) -> None:
        # Düzgün toparlanan bir restart "açıklanamayan kesinti" değil; promotion'ın
        # `paper_kesinti` sayacı bunu saymamalı.
        m, _ = kesintili(tmp_path, kesme=20)
        assert m.depo.kesinti_sayisi() == 0


class TestAyrisma:
    """Bozulmuş kayıt sessizce kabul edilmemeli — koşu durmalı."""

    def _kes(self, tmp_path, kesme: int = 20):
        bl = barlar(60)
        yol = tmp_path / "c.sqlite"
        depo1 = KosuDeposu(yol)
        m1 = motor_kur(TAKVIM, depo=depo1)
        toparlan(m1, [])
        kosuyu_isle(m1, bl[:kesme])
        depo1.kapat()
        return yol, bl

    def test_portfoy_fill_defteriyle_ayrisirsa_duruyor(self, tmp_path) -> None:
        yol, bl = self._kes(tmp_path)
        _boz(yol, "UPDATE durum SET portfoy = ? WHERE id = 1",
             json.dumps({"nakit": 1.0, "miktar": 99.0, "ortalama_maliyet": 5.0, "giris_ms": None}))

        depo2 = KosuDeposu(yol)
        m2 = motor_kur(TAKVIM, depo=depo2)
        with pytest.raises(ToparlanmaAyrismasi, match="fill defteri ayrıştı"):
            toparlan(m2, bl[:20])
        assert m2.durdu
        assert depo2.kesinti_sayisi() == 1

    def test_bekleyen_karar_ayrisirsa_duruyor(self, tmp_path) -> None:
        yol, bl = self._kes(tmp_path, kesme=17)
        _boz(yol, "UPDATE durum SET bekleyen = ? WHERE id = 1",
             json.dumps({"sinyal": {}, "hedef_maruziyet": 0.99, "karar_ms": 1, "kisitlayan": []}))

        depo2 = KosuDeposu(yol)
        m2 = motor_kur(TAKVIM, depo=depo2)
        with pytest.raises(ToparlanmaAyrismasi, match="aynı girdi aynı çıktıyı vermedi"):
            toparlan(m2, bl[:17])
        assert m2.durdu

    def test_son_bar_pencerede_yoksa_duruyor(self, tmp_path) -> None:
        yol, bl = self._kes(tmp_path, kesme=20)
        depo2 = KosuDeposu(yol)
        m2 = motor_kur(TAKVIM, depo=depo2)
        with pytest.raises(ToparlanmaAyrismasi, match="toparlanma penceresinde yok"):
            toparlan(m2, bl[:10])  # kayıtlı son bar (19) pencerede yok
        assert m2.durdu

    def test_durmus_kosu_bar_islemiyor(self, tmp_path) -> None:
        yol, bl = self._kes(tmp_path, kesme=20)
        depo2 = KosuDeposu(yol)
        m2 = motor_kur(TAKVIM, depo=depo2)
        with pytest.raises(ToparlanmaAyrismasi):
            toparlan(m2, bl[:10])
        with pytest.raises(Exception, match="durduruldu"):
            m2.bar_isle(bl[20])


class TestKillSwitchSurecTenUzunYasiyor:
    """K-008/4: SAFE_MODE'dan çıkış **yalnızca elle onayla**. Restart elle onay değildir."""

    def test_safe_mode_restarti_atlatiyor(self, tmp_path) -> None:
        bl = barlar(40)
        yol = tmp_path / "k.sqlite"
        depo1 = KosuDeposu(yol)
        m1 = motor_kur(TAKVIM, depo=depo1)
        toparlan(m1, [])
        kosuyu_isle(m1, bl[:20])
        m1.risk.kill("TEST_KILL", bl[19].open_time)
        # Kill sonrası bir bar daha işlensin ki kontrol noktası SAFE_MODE'u kaydetsin.
        m1.bar_isle(bl[20], simdi=20_000)
        depo1.kapat()

        depo2 = KosuDeposu(yol)
        m2 = motor_kur(TAKVIM, depo=depo2)
        toparlan(m2, bl[:21])
        assert m2.risk.durum.safe_mode is True
        assert m2.risk.durum.safe_mode_sebep == "TEST_KILL"


def _boz(yol, sorgu: str, deger: str) -> None:
    """Kayda elle müdahale — dışarıdan bozulmuş bir dosyanın taklidi."""
    import sqlite3

    b = sqlite3.connect(str(yol))
    b.execute(sorgu, (deger,))
    b.commit()
    b.close()


class TestKosuKimligi:
    """Koşunun kimliği ile süreç başlatmasının kimliği ayrı şeyler. (K-009)"""

    def test_konfigurasyon_ayni_olunca_toparlaniyor(self, tmp_path) -> None:
        # `olusturuldu_ms` her başlatmada farklı; tam eşitlik arasaydık aynı koşu hiçbir
        # zaman yeniden başlatılamazdı.
        from dataclasses import replace

        from tests.unit.test_paper_dongu import kimlik as kimlik_kur

        yol = tmp_path / "k.sqlite"
        ilk = kimlik_kur("gozlem")
        with KosuDeposu(yol) as d:
            d.kosu_yaz(ilk)
        with KosuDeposu(yol) as d:
            d.kosu_yaz(replace(ilk, olusturuldu_ms=ilk.olusturuldu_ms + 99_999))
            assert d.kosu_oku().olusturuldu_ms == ilk.olusturuldu_ms

    def test_konfigurasyon_degisince_hata(self, tmp_path) -> None:
        from dataclasses import replace

        from tests.unit.test_paper_dongu import kimlik as kimlik_kur

        yol = tmp_path / "k.sqlite"
        ilk = kimlik_kur("gozlem")
        with KosuDeposu(yol) as d:
            d.kosu_yaz(ilk)
        with KosuDeposu(yol) as d, pytest.raises(Exception, match="başka bir koşuya ait"):
            d.kosu_yaz(replace(ilk, baslangic_sermaye=5_000.0))

    def test_kod_degisirse_kaydediliyor_ama_durdurmuyor(self, tmp_path) -> None:
        # Bir commit atmak 30 günlük ölçümü sıfırlamamalı; ama sessizce de geçilmemeli.
        from dataclasses import replace

        from tests.unit.test_paper_dongu import kimlik as kimlik_kur

        yol = tmp_path / "k.sqlite"
        ilk = kimlik_kur("gozlem")
        with KosuDeposu(yol) as d:
            d.kosu_yaz(ilk)
        with KosuDeposu(yol) as d:
            d.kosu_yaz(replace(ilk, commit_sha="b" * 40, dirty=True))
            turler = [o["tur"] for o in d.olaylar()]
            assert str(KosuOlayi.KOD_DEGISTI) in turler
            assert d.kesinti_sayisi() == 0  # kesinti değil
