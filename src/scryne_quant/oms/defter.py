"""Emir defteri: "tek emir" iddiasının diskteki karşılığı. (§33, §25, Faz 7)

`oms/emir.py` aynı niyetin aynı kimliği ürettiğini garanti ediyor. Bu modül o kimliği
**tekil** yapıyor: `istemci_kimligi` birincil anahtar, yani aynı kimliğe ikinci bir satır
yazmak veritabanı düzeyinde imkânsız.

**Neden yalnızca deterministik kimlik yetmez.** Borsa duplicate kimliği reddeder — ama o
reddi görebilmek için isteği **göndermiş** olman gerekir, ve gönderim başlı başına bir
risk: yanıt kaybolursa emrin oluşup oluşmadığını bilemezsin (`EmirDurumu.UNKNOWN`).
Defter bu riski hiç almamayı sağlıyor: aynı niyet ikinci kez geldiğinde istek **hiç
gönderilmiyor**, çünkü defter o kimliği zaten tanıyor.

Yani iki katman var ve ikisi de gerekli:

| Katman | Neyi engelliyor |
| --- | --- |
| Defter (yerel) | Aynı niyetin ikinci kez **gönderilmesini** |
| Deterministik kimlik (borsa) | Defterin kaçırdığı bir ikinci gönderimin **emir olmasını** |

İkincisi birincinin yedeği: defter dosyası kaybolsa, elle silinse veya başka bir makineden
koşulsa bile borsa tarafındaki koruma ayakta kalır.

**`yer_ac` neden bir çift döndürüyor.** `(emir, yeni_mi)` — ve `yeni_mi` yanlışsa çağıran
**göndermemek zorunda**. Sessizce mevcut emri döndürmek, çağıranın "gönderdim" sanmasına
yol açardı; `None` döndürmek ise mevcut emrin durumunu gizlerdi (oysa çağıranın öğrenmesi
gereken tam olarak o: emir hangi durumda). İkisini birlikte vermek, tek doğru cevap.

Defter koşu dosyasının içinde yaşıyor (K-034): emir, risk kararı ve koşu durumu tek dosyada,
yani koşunun kopyası emirlerinin de kopyası.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any, Final

from scryne_quant.oms.emir import ACIK, Emir, EmirDurumu, EmirHatasi, Komisyon

BELLEK: Final = ":memory:"


class DefterHatasi(EmirHatasi):
    """Emir defteri sözleşmesi ihlal edildi."""


_SEMA = """
CREATE TABLE IF NOT EXISTS emir (
    -- Birincil anahtar **istemci kimliği**, otomatik bir sayı değil: "tek emir" iddiası
    -- burada, veritabanı kısıtı olarak yaşıyor. Otoartan bir anahtar olsaydı aynı
    -- kimlikten iki satır mümkün olur ve iddia bir koda, yani bir dikkate bağlı kalırdı.
    istemci_kimligi TEXT    PRIMARY KEY,
    sembol          TEXT    NOT NULL,
    yon             TEXT    NOT NULL,
    miktar          REAL    NOT NULL,
    durum           TEXT    NOT NULL,
    borsa_kimligi   TEXT,
    dolan_miktar    REAL    NOT NULL,
    ortalama_fiyat  REAL    NOT NULL,
    karar_ms        INTEGER NOT NULL,
    olusturuldu_ms  INTEGER NOT NULL,
    guncellendi_ms  INTEGER NOT NULL,
    gecmis          TEXT    NOT NULL,
    hata            TEXT    NOT NULL,

    -- Komisyon iki sütun: rakam ve **nereden geldiği**. Kaynak boşken komisyon
    -- "sıfır" değil "bilinmiyor" demektir (`oms/emir.KOMISYON_KAYNAKLARI`) ve pozisyon
    -- mutabakatı ikisini farklı işler. Tek sütun olsaydı, ölçülmemiş bir komisyon ile
    -- ölçülüp sıfır çıkmış bir komisyon diskte ayırt edilemezdi.
    komisyon        TEXT    NOT NULL DEFAULT '[]',
    komisyon_kaynagi TEXT   NOT NULL DEFAULT '',

    -- Tür ayrı bir sütun, `limit_fiyati`nın doluluğundan çıkarılmıyor: "fiyatı yoksa
    -- market'tir" kuralı, fiyatı yazılmayı unutulmuş bir limit emrini sessizce market
    -- emri gibi okur (`oms/emir.EMIR_TURLERI`).
    tur             TEXT    NOT NULL DEFAULT 'MARKET',
    limit_fiyati    REAL    NOT NULL DEFAULT 0.0
);
CREATE INDEX IF NOT EXISTS emir_durum ON emir (durum);
CREATE INDEX IF NOT EXISTS emir_karar ON emir (karar_ms);

-- Koşunun **açılış bakiyesi**: pozisyon mutabakatının bizim tarafımızdaki çıpası.
--
-- Tek satır (`tek = 1`) ve **yazılıp bırakılır**: iki tetik hem güncellemeyi hem silmeyi
-- reddediyor. Yazılabilir olsaydı pozisyon mutabakatının anlamı kalmazdı — açıklanamayan
-- bir farkla karşılaşan herkesin elinde "çıpayı tazele" diye bir düğme olurdu ve fark,
-- araştırılmak yerine sıfırlanırdı. Çıpanın değişmezliği, karşılaştırmayı bir ölçüm
-- yapan tek şey.
CREATE TABLE IF NOT EXISTS acilis_bakiyesi (
    tek        INTEGER PRIMARY KEY CHECK (tek = 1),
    varliklar  TEXT    NOT NULL,
    borsa_ms   INTEGER NOT NULL,
    yerel_ms   INTEGER NOT NULL,
    not_metni  TEXT    NOT NULL
);

CREATE TRIGGER IF NOT EXISTS acilis_degismez
BEFORE UPDATE ON acilis_bakiyesi
BEGIN SELECT RAISE(ABORT, 'açılış bakiyesi değiştirilemez: çıpa tazelenirse fark ölçülemez'); END;

CREATE TRIGGER IF NOT EXISTS acilis_silinmez
BEFORE DELETE ON acilis_bakiyesi
BEGIN SELECT RAISE(ABORT, 'açılış bakiyesi silinemez: koşunun başlangıç kaydı'); END;

-- Emir **silinemez**. Bir emri silmek, olmuş bir gönderimi kayıttan çıkarmak demek —
-- ve reconciliation'ın (§25) karşılaştıracağı iki taraftan birini yok etmek.
-- Güncelleme serbest: durum geçişleri yerinde yazılıyor, ama geçmiş `gecmis` sütununda
-- birikiyor, yani yol kaybolmuyor.
CREATE TRIGGER IF NOT EXISTS emir_silme_yok
BEFORE DELETE ON emir
BEGIN SELECT RAISE(ABORT, 'emir silinemez: olmuş bir gönderim kayıttan çıkarılamaz'); END;

-- Kimlik değiştirilemez: kimliği değiştirmek, o emri başka bir emre dönüştürmektir.
CREATE TRIGGER IF NOT EXISTS emir_kimlik_degismez
BEFORE UPDATE OF istemci_kimligi ON emir
BEGIN SELECT RAISE(ABORT, 'istemci kimliği değişmez (§33 idempotency)'); END;
"""


class EmirDefteri:
    """Koşuya ait emirlerin dayanıklı kaydı.

    `live/depo.py` ile aynı kilit ve WAL kalıbı: tek yazıcı, çok okuyucu, iş parçacığı
    kısıtı kapatılmıyor kilide taşınıyor.
    """

    __slots__ = ("yol", "_baglanti", "_kilit")

    def __init__(self, yol: str | Path = BELLEK) -> None:
        bellekte = str(yol) == BELLEK
        self.yol = Path(str(yol))
        if not bellekte:
            self.yol.parent.mkdir(parents=True, exist_ok=True)
        self._kilit = threading.RLock()
        self._baglanti = sqlite3.connect(
            str(yol), isolation_level=None, check_same_thread=False
        )
        self._baglanti.row_factory = sqlite3.Row
        if not bellekte:
            self._baglanti.execute("PRAGMA journal_mode=WAL")
            self._baglanti.execute("PRAGMA synchronous=FULL")
        self._baglanti.executescript(_SEMA)
        self._gocu_uygula()

    # -------------------------------------------------------------------- göç

    def _gocu_uygula(self) -> None:
        """Faz 7'de açılmış defterlere komisyon sütunlarını ekler.

        `CREATE TABLE IF NOT EXISTS` var olan bir tabloya sütun **eklemez**: Faz 7'nin
        100 emirlik koşusu gibi mevcut dosyalar şemanın eski hâliyle açılır ve ilk
        `INSERT`te "no such column" ile patlardı. Göç `DEFAULT` değerleriyle geliyor, yani
        eski satırlar *"komisyon bilinmiyor"* olarak açılıyor — ve bu doğru: o emirlerin
        komisyonu gerçekten kaydedilmemişti. Sıfır yazmak, ölçülmemiş bir şeyi ölçülmüş
        göstermek olurdu.
        """
        mevcut = {
            str(s["name"]) for s in self._baglanti.execute("PRAGMA table_info(emir)")
        }
        for sutun, tanim in (
            ("komisyon", "TEXT NOT NULL DEFAULT '[]'"),
            ("komisyon_kaynagi", "TEXT NOT NULL DEFAULT ''"),
            ("tur", "TEXT NOT NULL DEFAULT 'MARKET'"),
            ("limit_fiyati", "REAL NOT NULL DEFAULT 0.0"),
        ):
            if sutun not in mevcut:
                self._baglanti.execute(f"ALTER TABLE emir ADD COLUMN {sutun} {tanim}")

    # ------------------------------------------------------------------ işlem

    @contextmanager
    def _islem(self) -> Iterator[sqlite3.Connection]:
        with self._kilit:
            self._baglanti.execute("BEGIN IMMEDIATE")
            try:
                yield self._baglanti
            except BaseException:
                self._baglanti.execute("ROLLBACK")
                raise
            self._baglanti.execute("COMMIT")

    def _sorgu(self, sorgu: str, parametreler: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self._kilit:
            return list(self._baglanti.execute(sorgu, parametreler))

    # ------------------------------------------------------------------ yazma

    def yer_ac(self, emir: Emir) -> tuple[Emir, bool]:
        """Emri deftere yazar. Döner: `(emir, yeni_mi)`.

        **`yeni_mi` yanlışsa çağıran göndermemek zorunda.** Dönen emir defterdeki mevcut
        kayıttır — yani "bu niyet zaten bir emre dönüşmüş, durumu şu" cevabı. Duplicate
        koruması bu satırda: istek borsaya **hiç gitmiyor**.
        """
        mevcut = self.al(emir.istemci_kimligi)
        if mevcut is not None:
            return mevcut, False
        with self._islem() as b:
            b.execute(
                "INSERT INTO emir (istemci_kimligi, sembol, yon, miktar, durum, "
                "borsa_kimligi, dolan_miktar, ortalama_fiyat, karar_ms, olusturuldu_ms, "
                "guncellendi_ms, gecmis, hata, komisyon, komisyon_kaynagi, tur, "
                "limit_fiyati) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    emir.istemci_kimligi,
                    emir.sembol,
                    emir.yon,
                    emir.miktar,
                    str(emir.durum),
                    emir.borsa_kimligi,
                    emir.dolan_miktar,
                    emir.ortalama_fiyat,
                    emir.karar_ms,
                    emir.olusturuldu_ms,
                    emir.guncellendi_ms,
                    json.dumps(list(emir.gecmis), ensure_ascii=False),
                    emir.hata,
                    _komisyon_metni(emir.komisyon),
                    emir.komisyon_kaynagi,
                    emir.tur,
                    emir.limit_fiyati,
                ),
            )
        return emir, True

    def gecir(
        self,
        istemci_kimligi: str,
        durum: EmirDurumu,
        *,
        zaman_ms: int,
        borsa_kimligi: str | None = None,
        dolan_miktar: float | None = None,
        ortalama_fiyat: float | None = None,
        komisyon: Komisyon | None = None,
        komisyon_kaynagi: str | None = None,
        hata: str = "",
    ) -> Emir:
        """Emri yeni duruma geçirip **aynı transaction'da** yazar.

        Geçiş kontrolü `Emir.gecir`de (state machine), yazım burada. İkisinin tek bir
        transaction'da olması şart: geçiş bellekte yapılıp yazım ayrı olsaydı, aradaki
        anda ölen bir süreç emri eski durumda bırakır ve bellekteki doğru durum kaybolurdu.
        """
        with self._islem() as b:
            satir = b.execute(
                "SELECT * FROM emir WHERE istemci_kimligi = ?", (istemci_kimligi,)
            ).fetchone()
            if satir is None:
                raise DefterHatasi(f"emir defterde yok: {istemci_kimligi}")

            yeni = _satirdan(satir).gecir(
                durum,
                zaman_ms=zaman_ms,
                borsa_kimligi=borsa_kimligi,
                dolan_miktar=dolan_miktar,
                ortalama_fiyat=ortalama_fiyat,
                komisyon=komisyon,
                komisyon_kaynagi=komisyon_kaynagi,
                hata=hata,
            )
            b.execute(
                "UPDATE emir SET durum = ?, borsa_kimligi = ?, dolan_miktar = ?, "
                "ortalama_fiyat = ?, guncellendi_ms = ?, gecmis = ?, hata = ?, "
                "komisyon = ?, komisyon_kaynagi = ? "
                "WHERE istemci_kimligi = ?",
                (
                    str(yeni.durum),
                    yeni.borsa_kimligi,
                    yeni.dolan_miktar,
                    yeni.ortalama_fiyat,
                    yeni.guncellendi_ms,
                    json.dumps(list(yeni.gecmis), ensure_ascii=False),
                    yeni.hata,
                    _komisyon_metni(yeni.komisyon),
                    yeni.komisyon_kaynagi,
                    istemci_kimligi,
                ),
            )
        return yeni

    def komisyon_yaz(
        self, istemci_kimligi: str, komisyon: Komisyon, *, kaynak: str
    ) -> Emir:
        """Komisyonu **durum değiştirmeden** yazar. Yalnızca boş kaynağı doldurur.

        Ayrı bir metot çünkü komisyonun öğrenilmesi bir durum geçişi değil: `FILLED` bir
        emrin komisyonu sonradan `/api/v3/myTrades`ten gelir ve emir nihai durumda olduğu
        için `gecir` çağrılamaz (nihai durumdan geçiş yok, ve olmaması doğru).

        Kaynak zaten yazılıysa **hiçbir şey yapmaz** — ilk ölçüm korunur. İkinci bir
        kaynağın farklı bir sayı söylemesi sessizce kabul edilecek bir şey değil.
        """
        with self._islem() as b:
            satir = b.execute(
                "SELECT * FROM emir WHERE istemci_kimligi = ?", (istemci_kimligi,)
            ).fetchone()
            if satir is None:
                raise DefterHatasi(f"emir defterde yok: {istemci_kimligi}")
            mevcut = _satirdan(satir)
            if mevcut.komisyon_kaynagi:
                return mevcut
            if kaynak not in ("yanit", "islemler"):
                raise DefterHatasi(
                    f"komisyon kaynağı 'yanit' ya da 'islemler' olmalı: {kaynak!r}"
                )
            b.execute(
                "UPDATE emir SET komisyon = ?, komisyon_kaynagi = ? "
                "WHERE istemci_kimligi = ?",
                (_komisyon_metni(komisyon), kaynak, istemci_kimligi),
            )
        return replace(mevcut, komisyon=komisyon, komisyon_kaynagi=kaynak)

    # ------------------------------------------------------- açılış bakiyesi

    def acilis_yaz(
        self,
        varliklar: Mapping[str, tuple[float, float]],
        *,
        borsa_ms: int,
        yerel_ms: int,
        not_metni: str = "",
    ) -> None:
        """Koşunun açılış bakiyesini **bir kez** yazar. İkinci çağrı hatadır.

        Varlıklar `{varlık: (serbest, kilitli)}` — ikisi ayrı, çünkü pozisyon mutabakatı
        toplamı kullanır ama farkın hangi tarafta doğduğunu görmek için ayrımı ister.

        İkinci çağrının hata olması bir kolaylık kaybı değil, mekanizmanın kendisi: bir
        koşunun tek bir başlangıcı vardır. `zaten_var` ile önce sorulabilir.
        """
        if self.acilis_oku() is not None:
            raise DefterHatasi(
                "açılış bakiyesi zaten yazılmış. Bir koşunun tek bir başlangıcı vardır; "
                "yeni bir çıpa isteyen yeni bir koşu açar."
            )
        # Çıpa **ilk emirden önce** atılmak zorunda. Emirler varken yazılan bir açılış
        # bakiyesi, aradaki emirlerin etkisini içine almış olur: o emirler bir kez
        # bakiyeye, bir kez de beklenen hesabına girer ve fark tam olarak onlar kadar
        # çıkar. Sessizce izin vermek, mutabakatı ilk koşuda yanlış yapan bir kurulum
        # hatasını kalıcı kılardı.
        if self._sorgu("SELECT 1 FROM emir LIMIT 1"):
            raise DefterHatasi(
                "açılış bakiyesi emirlerden sonra yazılamaz: çıpa koşunun başlangıcını "
                "göstermeli. Deftere emir girmişse o koşunun başlangıcı kaçırılmıştır."
            )
        govde = {
            varlik: {"serbest": float(s), "kilitli": float(k)}
            for varlik, (s, k) in sorted(varliklar.items())
        }
        with self._islem() as b:
            b.execute(
                "INSERT INTO acilis_bakiyesi (tek, varliklar, borsa_ms, yerel_ms, "
                "not_metni) VALUES (1, ?, ?, ?, ?)",
                (
                    json.dumps(govde, ensure_ascii=False, sort_keys=True),
                    int(borsa_ms),
                    int(yerel_ms),
                    not_metni,
                ),
            )

    def acilis_oku(self) -> dict[str, Any] | None:
        """Açılış kaydı; hiç yazılmadıysa `None`."""
        satirlar = self._sorgu("SELECT * FROM acilis_bakiyesi WHERE tek = 1")
        if not satirlar:
            return None
        satir = satirlar[0]
        return {
            "varliklar": json.loads(satir["varliklar"]),
            "borsa_ms": int(satir["borsa_ms"]),
            "yerel_ms": int(satir["yerel_ms"]),
            "not_metni": str(satir["not_metni"]),
        }

    # ------------------------------------------------------------------ okuma

    def al(self, istemci_kimligi: str) -> Emir | None:
        satirlar = self._sorgu(
            "SELECT * FROM emir WHERE istemci_kimligi = ?", (istemci_kimligi,)
        )
        return _satirdan(satirlar[0]) if satirlar else None

    def acik_emirler(self) -> list[Emir]:
        """Borsada **var olabilecek** emirler. Reconciliation'ın sorgulayacağı küme (§25).

        `UNKNOWN` bu kümede ve olmak zorunda: bilinmezlik, yokluk değil.
        """
        isaretler = ",".join("?" * len(ACIK))
        return [
            _satirdan(s)
            for s in self._sorgu(
                f"SELECT * FROM emir WHERE durum IN ({isaretler}) ORDER BY olusturuldu_ms",
                sorted(str(d) for d in ACIK),
            )
        ]

    def tumu(self, *, limit: int | None = None) -> list[Emir]:
        sorgu = "SELECT * FROM emir ORDER BY olusturuldu_ms DESC"
        if limit is not None:
            sorgu += f" LIMIT {int(limit)}"
        return [_satirdan(s) for s in self._sorgu(sorgu)]

    def sayim(self) -> dict[str, int]:
        return {
            str(s["durum"]): int(s["n"])
            for s in self._sorgu("SELECT durum, COUNT(*) AS n FROM emir GROUP BY durum")
        }

    # ------------------------------------------------------------------ ömür

    def kapat(self) -> None:
        with self._kilit:
            self._baglanti.close()

    def __enter__(self) -> EmirDefteri:
        return self

    def __exit__(self, *_: object) -> None:
        self.kapat()


def _satirdan(satir: sqlite3.Row) -> Emir:
    return Emir(
        istemci_kimligi=str(satir["istemci_kimligi"]),
        sembol=str(satir["sembol"]),
        yon=str(satir["yon"]),
        miktar=float(satir["miktar"]),
        durum=EmirDurumu(str(satir["durum"])),
        borsa_kimligi=satir["borsa_kimligi"],
        dolan_miktar=float(satir["dolan_miktar"]),
        ortalama_fiyat=float(satir["ortalama_fiyat"]),
        karar_ms=int(satir["karar_ms"]),
        olusturuldu_ms=int(satir["olusturuldu_ms"]),
        guncellendi_ms=int(satir["guncellendi_ms"]),
        gecmis=tuple(json.loads(satir["gecmis"])),
        komisyon=tuple(
            (str(v), float(m)) for v, m in json.loads(satir["komisyon"] or "[]")
        ),
        komisyon_kaynagi=str(satir["komisyon_kaynagi"] or ""),
        tur=str(satir["tur"] or "MARKET"),
        limit_fiyati=float(satir["limit_fiyati"] or 0.0),
        hata=str(satir["hata"]),
    )


def _komisyon_metni(komisyon: Komisyon) -> str:
    return json.dumps([list(k) for k in komisyon], ensure_ascii=False)


__all__ = ["BELLEK", "DefterHatasi", "EmirDefteri"]
