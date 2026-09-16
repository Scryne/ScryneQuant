"""Arşiv indirici: zaman birimi, checksum, dosya planı, manifesto, idempotency. (Faz 9)

Testler **sahte bir arşivle** çalışır; sahte arşiv gerçeğinin 2026-09-15'te ölçülen
davranışını taklit eder: başlıksız 12 alanlı CSV, 2025-01'den itibaren µs zaman damgası,
zip'in SHA-256'sını taşıyan `.CHECKSUM` dosyası, S3 önek/anahtar listesi.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pandas as pd
import pytest

from scryne_quant.data.arsiv_indirici import ArsivIndirici, ArsivIndirmeHatasi, coklu_indir
from scryne_quant.data.depo import ParquetDepo
from scryne_quant.data.semalar import HAM_BAR_SUTUNLARI, KaliteDurumu
from scryne_quant.exchange import binance_arsiv as ba
from scryne_quant.exchange.binance_arsiv import ArsivHatasi, ArsivKaynagi, HttpArsiv

SAAT = 3_600_000
ARALIK_2024_12 = 1_733_011_200_000  # 2024-12-01 00:00 UTC
ARALIK_2025_01 = 1_735_689_600_000  # 2025-01-01 00:00 UTC
ARALIK_2025_02 = 1_738_368_000_000  # 2025-02-01 00:00 UTC


# ------------------------------------------------------------------ yardımcılar


def satirlar(baslangic_ms: int, n: int, *, mikro: bool, fiyat: float = 100.0) -> list[str]:
    carpan = 1000 if mikro else 1
    out = []
    for i in range(n):
        t = baslangic_ms + i * SAAT
        p = fiyat + i
        out.append(
            f"{t * carpan},{p:.8f},{p + 1:.8f},{p - 1:.8f},{p + 0.5:.8f},10.00000000,"
            f"{(t + SAAT) * carpan - 1},51410648.79613400,{100 + i},5.0,500.0,0"
        )
    return out


def zip_yap(ad: str, csv_satirlari: list[str]) -> bytes:
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(ad, "\n".join(csv_satirlari) + "\n")
    return tampon.getvalue()


class SahteArsiv(ArsivKaynagi):
    def __init__(self) -> None:
        self.dosyalar: dict[str, bytes] = {}
        self.getirilen: list[str] = []

    def ekle(
        self, anahtar: str, csv_satirlari: list[str], *, checksum: str | None = "dogru"
    ) -> None:
        ad = anahtar.rsplit("/", 1)[-1].replace(".zip", ".csv")
        bayt = zip_yap(ad, csv_satirlari)
        self.dosyalar[anahtar] = bayt
        self.dosyalar.pop(f"{anahtar}.CHECKSUM", None)
        if checksum == "dogru":
            ozet = hashlib.sha256(bayt).hexdigest()
            self.dosyalar[f"{anahtar}.CHECKSUM"] = f"{ozet}  {ad}\n".encode()
        elif checksum is not None:
            self.dosyalar[f"{anahtar}.CHECKSUM"] = f"{checksum}  {ad}\n".encode()

    def aylik(self, sembol: str, ay: str, baslangic_ms: int, n: int, **kw) -> str:
        anahtar = f"data/spot/monthly/klines/{sembol}/1h/{sembol}-1h-{ay}.zip"
        fiyat = kw.pop("fiyat", 100.0)
        self.ekle(anahtar, satirlar(baslangic_ms, n, mikro=ay >= "2025-01", fiyat=fiyat), **kw)
        return anahtar

    def gunluk(self, sembol: str, gun: str, baslangic_ms: int, **kw) -> str:
        anahtar = f"data/spot/daily/klines/{sembol}/1h/{sembol}-1h-{gun}.zip"
        fiyat = kw.pop("fiyat", 100.0)
        self.ekle(anahtar, satirlar(baslangic_ms, 24, mikro=True, fiyat=fiyat), **kw)
        return anahtar

    def listele(self, onek):
        onekler, anahtarlar = set(), []
        for anahtar in self.dosyalar:
            if not anahtar.startswith(onek):
                continue
            kalan = anahtar[len(onek) :]
            if "/" in kalan:
                onekler.add(onek + kalan.split("/", 1)[0] + "/")
            else:
                anahtarlar.append(anahtar)
        return sorted(onekler), sorted(anahtarlar)

    def getir(self, anahtar):
        self.getirilen.append(anahtar)
        return self.dosyalar.get(anahtar)


def zip_getirmeleri(arsiv: SahteArsiv) -> list[str]:
    return [a for a in arsiv.getirilen if a.endswith(".zip")]


@pytest.fixture
def kurulum(depo_kok):
    arsiv = SahteArsiv()
    arsiv.aylik("BTCUSDT", "2024-12", ARALIK_2024_12, 744)
    arsiv.aylik("BTCUSDT", "2025-01", ARALIK_2025_01, 744, fiyat=844.0)
    arsiv.gunluk("BTCUSDT", "2025-02-01", ARALIK_2025_02, fiyat=1588.0)
    arsiv.gunluk("BTCUSDT", "2025-02-02", ARALIK_2025_02 + 24 * SAAT, fiyat=1612.0)
    depo = ParquetDepo(depo_kok)
    return ArsivIndirici(arsiv, depo, paralel=4), arsiv, depo


# ------------------------------------------------------------ CSV / zaman birimi


class TestZipBarlari:
    def test_ms_ve_us_ayni_bari_verir(self):
        ms = ba.zip_barlari("a", zip_yap("a.csv", satirlar(ARALIK_2025_01, 3, mikro=False)))
        us = ba.zip_barlari("b", zip_yap("b.csv", satirlar(ARALIK_2025_01, 3, mikro=True)))
        pd.testing.assert_frame_equal(ms, us)
        assert int(us["open_time"].iloc[0]) == ARALIK_2025_01

    def test_sutunlar_ham_bar_sozlesmesi(self):
        df = ba.zip_barlari("a", zip_yap("a.csv", satirlar(ARALIK_2024_12, 2, mikro=False)))
        assert tuple(df.columns) == HAM_BAR_SUTUNLARI
        assert str(df["open_time"].dtype) == "int64"

    def test_float_rest_ile_bit_duzeyinde_ayni(self):
        """Varsayılan pandas ayrıştırıcısı bu değeri 2,4e-7 kaydırıyordu (ölçüldü)."""
        df = ba.zip_barlari("a", zip_yap("a.csv", satirlar(ARALIK_2024_12, 5, mikro=False)))
        assert (df["quote_volume"] == float("51410648.79613400")).all()

    def test_karisik_birim_reddedilir(self):
        karisik = satirlar(ARALIK_2024_12, 1, mikro=False) + satirlar(ARALIK_2025_01, 1, mikro=True)
        with pytest.raises(ArsivHatasi, match="karışık"):
            ba.zip_barlari("a", zip_yap("a.csv", karisik))

    def test_bine_bolunmeyen_us_reddedilir(self):
        satir = satirlar(ARALIK_2025_01, 1, mikro=True)[0].split(",")
        satir[0] = str(int(satir[0]) + 7)
        with pytest.raises(ArsivHatasi, match="bölünmüyor"):
            ba.zip_barlari("a", zip_yap("a.csv", [",".join(satir)]))

    def test_baslik_satiri_sessizce_okunmaz(self):
        baslik = ["open_time,open,high,low,close,volume,close_time,quote_volume,count,tb,tq,ig"]
        with pytest.raises(ArsivHatasi, match="başlık"):
            ba.zip_barlari("a", zip_yap("a.csv", baslik + satirlar(ARALIK_2024_12, 1, mikro=False)))

    def test_bozuk_zip(self):
        with pytest.raises(ArsivHatasi, match="bozuk zip"):
            ba.zip_barlari("a", b"zip degil")

    def test_birden_fazla_dosyali_zip(self):
        tampon = io.BytesIO()
        with zipfile.ZipFile(tampon, "w") as z:
            z.writestr("a.csv", "1,2")
            z.writestr("b.csv", "1,2")
        with pytest.raises(ArsivHatasi, match="tek dosya"):
            ba.zip_barlari("a", tampon.getvalue())


class TestChecksum:
    def test_dogru_checksum_hashi_dondurur(self):
        bayt = b"veri"
        ozet = hashlib.sha256(bayt).hexdigest()
        assert ba.checksum_dogrula("a", bayt, f"{ozet}  a.zip\n".encode()) == ozet

    def test_checksum_dosyasi_yoksa_hata(self):
        with pytest.raises(ArsivHatasi, match="CHECKSUM dosyası yok"):
            ba.checksum_dogrula("a", b"veri", None)

    def test_uyusmayan_checksum_hata(self):
        with pytest.raises(ArsivHatasi, match="uyuşmuyor"):
            ba.checksum_dogrula("a", b"veri", ("0" * 64 + "  a.zip").encode())

    def test_okunamayan_checksum_hata(self):
        with pytest.raises(ArsivHatasi, match="okunamadı"):
            ba.checksum_dogrula("a", b"veri", b"<html>404</html>")


# --------------------------------------------------------------------- indirme


class TestIndirme:
    def test_ay_siniri_birim_degisimine_ragmen_kesintisiz(self, kurulum):
        """2024-12 ms, 2025-01 µs: seri tek parça ve kusursuz olmalı."""
        indirici, _, depo = kurulum
        sonuc = indirici.indir("BTCUSDT")

        assert sonuc.depo is not None and sonuc.kalite is not None
        assert sonuc.depo.bar_sayisi == 744 + 744 + 48
        assert sonuc.kalite.kusursuz
        df = depo.oku("BTCUSDT", "1h")
        assert int(df["open_time"].diff().dropna().max()) == SAAT

    def test_plan_gunlukleri_son_aylik_aydan_sonrasi_icin_alir(self, kurulum):
        indirici, arsiv, _ = kurulum
        arsiv.gunluk("BTCUSDT", "2025-01-31", ARALIK_2025_02 - 24 * SAAT)  # aylıkta zaten var
        aylik, gunluk = indirici.plan("BTCUSDT", "1h")
        assert list(aylik) == ["2024-12", "2025-01"]
        assert list(gunluk) == ["2025-02-01", "2025-02-02"]

    def test_manifesto_her_dosyanin_sha256sini_tasir(self, kurulum):
        indirici, arsiv, _ = kurulum
        indirici.indir("BTCUSDT")
        govde = json.loads(indirici.manifesto_yolu("BTCUSDT", "1h").read_text(encoding="utf-8"))
        assert len(govde["dosyalar"]) == 4
        for anahtar, ozet in govde["dosyalar"].items():
            assert ozet == hashlib.sha256(arsiv.dosyalar[anahtar]).hexdigest()

    def test_ikinci_kosu_hic_dosya_indirmez_ve_dosya_degismez(self, kurulum):
        indirici, arsiv, depo = kurulum
        ilk = indirici.indir("BTCUSDT")
        arsiv.getirilen.clear()

        ikinci = indirici.indir("BTCUSDT")

        assert zip_getirmeleri(arsiv) == []
        assert not ikinci.degisti
        assert ikinci.depo is not None and ikinci.depo.sha256 == ilk.depo.sha256
        assert depo.sha256("BTCUSDT", "1h") == ilk.depo.sha256

    def test_yeni_gun_yalnizca_o_dosyayi_indirir(self, kurulum):
        indirici, arsiv, _ = kurulum
        indirici.indir("BTCUSDT")
        arsiv.getirilen.clear()
        yeni = arsiv.gunluk("BTCUSDT", "2025-02-03", ARALIK_2025_02 + 48 * SAAT, fiyat=1636.0)

        sonuc = indirici.indir("BTCUSDT")

        assert zip_getirmeleri(arsiv) == [yeni]
        assert sonuc.degisti
        assert sonuc.depo is not None and sonuc.depo.bar_sayisi == 744 + 744 + 72

    def test_aylik_dosya_gelince_gunluk_kayitlar_duser_veri_degismez(self, kurulum):
        indirici, arsiv, _ = kurulum
        ilk = indirici.indir("BTCUSDT")
        ay = arsiv.aylik("BTCUSDT", "2025-02", ARALIK_2025_02, 48, fiyat=1588.0)
        # Aylık dosyada iki gün aynı değerlerle: günlük dosyalarla birebir.
        arsiv.ekle(
            ay,
            satirlar(ARALIK_2025_02, 24, mikro=True, fiyat=1588.0)
            + satirlar(ARALIK_2025_02 + 24 * SAAT, 24, mikro=True, fiyat=1612.0),
        )

        sonuc = indirici.indir("BTCUSDT")

        assert sonuc.depo is not None and sonuc.depo.sha256 == ilk.depo.sha256
        assert set(sonuc.manifesto) == {
            k for k in arsiv.dosyalar if "/monthly/" in k and k.endswith(".zip")
        }

    def test_checksum_hatasi_hicbir_sey_yazmaz(self, kurulum):
        indirici, arsiv, depo = kurulum
        arsiv.aylik("BTCUSDT", "2025-01", ARALIK_2025_01, 744, checksum="0" * 64)

        with pytest.raises(ArsivIndirmeHatasi, match="uyuşmuyor"):
            indirici.indir("BTCUSDT")

        assert not depo.var_mi("BTCUSDT", "1h")
        assert not indirici.manifesto_yolu("BTCUSDT", "1h").exists()

    def test_checksumsiz_dosya_kabul_edilmez(self, kurulum):
        indirici, arsiv, depo = kurulum
        arsiv.aylik("BTCUSDT", "2025-01", ARALIK_2025_01, 744, checksum=None)
        with pytest.raises(ArsivIndirmeHatasi, match="CHECKSUM"):
            indirici.indir("BTCUSDT")
        assert not depo.var_mi("BTCUSDT", "1h")

    def test_depo_silinmisse_manifesto_yok_sayilir(self, kurulum):
        """Depoda olmayan veriyi "indirildi" gösteren manifesto yeniden indirmeyi engellememeli."""
        indirici, arsiv, depo = kurulum
        indirici.indir("BTCUSDT")
        depo.yol("BTCUSDT", "1h").unlink()
        arsiv.getirilen.clear()

        sonuc = indirici.indir("BTCUSDT")

        assert len(zip_getirmeleri(arsiv)) == 4
        assert sonuc.depo is not None and sonuc.depo.bar_sayisi == 744 + 744 + 48

    def test_tam_dogrulama_yeniden_yayimlanan_dosyayi_yakalar(self, kurulum):
        indirici, arsiv, depo = kurulum
        indirici.indir("BTCUSDT")
        anahtar = arsiv.aylik("BTCUSDT", "2024-12", ARALIK_2024_12, 744, fiyat=200.0)
        arsiv.getirilen.clear()

        varsayilan = indirici.indir("BTCUSDT")
        assert zip_getirmeleri(arsiv) == [] and not varsayilan.degisti

        tam = indirici.indir("BTCUSDT", tam_dogrulama=True)
        assert tam.degisen_dosyalar == (anahtar,)
        assert tam.degisti
        assert float(depo.oku("BTCUSDT", "1h")["open"].iloc[0]) == 200.0

    def test_arsivdeki_bosluk_gap_olarak_bayraklanir(self, depo_kok):
        """LUNAUSDT 2022-05 gibi: ay dosyası 744 değil 307 satır."""
        arsiv = SahteArsiv()
        # Yüksek taban fiyat: boşluk boyunca biriken +200'lük artış `asiri_hareket` sayılmasın;
        # ölçülen şey `gap`, `suspect` değil (suspect gap'i bayrak önceliğinde ezer).
        satir = satirlar(ARALIK_2024_12, 744, mikro=False, fiyat=100_000.0)
        anahtar = "data/spot/monthly/klines/LUNAUSDT/1h/LUNAUSDT-1h-2024-12.zip"
        arsiv.ekle(anahtar, satir[:300] + satir[500:])
        sonuc = ArsivIndirici(arsiv, ParquetDepo(depo_kok)).indir("LUNAUSDT")
        assert sonuc.kalite is not None
        assert sonuc.kalite.bosluk_sayisi == 1
        assert sonuc.kalite.bayraklar[KaliteDurumu.GAP] == 1

    def test_hizasiz_barlar_atilir_sayilir_ve_gap_olur(self, depo_kok):
        """BTCUSDT-1h-2018-02 gibi: kesinti sonrası barlar 28:14.789 kaymış açılışla."""
        arsiv = SahteArsiv()
        satir = satirlar(ARALIK_2024_12, 20, mikro=False, fiyat=100_000.0)
        kaymis = []
        for s in satir[5:8]:
            alan = s.split(",")
            alan[0] = str(int(alan[0]) + 1_694_789)
            kaymis.append(",".join(alan))
        anahtar = "data/spot/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2024-12.zip"
        arsiv.ekle(anahtar, satir[:5] + kaymis + satir[8:])
        indirici = ArsivIndirici(arsiv, ParquetDepo(depo_kok))

        sonuc = indirici.indir("BTCUSDT")

        assert sonuc.atilan_hizasiz_bar == {anahtar: 3}
        assert sonuc.kalite is not None and sonuc.kalite.bosluk_sayisi == 1
        assert sonuc.depo is not None and sonuc.depo.bar_sayisi == 17
        govde = json.loads(indirici.manifesto_yolu("BTCUSDT", "1h").read_text(encoding="utf-8"))
        assert govde["atilan_hizasiz_bar"] == {anahtar: 3}

        # İkinci koşu kaydı silmemeli.
        indirici.indir("BTCUSDT")
        govde = json.loads(indirici.manifesto_yolu("BTCUSDT", "1h").read_text(encoding="utf-8"))
        assert govde["atilan_hizasiz_bar"] == {anahtar: 3}

    def test_dogrulama_hatasi_sembol_hatasina_doner(self, kurulum, monkeypatch):
        from scryne_quant.data import arsiv_indirici as mod
        from scryne_quant.data.dogrulama import DogrulamaHatasi

        def patla(*a, **k):
            raise DogrulamaHatasi("sahte")

        monkeypatch.setattr(mod, "dogrula", patla)
        indirici, _, _ = kurulum
        with pytest.raises(ArsivIndirmeHatasi, match="sahte"):
            indirici.indir("BTCUSDT")

    def test_arsivde_olmayan_sembol_veri_yok(self, kurulum):
        indirici, _, depo = kurulum
        sonuc = indirici.indir("USDSOLDUSDT")
        assert sonuc.veri_yok and sonuc.depo is None
        assert not depo.var_mi("USDSOLDUSDT", "1h")

    def test_coklu_indir_hatayi_kaydeder_digerlerini_surdurur(self, kurulum):
        indirici, arsiv, depo = kurulum
        arsiv.aylik("ETHUSDT", "2024-12", ARALIK_2024_12, 10, checksum="0" * 64)
        sonuclar, hatalar = coklu_indir(indirici, ["ETHUSDT", "BTCUSDT"])
        assert set(hatalar) == {"ETHUSDT"}
        assert [s.sembol for s in sonuclar] == ["BTCUSDT"]
        assert depo.var_mi("BTCUSDT", "1h")


class TestSemboller:
    def test_filtre_yok_ve_sirali(self):
        arsiv = SahteArsiv()
        for s in ("ETHUSDT", "BTCUP", "BTCUSDT", "EURUSDT"):
            arsiv.aylik(s, "2024-12", ARALIK_2024_12, 1)
        assert ba.spot_sembolleri(arsiv) == ["BTCUP", "BTCUSDT", "ETHUSDT", "EURUSDT"]


class TestS3Listeleme:
    """Gerçek S3 XML'i: ad alanı, önekler, sayfalama."""

    class _Yanit:
        def __init__(self, govde: str) -> None:
            self.status_code = 200
            self.content = govde.encode()

    @staticmethod
    def _xml(onekler: list[str], anahtarlar: list[str], kesik: bool, sonraki: str = "") -> str:
        ns = "http://s3.amazonaws.com/doc/2006-03-01/"
        parca = "".join(f"<CommonPrefixes><Prefix>{p}</Prefix></CommonPrefixes>" for p in onekler)
        parca += "".join(f"<Contents><Key>{k}</Key></Contents>" for k in anahtarlar)
        marker = f"<NextMarker>{sonraki}</NextMarker>" if sonraki else ""
        return (
            f'<?xml version="1.0"?><ListBucketResult xmlns="{ns}">'
            f"<IsTruncated>{'true' if kesik else 'false'}</IsTruncated>{marker}{parca}"
            "</ListBucketResult>"
        )

    def test_sayfali_liste_birlesir(self, monkeypatch):
        sayfalar = [
            self._xml(["x/A/"], ["x/1.zip"], True, sonraki="x/1.zip"),
            self._xml(["x/B/"], ["x/2.zip"], False),
        ]
        cagrilar: list[dict] = []

        def sahte_istek(self, url, params=None):
            cagrilar.append(dict(params or {}))
            return TestS3Listeleme._Yanit(sayfalar[len(cagrilar) - 1])

        monkeypatch.setattr(HttpArsiv, "_istek", sahte_istek)
        arsiv = HttpArsiv.__new__(HttpArsiv)
        onekler, anahtarlar = arsiv.listele("x/")

        assert onekler == ["x/A/", "x/B/"]
        assert anahtarlar == ["x/1.zip", "x/2.zip"]
        assert cagrilar[1]["marker"] == "x/1.zip"
