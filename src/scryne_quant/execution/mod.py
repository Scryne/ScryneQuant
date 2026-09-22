"""Execution modu: sistemin gerçek paraya ne kadar yakın çalışmaya yetkili olduğu. (K-114)

Live tek bir boolean ile açılmaz. Bu modül açık, sıralı ve denetlenebilir bir durum
makinesidir:

    DISABLED → PAPER → SHADOW → TESTNET → LIVE_PENDING_APPROVAL → LIVE

**Üç kural bu modülün tamamı:**

1. **Yukarı yalnızca bir adım, yalnızca kapıdan geçerek.** Her yukarı geçiş, hedef modun
   kontrol listesini (`execution/canli_kapi.py`) çalıştırır; tek bir kontrol geçmezse geçiş
   yazılmaz. PAPER'dan LIVE'a atlamak diye bir yol yok.
2. **Aşağı her zaman ve kendiliğinden.** Riski azaltan otomasyon serbesttir (K-050):
   kill switch, uyuşmazlık, kopuk bağlantı modu herhangi bir alt moda indirebilir ve bunun
   için onay gerekmez. İzni artıran hiçbir şey otomatik değildir.
3. **`LIVE_PENDING_APPROVAL → LIVE` makine tarafından verilemez.** Tek yol `canli_onayla`;
   o fonksiyonu `execution/`, `trader/`, `risk/` içinden çağıran satır yok ve bu
   `tests/unit/test_canli_izolasyon.py`de `ast` ile kontrol ediliyor — yalnızca
   `cli/execution.py` (insanın yazdığı komut) çağırabilir. Onay bir gerekçe notu (≥ 20
   karakter) ve onaylanan live-gate raporunun hash'ini ister; onay anında kapı **yeniden**
   çalışır ve hash tutmazsa (bir şey değiştiyse) onay reddedilir.

**Kayıt zincirli ve audit'e bağlı** (K-082 kalıbı): `runs/execution/mod.json`in her satırı
`onceki_hash` + `satir_hash` taşır; `yukle()` zinciri baştan doğrular ve kırık bir zincir
**DISABLED** okunur (fail closed) — elle düzenlenmiş bir mod dosyası hiçbir yetki vermez.
Her geçiş ayrıca audit defterine `OlayTuru.EXECUTION` olarak yazılır.

**Mod bir tavan, bir koşu değil.** Sistem modu TESTNET iken bir paper koşusu açılabilir
(daha az risk); LIVE koşusu ise yalnızca mod LIVE iken ve geçerli bir `CanliYetki` ile.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

from scryne_quant.common.hash import nesne_hash
from scryne_quant.common.zaman import simdi_ms, utc_str
from scryne_quant.risk.audit import KOK_HASH, Defter, Olay, OlayTuru


class CalismaModu(StrEnum):
    DISABLED = "DISABLED"
    """Hiçbir koşu emir yoluna bağlanamaz. Başlangıç ve her kırık kaydın okunduğu hâl."""

    PAPER = "PAPER"
    """Gerçek emir yolu, simüle borsa (`exchange/paper_adaptoru.py`)."""

    SHADOW = "SHADOW"
    """Gerçek hesap salt okunur; emir kurulur, doğrulanır, **gönderilmez** (`GOLGE`)."""

    TESTNET = "TESTNET"
    """Gerçek emir, sanal para (Binance Spot Testnet)."""

    LIVE_PENDING_APPROVAL = "LIVE_PENDING_APPROVAL"
    """Makine kontrollerinin tamamı geçti; kalan tek şey insan onayı."""

    LIVE = "LIVE"
    """Gerçek emir, gerçek para. Kademe sermayesiyle sınırlı (K-050/3)."""


SIRA: Final[tuple[CalismaModu, ...]] = tuple(CalismaModu)

#: Onay notunun asgari uzunluğu. `promotion.elle_onayla`nın 10 karakterinin iki katı:
#: bu not gerçek parayı açan kararın tek yazılı gerekçesi.
ASGARI_ONAY_NOTU: Final = 20

VARSAYILAN_YOL: Final = Path("runs/execution/mod.json")

HASH_DISI: Final[frozenset[str]] = frozenset({"onceki_hash", "satir_hash", "audit_hash"})


class ModHatasi(RuntimeError):
    """Mod geçişi kuralı ihlal edildi."""


class OnayGerekli(ModHatasi):
    """`LIVE`a geçiş yalnızca `canli_onayla` ile yapılabilir."""


def sira(mod: CalismaModu) -> int:
    return SIRA.index(mod)


def satir_hashi(satir: dict[str, Any], onceki_hash: str) -> str:
    govde = {k: v for k, v in satir.items() if k not in HASH_DISI}
    return nesne_hash({"govde": govde, "onceki_hash": onceki_hash})


@dataclass
class ModKaydi:
    """Mod geçmişi. Güncel mod son satırın `nereye`si; boşsa DISABLED."""

    gecmis: list[dict[str, Any]] = field(default_factory=list)
    bozuk: str = ""
    """Zincir doğrulanamadıysa sebebi. Doluysa mod DISABLED okunur (fail closed)."""

    @property
    def mod(self) -> CalismaModu:
        if self.bozuk or not self.gecmis:
            return CalismaModu.DISABLED
        return CalismaModu(self.gecmis[-1]["nereye"])

    @property
    def son_hash(self) -> str:
        return self.gecmis[-1]["satir_hash"] if self.gecmis else KOK_HASH

    @property
    def son_onay(self) -> dict[str, Any] | None:
        """Güncel LIVE modunu açan onay satırı; mod LIVE değilse `None`."""
        if self.mod is not CalismaModu.LIVE:
            return None
        return self.gecmis[-1]

    def sozluk(self) -> dict[str, Any]:
        return {
            "mod": str(self.mod),
            "bozuk": self.bozuk,
            "gecmis": self.gecmis,
        }

    @classmethod
    def yukle(cls, kayit: dict[str, Any]) -> ModKaydi:
        gecmis = list(kayit.get("gecmis", []))
        onceki = KOK_HASH
        for i, satir in enumerate(gecmis):
            if satir.get("onceki_hash") != onceki:
                return cls(gecmis, bozuk=f"satır {i}: onceki_hash zincire uymuyor")
            if satir.get("satir_hash") != satir_hashi(satir, onceki):
                return cls(gecmis, bozuk=f"satır {i}: satir_hash içerikle uyuşmuyor")
            try:
                CalismaModu(satir["nereye"])
                CalismaModu(satir["nereden"])
            except (KeyError, ValueError):
                return cls(gecmis, bozuk=f"satır {i}: bilinmeyen mod")
            onceki = satir["satir_hash"]
        return cls(gecmis)


class ModDefteri:
    """Mod kaydının diskteki hâli ve geçişlerin tek yazıcısı."""

    def __init__(self, yol: str | Path = VARSAYILAN_YOL, *, audit: Defter | None = None) -> None:
        self.yol = Path(yol)
        self.audit = audit

    def oku(self) -> ModKaydi:
        if not self.yol.is_file():
            return ModKaydi()
        try:
            kayit = json.loads(self.yol.read_text(encoding="utf-8"))
        except (OSError, ValueError) as hata:
            return ModKaydi(bozuk=f"okunamadı: {hata}")
        return ModKaydi.yukle(kayit)

    def mod(self) -> CalismaModu:
        return self.oku().mod

    def _yaz(self, kayit: ModKaydi, satir: dict[str, Any]) -> dict[str, Any]:
        if kayit.bozuk:
            raise ModHatasi(
                f"mod kaydı bozuk ({kayit.bozuk}); yeni geçiş yazılmaz. Kayıt incelenmeden "
                f"düzeltilemez — bozuk kayıt DISABLED okunuyor (fail closed)."
            )
        satir = dict(satir)
        satir["onceki_hash"] = kayit.son_hash
        satir["satir_hash"] = satir_hashi(satir, kayit.son_hash)
        if self.audit is not None:
            satir["audit_hash"] = self.audit.yaz(
                Olay(
                    tur=OlayTuru.EXECUTION,
                    zaman_ms=int(satir["zaman_ms"]),
                    sembol="",
                    govde={"olay": "mod_gecisi", **{k: v for k, v in satir.items()
                                                    if k != "audit_hash"}},
                    durum={},
                )
            )
        kayit.gecmis.append(satir)
        self.yol.parent.mkdir(parents=True, exist_ok=True)
        gecici = self.yol.with_suffix(".tmp")
        gecici.write_text(
            json.dumps({"surum": 1, "gecmis": kayit.gecmis}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        gecici.replace(self.yol)
        return satir

    def yukselt(
        self,
        hedef: CalismaModu,
        *,
        kapi_raporu: dict[str, Any],
        not_metni: str = "",
    ) -> dict[str, Any]:
        """Bir adım yukarı. `kapi_raporu` hedef modun kontrol listesinin çıktısıdır.

        `LIVE` bu yoldan açılamaz (`OnayGerekli`). Rapor `gecti=False` ise geçiş yazılmaz
        ve eksik kontroller hata metninde listelenir.
        """
        kayit = self.oku()
        mevcut = kayit.mod
        if hedef is CalismaModu.LIVE:
            raise OnayGerekli(
                "LIVE'a geçiş yalnızca elle onayla: `sq execution onayla` (K-114, K-010)"
            )
        if sira(hedef) != sira(mevcut) + 1:
            raise ModHatasi(
                f"yukarı geçiş yalnızca bir adım: {mevcut} → {hedef} yasak "
                f"(sıradaki: {SIRA[sira(mevcut) + 1] if sira(mevcut) + 1 < len(SIRA) else '—'})"
            )
        if kapi_raporu.get("hedef") != str(hedef):
            raise ModHatasi(
                f"kapı raporu başka bir mod için: {kapi_raporu.get('hedef')} ≠ {hedef}"
            )
        if not kapi_raporu.get("gecti"):
            eksik = [k["ad"] for k in kapi_raporu.get("kontroller", []) if not k.get("gecti")]
            raise ModHatasi(f"{hedef} kapısı geçilmedi; eksik: {', '.join(eksik) or '?'}")
        return self._yaz(
            kayit,
            {
                "nereden": str(mevcut),
                "nereye": str(hedef),
                "yon": "yukari",
                "zaman_ms": simdi_ms(),
                "zaman_utc": utc_str(simdi_ms()),
                "kapi_hash": kapi_raporu.get("hash", ""),
                "not": not_metni,
            },
        )

    def indir(self, hedef: CalismaModu, *, sebep: str) -> dict[str, Any] | None:
        """Herhangi bir alt moda iner. Onay istemez (K-050: riski azaltan otomatik).

        Mevcut mod zaten hedefte ya da altındaysa hiçbir şey yazılmaz ve `None` döner.
        Bozuk bir kayıtta da `None`: bozuk kayıt zaten DISABLED okunuyor.
        """
        if len(sebep.strip()) < 5:
            raise ModHatasi("mod indirme bir sebep ister (≥5 karakter)")
        kayit = self.oku()
        if kayit.bozuk or sira(hedef) >= sira(kayit.mod):
            return None
        return self._yaz(
            kayit,
            {
                "nereden": str(kayit.mod),
                "nereye": str(hedef),
                "yon": "asagi",
                "zaman_ms": simdi_ms(),
                "zaman_utc": utc_str(simdi_ms()),
                "sebep": sebep.strip(),
            },
        )

    def _canli_onay_yaz(
        self,
        *,
        kapi_raporu: dict[str, Any],
        gorulen_hash: str,
        not_metni: str,
        onaylayan: str,
    ) -> dict[str, Any]:
        """`canli_onayla`nın yazım yarısı. Doğrudan çağrılmaz."""
        kayit = self.oku()
        if kayit.mod is not CalismaModu.LIVE_PENDING_APPROVAL:
            raise ModHatasi(
                f"elle onay yalnızca LIVE_PENDING_APPROVAL'dan verilir; mevcut: {kayit.mod}"
            )
        metin = not_metni.strip()
        if len(metin) < ASGARI_ONAY_NOTU:
            raise ModHatasi(
                f"canlı onay bir gerekçe ister (≥{ASGARI_ONAY_NOTU} karakter): gerçek parayı "
                f"açan kararın tek yazılı kaydı bu not"
            )
        if kapi_raporu.get("hedef") != str(CalismaModu.LIVE) or not kapi_raporu.get("gecti"):
            raise ModHatasi("LIVE kapısı onay anında yeniden çalıştı ve geçmedi; onay yok")
        if kapi_raporu.get("hash") != gorulen_hash:
            raise ModHatasi(
                "onaylanan rapor ile onay anındaki rapor farklı (hash tutmuyor): arada bir "
                "şey değişti. Raporu yeniden oku, yeniden onayla."
            )
        return self._yaz(
            kayit,
            {
                "nereden": str(CalismaModu.LIVE_PENDING_APPROVAL),
                "nereye": str(CalismaModu.LIVE),
                "yon": "yukari",
                "zaman_ms": simdi_ms(),
                "zaman_utc": utc_str(simdi_ms()),
                "kapi_hash": gorulen_hash,
                "not": metin,
                "onaylayan": onaylayan,
                "strateji": kapi_raporu.get("strateji", ""),
                "kademe": kapi_raporu.get("kademe"),
                "sermaye_usdt": kapi_raporu.get("sermaye_usdt"),
            },
        )


def canli_onayla(
    defter: ModDefteri,
    *,
    kapi_raporu: dict[str, Any],
    gorulen_hash: str,
    not_metni: str,
    onaylayan: str,
) -> dict[str, Any]:
    """`LIVE_PENDING_APPROVAL → LIVE`. **Yalnızca `cli/execution.py` çağırır** (AST testi).

    `kapi_raporu` onay anında **yeniden** üretilmiş rapordur; `gorulen_hash` insanın
    okuyup onayladığı raporun hash'i. İkisi aynı değilse onay yok.
    """
    return defter._canli_onay_yaz(
        kapi_raporu=kapi_raporu,
        gorulen_hash=gorulen_hash,
        not_metni=not_metni,
        onaylayan=onaylayan,
    )


__all__ = [
    "ASGARI_ONAY_NOTU",
    "SIRA",
    "VARSAYILAN_YOL",
    "CalismaModu",
    "ModDefteri",
    "ModHatasi",
    "ModKaydi",
    "OnayGerekli",
    "canli_onayla",
    "sira",
]
