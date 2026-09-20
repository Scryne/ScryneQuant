"""K-009 ortam kaydı: bilgilendirici, hash'lere girmez. (R1(f), 2026-09-20)

`duckdb` bağımlılıktan ve `VARSAYILAN_PAKETLER`den çıkarıldı. Bu, eski kayıtların
`kimlik.ortam.paketler`i ile yenilerinin ayrışması demek — ve bunun **hiçbir kimliği**
değiştirmediği burada kanıtlanıyor: deney `girdi_hash`/`cikti_hash` ve backtest
`config_hash`/`sonuc_hash` ortam kaydını okumuyor.
"""

from __future__ import annotations

from scryne_quant.common import hash as hash_mod
from scryne_quant.common.hash import VARSAYILAN_PAKETLER, ortam_kaydi


class TestOrtamKaydi:
    def test_varsayilan_paketlerin_hepsi_kurulu_ve_duckdb_yok(self):
        kayit = ortam_kaydi()
        assert set(kayit["paketler"]) == set(VARSAYILAN_PAKETLER)
        assert "duckdb" not in kayit["paketler"]
        assert all(v is not None for v in kayit["paketler"].values()), kayit["paketler"]
        assert kayit["python"] and kayit["platform"]

    def test_kurulu_olmayan_paket_none_yaziliyor_sessiz_dusmuyor(self):
        kayit = ortam_kaydi(("pandas", "boyle_bir_paket_yok"))
        assert kayit["paketler"]["boyle_bir_paket_yok"] is None
        assert kayit["paketler"]["pandas"]

    def test_ortam_deney_kimligine_girmiyor(self, monkeypatch):
        from scryne_quant.research.deney import Deney

        d = Deney(
            tip="tarama", strateji="x", girdi={"a": 1}, cikti={"b": 2}, veri_sha256="v" * 64
        )
        once = (d.girdi_hash, d.cikti_hash, d.kimlik)
        monkeypatch.setattr(
            hash_mod, "VARSAYILAN_PAKETLER", ("pandas", "numpy", "pyarrow", "duckdb", "ccxt")
        )
        assert (d.girdi_hash, d.cikti_hash, d.kimlik) == once
        assert d.sozluk()["kimlik"]["ortam"]["paketler"].get("duckdb", "yok") in (None, "yok")

    def test_ortam_backtest_sonuc_hashine_girmiyor(self):
        import inspect

        from scryne_quant.backtest import sonuc as sonuc_mod

        kaynak = inspect.getsource(sonuc_mod.Sonuc.sonuc_hash.fget) + inspect.getsource(
            sonuc_mod.Sonuc.config_hash.fget
        )
        assert "ortam" not in kaynak
