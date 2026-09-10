"""Audit defteri: append-only, zincirlenmiş, PostgreSQL şemasıyla hizalı. (K-008/5, K-011, K-032)

Üç şey ölçülüyor ve üçü de Faz 6'nın ön koşulu:

1. **Append-only teknik olarak zorlanıyor** — yorumda değil veritabanında. SQLite
   tetikleyicileri UPDATE ve DELETE'i hatayla reddediyor.
2. **Zincir sessiz kurcalamayı yakalıyor** — tek bir satırı değiştirmek `dogrula()`yı
   kırıyor.
3. **Şema PostgreSQL karşılığıyla aynı** — `migrations/001_faz5.sql` ile kolon adları
   birebir. Bu test olmadan Faz 6, şemanın ayrıştığını ancak gerçek veritabanına geçerken
   öğrenirdi.

**Üçüncüsü neden bir test:** K-032 "Faz 6 bir şema tasarımıyla değil bir bağlantı dizgisiyle
başlıyor" diyor. O cümlenin doğru kalması, iki dosyanın elle senkron tutulmasına bağlı
olurdu — yani bir gün ayrışırdı. Test o cümleyi bir iddiadan kısıta çeviriyor.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Final

import pytest

from scryne_quant.risk.audit import (
    KOK_HASH,
    KOLONLAR,
    BellekDefteri,
    JsonlDefter,
    Olay,
    OlayTuru,
    SqliteDefter,
)

MIGRATION: Final = Path(__file__).resolve().parents[2] / "migrations" / "001_faz5.sql"
T0 = 1_700_006_400_000


def _sql_kodu() -> str:
    """Migration dosyasının yorumları çıkarılmış hâli.

    Yorumları çıkarmak şart: dosyanın gerekçe blokları `DO INSTEAD NOTHING` gibi
    **reddedilmiş** alternatifleri adıyla anıyor ve ham metinde arama yapan bir test onları
    kod sanar. Testin ilk hâli tam bu yüzden kırıldı.
    """
    satirlar = [
        satir.split("--", 1)[0] for satir in MIGRATION.read_text(encoding="utf-8").splitlines()
    ]
    return "\n".join(satirlar)


def olay(tur: OlayTuru = OlayTuru.ONAY, zaman: int = T0, **govde) -> Olay:
    return Olay(
        tur=tur,
        zaman_ms=zaman,
        sembol="BTCUSDT",
        govde=govde or {"karar": "onay", "onayli_maruziyet": 0.2},
        durum={"safe_mode": False, "bar_sayisi": 1},
    )


class TestZincir:
    def test_ilk_satir_kok_hashe_baglaniyor(self):
        with SqliteDefter(":memory:") as d:
            d.yaz(olay())
            assert d.oku()[0]["onceki_hash"] == KOK_HASH

    def test_her_satir_oncekine_baglaniyor(self):
        with SqliteDefter(":memory:") as d:
            for i in range(5):
                d.yaz(olay(zaman=T0 + i * 3_600_000))
            satirlar = d.oku()
            for onceki, sonraki in zip(satirlar, satirlar[1:], strict=False):
                assert sonraki["onceki_hash"] == onceki["satir_hash"]

    def test_bos_defter_dogrulanir(self):
        with SqliteDefter(":memory:") as d:
            assert d.dogrula() is True

    def test_dogru_zincir_dogrulanir(self):
        with SqliteDefter(":memory:") as d:
            for i in range(10):
                d.yaz(olay(zaman=T0 + i * 3_600_000))
            assert d.dogrula() is True

    def test_kurcalanan_govde_yakalanir(self):
        """Tetikleyiciyi atlatıp doğrudan yazsa bile zincir söyler.

        `PRAGMA writable_schema` ile tetikleyici silinebilir — dolayısıyla tetikleyici tek
        savunma değil. Zincir, o atlatmanın **sessiz** olmasını engelliyor.
        """
        yol = ":memory:"
        d = SqliteDefter(yol)
        for i in range(3):
            d.yaz(olay(zaman=T0 + i * 3_600_000))
        assert d.dogrula() is True

        # Tetikleyicileri düşürüp ortadaki satırı değiştiriyoruz: kasıtlı kurcalama.
        d._baglanti.execute("DROP TRIGGER audit_guncelleme_yok")
        d._baglanti.execute("UPDATE audit SET govde = '{\"karar\":\"onay\"}' WHERE id = 2")
        assert d.dogrula() is False
        d.kapat()

    def test_kurcalanan_onceki_hash_yakalanir(self):
        d = SqliteDefter(":memory:")
        d.yaz(olay())
        d.yaz(olay(zaman=T0 + 3_600_000))
        d._baglanti.execute("DROP TRIGGER audit_guncelleme_yok")
        d._baglanti.execute("UPDATE audit SET onceki_hash = ? WHERE id = 2", ("f" * 64,))
        assert d.dogrula() is False
        d.kapat()

    def test_zaman_ms_bar_zamani_duvar_saati_degil(self):
        """Backtest'te duvar saati yazmak aynı koşuyu iki kez farklı gösterirdi (K-009)."""
        with SqliteDefter(":memory:") as d:
            d.yaz(olay(zaman=T0))
            satir = d.oku()[0]
            assert satir["zaman_ms"] == T0
            assert satir["yazim_ms"] != T0  # duvar saati ayrı alanda

    def test_ayni_icerik_ayni_hash(self):
        """Zincir hash'i deterministik: aynı olaylar aynı zinciri üretir."""
        hashler = []
        for _ in range(2):
            with SqliteDefter(":memory:") as d:
                for i in range(4):
                    son = d.yaz(olay(zaman=T0 + i * 3_600_000))
                hashler.append(son)
        assert hashler[0] == hashler[1]


class TestAppendOnly:
    def test_update_reddedilir(self):
        with SqliteDefter(":memory:") as d:
            d.yaz(olay())
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                d._baglanti.execute("UPDATE audit SET sembol = 'ETHUSDT' WHERE id = 1")

    def test_delete_reddedilir(self):
        with SqliteDefter(":memory:") as d:
            d.yaz(olay())
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                d._baglanti.execute("DELETE FROM audit WHERE id = 1")

    def test_defterde_silme_metodu_yok(self):
        """Sözleşme düzeyinde de yok: `Defter` protokolünde `sil`/`guncelle` bulunmuyor."""
        for sinif in (SqliteDefter, JsonlDefter, BellekDefteri):
            assert not hasattr(sinif, "sil")
            assert not hasattr(sinif, "guncelle")


class TestSemaHizalamasi:
    """Şema `migrations/001_faz5.sql` ile aynı kalmak zorunda (K-032)."""

    def test_sqlite_kolonlari_kanonik_listeyle_ayni(self):
        with SqliteDefter(":memory:") as d:
            gercek = [s[1] for s in d._baglanti.execute("PRAGMA table_info(audit)")]
        assert tuple(gercek) == KOLONLAR

    def test_postgres_kolonlari_ayni(self):
        """Migration dosyasındaki `audit` tablosu aynı kolonları aynı adla taşıyor."""
        sql = _sql_kodu()
        govde = re.search(
            r"CREATE TABLE IF NOT EXISTS audit \((.*?)\n\);", sql, re.DOTALL
        )
        assert govde, "migration'da `audit` tablo tanımı bulunamadı"
        adlar = [
            m.group(1)
            for satir in govde.group(1).splitlines()
            if (m := re.match(r"\s+([a-z_]+)\s+[A-Z]", satir))
        ]
        assert tuple(adlar) == KOLONLAR, (
            "PostgreSQL şeması SQLite defteriyle ayrıştı; Faz 6 bunu ancak gerçek "
            "veritabanına geçerken öğrenirdi (K-032)"
        )

    def test_postgres_append_only_hatayla_reddediyor(self):
        """`DO INSTEAD NOTHING` yazmayı sessizce yutar; trigger hata fırlatır.

        Sessiz yutma daha kötü: bir DELETE başarılı görünür, hiçbir şey silinmez ve kimse
        yanlış bir şey yapıldığını öğrenmez.
        """
        sql = _sql_kodu()
        assert "DO INSTEAD NOTHING" not in sql, (
            "kural (RULE) ile yazmayı yutmak, hatayla reddetmekten kötü"
        )
        assert "RAISE EXCEPTION" in sql
        assert "BEFORE UPDATE ON audit" in sql
        assert "BEFORE DELETE ON audit" in sql

    def test_migration_risk_durumunu_tasiyor(self):
        """Faz 6'nın restart kriteri için `risk_durumu` tablosu hazır olmalı."""
        sql = _sql_kodu()
        assert "CREATE TABLE IF NOT EXISTS risk_durumu" in sql
        for alan in ("safe_mode", "safe_mode_sebep", "zirve_ozkaynak", "cooldown_bitis_ms"):
            assert alan in sql, f"risk_durumu şemasında eksik alan: {alan}"


class TestJsonlDefteri:
    def test_yazip_okuyor(self, tmp_path):
        d = JsonlDefter(tmp_path / "audit.jsonl")
        d.yaz(olay())
        d.yaz(olay(OlayTuru.RED, zaman=T0 + 3_600_000))
        kayitlar = d.oku()
        assert [k["tur"] for k in kayitlar] == ["onay", "red"]
        assert d.dogrula() is True

    def test_zincir_surec_arasinda_devam_ediyor(self, tmp_path):
        """Yeniden açılan defter zincirin sonundan devam eder, baştan başlamaz."""
        yol = tmp_path / "audit.jsonl"
        a = JsonlDefter(yol)
        son = a.yaz(olay())

        b = JsonlDefter(yol)
        b.yaz(olay(zaman=T0 + 3_600_000))
        assert b.oku()[1]["onceki_hash"] == son
        assert b.dogrula() is True

    def test_kurcalama_yakalanir(self, tmp_path):
        yol = tmp_path / "audit.jsonl"
        d = JsonlDefter(yol)
        d.yaz(olay())
        d.yaz(olay(zaman=T0 + 3_600_000))
        bozuk = yol.read_text(encoding="utf-8").replace('"BTCUSDT"', '"ETHUSDT"', 1)
        yol.write_text(bozuk, encoding="utf-8")
        assert JsonlDefter(yol).dogrula() is False

    def test_sqlite_ile_ayni_zinciri_uretiyor(self, tmp_path):
        """İki backend aynı hash zincirini üretmeli: biçim farkı kimliği değiştirmemeli."""
        olaylar = [olay(zaman=T0 + i * 3_600_000) for i in range(4)]
        j = JsonlDefter(tmp_path / "a.jsonl")
        jsonl_son = [j.yaz(o) for o in olaylar][-1]
        with SqliteDefter(":memory:") as s:
            sqlite_son = [s.yaz(o) for o in olaylar][-1]
        assert jsonl_son == sqlite_son


class TestSayim:
    def test_tur_bazinda_sayim(self):
        with SqliteDefter(":memory:") as d:
            d.yaz(olay(OlayTuru.ONAY))
            d.yaz(olay(OlayTuru.ONAY, zaman=T0 + 3_600_000))
            d.yaz(olay(OlayTuru.RED, zaman=T0 + 7_200_000))
            assert d.sayim() == {"onay": 2, "red": 1}

    def test_tur_suzgeci(self):
        with SqliteDefter(":memory:") as d:
            d.yaz(olay(OlayTuru.ONAY))
            d.yaz(olay(OlayTuru.KILL, zaman=T0 + 3_600_000))
            assert len(d.oku(tur=OlayTuru.KILL)) == 1
            assert len(d.oku()) == 2
