"""FXCM MarketData M1 → 1h FX deposu. (K-088, R3 Paket 1(a))

Sentetik dosyalar kaynağın **ölçülmüş** biçimini taklit eder (başlık, `MM/DD/YYYY HH:MM:SS.000`,
UTC, bid+ask, hacimsiz). Gerçek dosya (`data/fx/_gelen`, gitignore; lisans "personal use" —
fixture olarak **dağıtılmaz**) yerelde varsa ayrıca sınanır.
"""

from __future__ import annotations

import datetime as dt
import gzip
import json
from pathlib import Path

import numpy as np
import pytest

from scryne_quant.common.zaman import utc_str
from scryne_quant.data import fx
from scryne_quant.data.fx import FxDepo, FxHatasi, fx_al, hafta_no, m1_oku, pazarlar, saatlik

KOK = Path(__file__).resolve().parents[2]
GERCEK = KOK / "data" / "fx" / "_gelen" / "EURUSD" / "2024-2.csv.gz"
SAAT = 3_600_000


def _satir(t: dt.datetime, bid: float, ask: float | None = None) -> str:
    ask = bid + 0.0002 if ask is None else ask
    return (
        f"{t:%m/%d/%Y %H:%M:%S}.000,{bid:.5f},{bid + 0.0001:.5f},{bid - 0.0001:.5f},{bid:.5f},"
        f"{ask:.5f},{ask + 0.0001:.5f},{ask - 0.0001:.5f},{ask:.5f}"
    )


def _dosya(satirlar: list[str], baslik: str = fx.KAYNAK_BASLIK) -> bytes:
    return gzip.compress(("\n".join([baslik, *satirlar]) + "\n").encode("utf-8"))


def _hafta(
    pazar: dt.date, *, dakika: int = 60 * 3, bas_saat: int = 22, fiyat: float = 1.1
) -> bytes:
    """Pazar `bas_saat`:00 UTC'den itibaren `dakika` dakika, fiyat artan."""
    t0 = dt.datetime.combine(pazar, dt.time(bas_saat), tzinfo=dt.UTC)
    return _dosya([_satir(t0 + dt.timedelta(minutes=i), fiyat + i * 1e-5) for i in range(dakika)])


class SahteKaynak:
    """URL → gövde; `yok` kümesindeki haftalar 404. Çağrılar sayılır (önbellek kanıtı)."""

    def __init__(
        self, haftalar: dict[tuple[int, int], bytes], yok: set[tuple[int, int]] = frozenset()
    ):
        self.haftalar, self.yok, self.cagri = haftalar, set(yok), []

    def __call__(self, url: str) -> bytes | None:
        self.cagri.append(url)
        yil, hafta = url.rsplit("/", 2)[1:]
        anahtar = (int(yil), int(hafta.split(".")[0]))
        if anahtar in self.yok:
            return None
        if anahtar not in self.haftalar:
            raise AssertionError(f"beklenmeyen istek {url}")
        return self.haftalar[anahtar]


# ------------------------------------------------------------------ hafta numarası


class TestHaftaNo:
    @pytest.mark.parametrize(
        ("pazar", "beklenen"),
        [
            (dt.date(2023, 12, 17), (2023, 51)),
            (dt.date(2023, 12, 24), (2023, 52)),
            (dt.date(2023, 12, 31), (2023, 53)),  # 1 Ocak 2024'ü içeren hafta 2023/53 (ölçüldü)
            (dt.date(2024, 1, 7), (2024, 2)),  # 2024/1 kaynakta 404 (ölçüldü)
            (dt.date(2024, 3, 3), (2024, 10)),
            (dt.date(2024, 3, 10), (2024, 11)),
            (dt.date(2024, 10, 27), (2024, 44)),
            (dt.date(2024, 11, 3), (2024, 45)),
        ],
    )
    def test_olculen_anahtarlar(self, pazar, beklenen):
        assert hafta_no(pazar) == beklenen

    def test_pazar_degilse_hata(self):
        with pytest.raises(FxHatasi, match="Pazar değil"):
            hafta_no(dt.date(2024, 3, 4))

    def test_pazarlar_araligi_haftayi_icerir(self):
        assert list(pazarlar(dt.date(2024, 1, 10), dt.date(2024, 1, 27))) == [
            dt.date(2024, 1, 7), dt.date(2024, 1, 14), dt.date(2024, 1, 21)
        ]
        assert list(pazarlar(dt.date(2024, 1, 7), dt.date(2024, 1, 7))) == [dt.date(2024, 1, 7)]
        with pytest.raises(FxHatasi, match="ters"):
            list(pazarlar(dt.date(2024, 2, 1), dt.date(2024, 1, 1)))

    def test_url(self):
        assert fx.dosya_url("EURUSD", 2024, 10) == (
            "https://candledata.fxcorporate.com/m1/EURUSD/2024/10.csv.gz"
        )


# ------------------------------------------------------------------ okuma


class TestM1Oku:
    def test_damga_utc_ve_bid_ask_korunur(self):
        t = dt.datetime(2024, 3, 3, 22, 3, tzinfo=dt.UTC)
        df = m1_oku(_dosya([_satir(t, 1.08345, 1.0843)]))
        assert int(df["open_time"].iloc[0]) == int(t.timestamp() * 1000)
        assert utc_str(int(df["open_time"].iloc[0])) == "2024-03-03 22:03:00 UTC"
        assert df["bid_close"].iloc[0] == 1.08345 and df["ask_close"].iloc[0] == 1.0843
        assert list(df.columns) == list(fx.FX_BAR_SUTUNLARI[:9])

    def test_baslik_farkli_red(self):
        with pytest.raises(FxHatasi, match="başlık"):
            m1_oku(_dosya(["x"], baslik="DateTime,Open,High,Low,Close"))

    def test_bos_gzip_degil_sirasiz_ohlc_red(self):
        with pytest.raises(FxHatasi, match="gzip"):
            m1_oku(b"not gzip")
        with pytest.raises(FxHatasi, match="veri satırı yok"):
            m1_oku(_dosya([]))
        t = dt.datetime(2024, 3, 3, 22, 0, tzinfo=dt.UTC)
        with pytest.raises(FxHatasi, match="artan/tekil"):
            m1_oku(_dosya([_satir(t + dt.timedelta(minutes=1), 1.1), _satir(t, 1.1)]))
        with pytest.raises(FxHatasi, match="artan/tekil"):
            m1_oku(_dosya([_satir(t, 1.1), _satir(t, 1.1)]))
        with pytest.raises(FxHatasi, match="OHLC tutarsız"):
            m1_oku(_dosya(["03/03/2024 22:00:00.000,1.1,1.0,1.0,1.1,1.1,1.2,1.0,1.1"]))
        with pytest.raises(FxHatasi, match="biçimi dışı"):
            m1_oku(_dosya(["2024-03-03 22:00:00,1.1,1.1,1.1,1.1,1.1,1.1,1.1,1.1"]))
        with pytest.raises(FxHatasi, match="dakika ızgarası"):
            m1_oku(_dosya(["03/03/2024 22:00:30.000,1.1,1.1,1.1,1.1,1.1,1.1,1.1,1.1"]))


class TestSaatlik:
    def test_ilk_maks_min_son_ve_sayim(self):
        t0 = dt.datetime(2024, 3, 3, 22, 0, tzinfo=dt.UTC)
        satirlar = [_satir(t0 + dt.timedelta(minutes=i), 1.1 + i * 1e-4) for i in (5, 30, 59)]
        satirlar += [_satir(t0 + dt.timedelta(minutes=i), 1.2 - (i - 60) * 1e-4) for i in (60, 61)]
        h = saatlik(m1_oku(_dosya(satirlar)))
        assert len(h) == 2 and list(h["m1_sayisi"]) == [3, 2]
        assert int(h["open_time"].iloc[0]) == int(t0.timestamp() * 1000)
        b = h.iloc[0]
        assert (b["bid_open"], b["bid_close"]) == (1.1005, 1.1059)
        assert b["bid_high"] == pytest.approx(1.1059 + 0.0001)
        assert b["bid_low"] == pytest.approx(1.1005 - 0.0001)
        assert b["ask_open"] == pytest.approx(1.1005 + 0.0002)
        assert h["open_time"].dtype == np.dtype("int64") and (h["open_time"] % SAAT == 0).all()

    def test_bos(self):
        tek = m1_oku(_dosya([_satir(dt.datetime(2024, 3, 3, 22, tzinfo=dt.UTC), 1.1)]))
        assert saatlik(tek.iloc[0:0]).empty


# ------------------------------------------------------------------ depo / idempotency / K-080


@pytest.fixture
def kaynak():
    return SahteKaynak(
        {
            (2024, 2): _hafta(dt.date(2024, 1, 7)),
            (2024, 3): _hafta(dt.date(2024, 1, 14), fiyat=1.2),
            (2024, 4): _hafta(dt.date(2024, 1, 21), fiyat=1.3),
        },
        yok={(2024, 5)},
    )


class TestFxAl:
    def test_kurulum_manifesto_ve_bayt_idempotency(self, tmp_path, kaynak):
        depo = FxDepo(tmp_path)
        k1 = fx_al("EURUSD", "2024-01-07", "2024-02-02", depo=depo, indirici=kaynak)
        assert k1.bar_sayisi == 9 and utc_str(k1.ilk_ms) == "2024-01-07 22:00:00 UTC"
        assert set(k1.haftalar) == {"2024-2", "2024-3", "2024-4", "2024-5"}
        assert k1.haftalar["2024-5"] == {"durum": "yok", "pazar": "2024-01-28"}
        assert k1.haftalar["2024-2"]["m1_satir"] == 180
        assert len(k1.haftalar["2024-2"]["sha256"]) == 64
        p1 = depo.parquet_yolu("EURUSD").read_bytes()
        m1 = depo.manifesto_yolu("EURUSD").read_bytes()
        assert json.loads(m1)["sha256"] == k1.sha256
        assert json.loads(m1)["veri_sonu"] == utc_str(k1.son_ms)
        n = len(kaynak.cagri)
        k2 = fx_al("EURUSD", "2024-01-07", "2024-02-02", depo=depo, indirici=kaynak)
        assert depo.parquet_yolu("EURUSD").read_bytes() == p1
        assert depo.manifesto_yolu("EURUSD").read_bytes() == m1
        assert k2.sha256 == k1.sha256 and len(kaynak.cagri) == n  # gelen dosyalar yeniden istenmedi
        assert (tmp_path / "_gelen" / "EURUSD" / "2024-5.yok").exists()
        df = depo.oku("EURUSD")
        assert list(df.columns) == list(fx.FX_BAR_SUTUNLARI)
        assert df["open_time"].is_monotonic_increasing

    def test_bitis_gun_kirpar_ve_geri_uzatilinca_ayni(self, tmp_path, kaynak):
        depo = FxDepo(tmp_path)
        tam = fx_al("EURUSD", "2024-01-07", "2024-02-02", depo=depo, indirici=kaynak)
        tam_bayt = depo.parquet_yolu("EURUSD").read_bytes()
        n = len(kaynak.cagri)
        sabit = fx_al("EURUSD", "2024-01-07", "2024-02-02", depo=depo, indirici=kaynak,
                      bitis_gun="2024-01-14")
        # h2 (Paz 22, 23, Pzt 00) + h3'ten 14 Ocak 22:00 ve 23:00; 15 Ocak 00:00 sınır dışı.
        assert sabit.bitis_gun == "2024-01-14" and sabit.bar_sayisi == 5
        assert utc_str(sabit.son_ms) == "2024-01-14 23:00:00 UTC"
        assert "2024-4" not in sabit.haftalar and len(kaynak.cagri) == n  # sonraki hafta istenmedi
        assert depo.manifesto("EURUSD")["bitis_gun"] == "2024-01-14"
        geri = fx_al("EURUSD", "2024-01-07", "2024-02-02", depo=depo, indirici=kaynak)
        assert geri.sha256 == tam.sha256 and depo.parquet_yolu("EURUSD").read_bytes() == tam_bayt

    def test_gecersiz_girdi(self, tmp_path, kaynak):
        with pytest.raises(FxHatasi, match="pair"):
            fx_al("eurusd", "2024-01-07", "2024-02-02", depo=FxDepo(tmp_path), indirici=kaynak)
        with pytest.raises(FxHatasi, match="YYYY-MM-DD"):
            fx_al("EURUSD", "2024/01/07", "2024-02-02", depo=FxDepo(tmp_path), indirici=kaynak)
        with pytest.raises(FxHatasi, match="depoda yok"):
            FxDepo(tmp_path).oku("GBPUSD")

    def test_cakisan_dakika_iki_haftada_red(self, tmp_path):
        ayni = _hafta(dt.date(2024, 1, 7))
        k = SahteKaynak({(2024, 2): ayni, (2024, 3): ayni})
        with pytest.raises(FxHatasi, match="çakışan dakika"):
            fx_al("EURUSD", "2024-01-07", "2024-01-20", depo=FxDepo(tmp_path), indirici=k)

    def test_parquet_semasi_ve_hacim_yok(self, tmp_path, kaynak):
        import pyarrow.parquet as pq

        depo = FxDepo(tmp_path)
        fx_al("EURUSD", "2024-01-07", "2024-01-13", depo=depo, indirici=kaynak)
        sema = pq.read_schema(depo.parquet_yolu("EURUSD"))
        assert sema.names == list(fx.FX_BAR_SUTUNLARI)
        assert "volume" not in sema.names and "close" not in sema.names  # mid/hacim üretilmez (R4)
        assert sema.metadata is None or b"pandas" not in sema.metadata


@pytest.mark.skipif(not GERCEK.exists(), reason="gerçek FXCM dosyası yerelde yok (gitignore)")
class TestGercekDosya:
    def test_2024_hafta2_olculen_seans(self):
        m1 = m1_oku(GERCEK.read_bytes(), ad=GERCEK.name)
        assert utc_str(int(m1["open_time"].iloc[0])) == "2024-01-07 22:08:00 UTC"
        assert utc_str(int(m1["open_time"].iloc[-1])) == "2024-01-12 21:59:00 UTC"
        assert len(m1) == 7172
        h = saatlik(m1)
        assert len(h) == 120 and 1 <= h["m1_sayisi"].min() <= h["m1_sayisi"].max() <= 60
        assert (h["ask_close"] >= h["bid_close"]).all()  # spread ≥ 0 her saatte


# --------------------------------------------------------- Paket 1(b)+(c): çiftler, keşif, kalite


class TestCiftlerVeKesif:
    def test_21_cift_kapali_kume(self, tmp_path, kaynak):
        assert len(fx.FXCM_CIFTLER) == 21 and len(set(fx.FXCM_CIFTLER)) == 21
        assert all(len(p) == 6 and p.isupper() for p in fx.FXCM_CIFTLER)
        with pytest.raises(FxHatasi, match="listesinde yok"):
            fx_al("ABCDEF", "2024-01-07", "2024-01-13", depo=FxDepo(tmp_path), indirici=kaynak)
        assert dt.date(2012, 1, 1) == fx.KAYNAK_BASLANGIC
        assert fx.hafta_no(fx.KAYNAK_BASLANGIC) == (2012, 1)

    def test_kesfet_head_ile_indirmeden(self):
        soruldu = []

        def var_mi(url: str) -> bool:
            soruldu.append(url)
            return "2024/5" not in url

        r = fx.kesfet("EURUSD", "2024-01-07", "2024-02-02", var_mi=var_mi)
        assert (r["hafta"], r["var"], r["yok"]) == (4, 3, 1)
        assert r["ilk_var"] == "2024-01-07" and r["son_var"] == "2024-01-21"
        assert r["haftalar"]["2024-5"] == {"pazar": "2024-01-28", "var": False}
        assert soruldu == [fx.dosya_url("EURUSD", 2024, w) for w in (2, 3, 4, 5)]
        assert json.dumps(r, sort_keys=True) == json.dumps(
            fx.kesfet("EURUSD", "2024-01-07", "2024-02-02", var_mi=var_mi), sort_keys=True
        )
        with pytest.raises(FxHatasi, match="listesinde yok"):
            fx.kesfet("ABCDEF", "2024-01-07", "2024-01-13", var_mi=var_mi)


def _hafta_saatli(pazar: dt.date, *, saatler: list[int], bas_saat: int = 22) -> bytes:
    """Pazar `bas_saat`:00'dan itibaren yalnız verilen saat ofsetlerinde 60'ar dakika."""
    t0 = dt.datetime.combine(pazar, dt.time(bas_saat), tzinfo=dt.UTC)
    satirlar = []
    for h in saatler:
        for m in range(60):
            satirlar.append(_satir(t0 + dt.timedelta(hours=h, minutes=m), 1.1 + h * 1e-4))
    return _dosya(satirlar)


class TestFxKalite:
    @pytest.fixture
    def kalite_depo(self, tmp_path):
        kaynak = SahteKaynak(
            {
                # h2: kış açılışı 22:00, 5 saat tam
                (2024, 2): _hafta_saatli(dt.date(2024, 1, 7), saatler=[0, 1, 2, 3, 4]),
                # h3: 2. saat eksik → hafta içi gap
                (2024, 3): _hafta_saatli(dt.date(2024, 1, 14), saatler=[0, 1, 3, 4]),
                # h4: dosya yok (404) → eksik_dosya
                # h5: "DST" haftası 21:00 açılış, tam
                (2024, 5): _hafta_saatli(dt.date(2024, 1, 28), saatler=[0, 1, 2], bas_saat=21),
                # h6: son saat kısa (30 dk) — gap değil, kısa saat
                (2024, 6): _dosya(
                    [
                        _satir(
                            dt.datetime(2024, 2, 4, 22, tzinfo=dt.UTC) + dt.timedelta(minutes=m),
                            1.2,
                        )
                        for m in range(90)
                    ]
                ),
            },
            yok={(2024, 4), (2024, 7)},
        )
        depo = FxDepo(tmp_path)
        fx_al("EURUSD", "2024-01-07", "2024-02-16", depo=depo, indirici=kaynak)
        return depo

    def test_hafta_sonu_gap_degil_hafta_ici_eksik_saat_gap(self, kalite_depo):
        k = fx.fx_kalite(kalite_depo, "EURUSD")
        assert k["bar"]["mevcut"] == 5 + 4 + 3 + 2
        assert k["bar"]["beklenen"] == 5 + 5 + 3 + 2  # haftalar arası (hafta sonu) sayılmaz
        assert k["bar"]["eksik"] == 1
        assert k["bar"]["eksik_saatler"] == ["2024-01-15 00:00:00 UTC"]
        assert k["haftalar"]["2024-3"]["eksik_bar"] == 1
        assert k["haftalar"]["2024-2"]["eksik_bar"] == 0

    def test_eksik_dosya_ile_kapsam_disi_ayri(self, kalite_depo):
        k = fx.fx_kalite(kalite_depo, "EURUSD")
        assert k["dosya"] == {
            "hafta": 6, "var": 4, "eksik_dosya": ["2024-4"], "kapsam_disi": ["2024-7"]
        }
        assert k["haftalar"]["2024-4"] == {"durum": "yok", "pazar": "2024-01-21"}

    def test_dst_acilisi_yanlis_gap_uretmez_ve_seans_kaniti(self, kalite_depo):
        k = fx.fx_kalite(kalite_depo, "EURUSD")
        assert k["haftalar"]["2024-5"]["acilis"] == "2024-01-28 21:00:00 UTC"
        assert k["haftalar"]["2024-5"]["eksik_bar"] == 0
        assert k["seans"]["acilis_saati_utc"] == {"21": 1, "22": 3}
        assert k["seans"]["hafta_uzunlugu_saat"] == {"2": 1, "3": 1, "5": 2}

    def test_kisa_saat_gap_degil(self, kalite_depo):
        k = fx.fx_kalite(kalite_depo, "EURUSD")
        assert k["bar"]["kisa_saat"] == 1 and k["bar"]["kisa_saat_dagilimi"] == {"23": 1}
        assert k["haftalar"]["2024-6"]["eksik_bar"] == 0

    def test_deterministik_ve_json(self, kalite_depo):
        a = json.dumps(fx.fx_kalite(kalite_depo, "EURUSD"), sort_keys=True)
        b = json.dumps(fx.fx_kalite(kalite_depo, "EURUSD"), sort_keys=True)
        assert a == b
        assert json.loads(a)["veri_sha256"] == kalite_depo.manifesto("EURUSD")["sha256"]

    def test_manifesto_yoksa_hata(self, tmp_path):
        with pytest.raises(FxHatasi, match="manifesto yok"):
            fx.fx_kalite(FxDepo(tmp_path), "EURUSD")

    def test_cli_quality_fx(self, kalite_depo):
        from typer.testing import CliRunner

        from scryne_quant.cli.main import app

        r = CliRunner().invoke(
            app, ["data", "quality", "fx", "EURUSD", "--depo", str(kalite_depo.kok), "--json"]
        )
        assert r.exit_code == 0, r.output
        govde = json.loads(r.output)
        assert govde["kalite"]["pair"] == "EURUSD" and govde["kalite"]["bar"]["eksik"] == 1
