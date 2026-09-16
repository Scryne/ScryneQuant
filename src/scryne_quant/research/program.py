"""Araştırma programı kaydı ve arama bütçesi. (K-051, K-049, Faz 11)

**Kapatmaya çalıştığı boşluk.** K-044 ölçtü: her yeni çekiliş `oos_sharpe` kapısını
yükseltiyor. Yani büyük bir arama programı, bulduğu şeyi geçiremeyeceği bir duvarı kendisi
örebilir — ve bunu ancak sonunda öğrenir. K-051'in cevabı yasak değil **fiyat etiketi**:
program açılırken gerekçesi, kaynağının neden farklı olduğu (**ölçüyle**), azami çekiliş
sayısı ve durma kuralı deftere yazılır.

## Bu defter neyi zorluyor

1. **Bütçe aşılamaz.** Program `azami_cekilis` kadar hipotez taşıyabilir; aşmak yeni bir
   program kaydı ve yeni bir gerekçe ister. Bütçeyi sonuçları gördükten sonra büyütmek,
   K-042'nin durma kuralının yasakladığı şeyin ta kendisi.
2. **Kaynak farkı iddia değil ölçüdür.** K-045 tek sembollü yönlü aramayı kapattı ve tek
   istisna *"ölçüyle gerekçelendirilmiş belirgin biçimde farklı bir bilgi kaynağı"*.
   `kaynak_olcumu` boş bırakılamaz: "cross-sectional farklıdır" bir cümle, "evren geneli
   sıralama ile tek sembol getirisi arasındaki korelasyon 0,18" bir ölçü.
3. **Duvar önceden görünür.** `esik_tahmini` programın kendi dikeceği duvarın mertebe
   tahmini. **Kapı değildir** — kapı bitiminde `sq lab coklu-test` ile ölçülür (K-044);
   amacı programın maliyetini baştan göstermek.

## Defter neden `docs/` altında

`docs/Hipotez-Defteri.jsonl` ile aynı gerekçe: `runs/` `.gitignore`'da ve **iz bırakmadan
silinebilen bir defter, defter değildir.** Program kaydı bir çalışma çıktısı değil, bir
araştırma taahhüdü.

## LLM türetimi ve `leak_riski` (K-049)

Aynı dosyada duruyorlar çünkü ikisi de *"bu sonucu üretirken hangi bilgiye baktık"*
sorusunun kaydı. K-049/4'ün adlandırdığı risk şu: 2026'da eğitilmiş bir model 2023
haberini okuduğunda o haberden **sonra ne olduğunu biliyor**. Sızıntı veride değil
ağırlıklarda olduğu için look-ahead testi onu yakalayamaz — kodda çiğnenen tek bir satır
yok. Bu yüzden kural veriden değil **beyandan** gelir: türetimin kapsadığı dönem modelin
eğitim kesiminden önceye uzanıyorsa o türetim `leak_riski` taşır ve promotion'un mutlak
engelidir (K-054).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from scryne_quant.common.hash import nesne_hash
from scryne_quant.common.zaman import simdi_ms, utc_str

VARSAYILAN_YOL: Final = Path("docs/Arastirma-Programlari.jsonl")

#: Program adı bir **kod**: defterde gruplanabilir, testte eşitlenebilir, dilden bağımsız.
#: `Sinyal.reason` ile aynı kalıp ve aynı gerekçe.
AD_DESENI: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]{2,47}$")

#: Gerekçe ve kaynak farkı için asgari uzunluk. Hipotez defterinin 20 karakterinden uzun:
#: bir program onlarca çekilişi kapsıyor ve bir cümlelik gerekçe onu taşımaz.
ASGARI_METIN: Final = 60


class ProgramHatasi(ValueError):
    """Program kaydı kuralı ihlal edildi."""


@dataclass(frozen=True, slots=True)
class ProgramKaydi:
    """Bir araştırma programının ön kaydı. (K-051/2)"""

    ad: str
    gerekce: str
    kaynak_farki: str
    """Bilgi kaynağının neden **belirgin biçimde farklı** olduğu (K-045'in istisna şartı)."""

    kaynak_olcumu: dict[str, Any]
    """Farkın **sayısal** dayanağı. Boş olamaz: iddia ölçü yerine geçmez."""

    azami_cekilis: int
    durma_kurali: str
    esik_tahmini: dict[str, Any]
    """Bütçe dahil edildiğinde eşiğin nereye çıkacağının mertebe tahmini (DSR/Bonferroni)."""

    acildi_ms: int = field(default_factory=simdi_ms)

    def __post_init__(self) -> None:
        if not AD_DESENI.fullmatch(self.ad):
            raise ProgramHatasi(
                f"program adı bir kod olmalı (a-z, 0-9, _; 3-48 karakter): {self.ad!r}"
            )
        for alan, metin in (("gerekce", self.gerekce), ("kaynak_farki", self.kaynak_farki)):
            if len(metin.strip()) < ASGARI_METIN:
                raise ProgramHatasi(
                    f"{alan} en az {ASGARI_METIN} karakter olmalı: bir program onlarca "
                    "çekilişi kapsıyor ve tek cümlelik bir gerekçe onu taşımaz (K-051/2)"
                )
        if not self.kaynak_olcumu:
            raise ProgramHatasi(
                "kaynak_olcumu boş olamaz: K-045'in istisnası 'ölçüyle gerekçelendirilmiş' "
                "diyor. 'Bu kaynak farklıdır' bir iddia, bir ölçü değil"
            )
        if self.azami_cekilis < 1:
            raise ProgramHatasi(f"azami_cekilis ≥ 1 olmalı: {self.azami_cekilis}")
        if len(self.durma_kurali.strip()) < 20:
            raise ProgramHatasi(
                "durma kuralı yazılmalı (≥20 karakter): sonunda durulacağı söylenmeyen "
                "bir arama, sonucu görene kadar süren bir aramadır (K-042)"
            )
        if not self.esik_tahmini:
            raise ProgramHatasi(
                "esik_tahmini boş olamaz: programın kendi dikeceği duvarı baştan görmesi "
                "K-051/3'ün amacı. Tahmin kapı değildir, ölçüm bitiminde yapılır"
            )

    @property
    def kimlik(self) -> str:
        """İçerik hash'i. Gerekçe metni **dahil değil** — aynı programı farklı kelimelerle
        anlatmak yeni bir program değildir; bütçeyi veya kaynağı değiştirmek yenidir."""
        return nesne_hash(
            {
                "ad": self.ad,
                "kaynak_olcumu": self.kaynak_olcumu,
                "azami_cekilis": self.azami_cekilis,
            }
        )

    def sozluk(self) -> dict[str, Any]:
        return {
            "kimlik": self.kimlik,
            "ad": self.ad,
            "gerekce": self.gerekce,
            "kaynak_farki": self.kaynak_farki,
            "kaynak_olcumu": self.kaynak_olcumu,
            "azami_cekilis": self.azami_cekilis,
            "durma_kurali": self.durma_kurali,
            "esik_tahmini": self.esik_tahmini,
            "acildi_ms": self.acildi_ms,
            "acildi_utc": utc_str(self.acildi_ms),
        }


@dataclass(frozen=True, slots=True)
class ProgramKapanisi:
    """Bir programın kapanış kaydı. Ayrı satır: defter append-only."""

    ad: str
    sonuc: str
    harcanan_cekilis: int
    kapandi_ms: int = field(default_factory=simdi_ms)

    def __post_init__(self) -> None:
        if len(self.sonuc.strip()) < 20:
            raise ProgramHatasi(
                "kapanış bir sonuç metni ister (≥20 karakter): ne bulunduğu yazılmadan "
                "kapanan program, sayacı harcamış ama hiçbir şey öğretmemiş olur"
            )

    def sozluk(self) -> dict[str, Any]:
        return {
            "tur": "kapanis",
            "ad": self.ad,
            "sonuc": self.sonuc,
            "harcanan_cekilis": self.harcanan_cekilis,
            "kapandi_ms": self.kapandi_ms,
            "kapandi_utc": utc_str(self.kapandi_ms),
        }


class ProgramDefteri:
    """Append-only araştırma programı kaydı (JSONL). Açılış ve kapanış ayrı satırlar."""

    __slots__ = ("yol",)

    def __init__(self, yol: str | Path = VARSAYILAN_YOL) -> None:
        self.yol = Path(yol)

    # ------------------------------------------------------------------ yazma

    def ac(self, kayit: ProgramKaydi) -> ProgramKaydi:
        """Programı açar. Aynı adla açık bir program varsa hata."""
        if self.acik(kayit.ad) is not None:
            raise ProgramHatasi(
                f"{kayit.ad!r} zaten açık. İkinci bir kayıt, bütçeyi sessizce ikiye "
                "katlamanın en kolay yolu olurdu (K-051/2)"
            )
        self._yaz({"tur": "acilis", **kayit.sozluk()})
        return kayit

    def kapat(self, ad: str, sonuc: str, harcanan_cekilis: int) -> ProgramKapanisi:
        if self.acik(ad) is None:
            raise ProgramHatasi(f"{ad!r} açık bir program değil; kapatılacak bir şey yok")
        kapanis = ProgramKapanisi(ad=ad, sonuc=sonuc, harcanan_cekilis=harcanan_cekilis)
        self._yaz(kapanis.sozluk())
        return kapanis

    def _yaz(self, govde: Mapping[str, Any]) -> None:
        self.yol.parent.mkdir(parents=True, exist_ok=True)
        satir = json.dumps(govde, ensure_ascii=False, sort_keys=True)
        with self.yol.open("a", encoding="utf-8", newline="\n") as dosya:
            dosya.write(satir + "\n")

    # ------------------------------------------------------------------ okuma

    def tumu(self) -> list[dict[str, Any]]:
        if not self.yol.exists():
            return []
        return [
            json.loads(s)
            for s in self.yol.read_text(encoding="utf-8").splitlines()
            if s.strip()
        ]

    def acik(self, ad: str) -> dict[str, Any] | None:
        """Bu ad için **açık** (kapatılmamış) program kaydı; yoksa `None`."""
        kayit: dict[str, Any] | None = None
        for satir in self.tumu():
            if satir.get("ad") != ad:
                continue
            if satir.get("tur") == "acilis":
                kayit = satir
            elif satir.get("tur") == "kapanis":
                kayit = None
        return kayit

    def acik_programlar(self) -> list[dict[str, Any]]:
        adlar = {s["ad"] for s in self.tumu() if "ad" in s}
        return [k for a in sorted(adlar) if (k := self.acik(a)) is not None]

    # ------------------------------------------------------------------ bütçe

    def harcanan(self, ad: str, hipotezler: list[Mapping[str, Any]]) -> int:
        """Bu programa yazılmış hipotez sayısı."""
        return sum(1 for h in hipotezler if h.get("program") == ad)

    def butce(self, ad: str, hipotezler: list[Mapping[str, Any]]) -> dict[str, Any]:
        kayit = self.acik(ad)
        if kayit is None:
            raise ProgramHatasi(f"{ad!r} açık bir program değil")
        harcanan = self.harcanan(ad, hipotezler)
        azami = int(kayit["azami_cekilis"])
        return {
            "ad": ad,
            "azami_cekilis": azami,
            "harcanan": harcanan,
            "kalan": azami - harcanan,
            "durma_kurali": kayit["durma_kurali"],
            "esik_tahmini": kayit["esik_tahmini"],
        }

    def dogrula_cekilis(self, ad: str, hipotezler: list[Mapping[str, Any]]) -> dict[str, Any]:
        """Bu programa **bir çekiliş daha** yazılabilir mi? (K-051/2)

        Program kaydı olmadan bir araştırma programı koşturulamaz; bütçesi dolmuş bir
        program da koşturulamaz. İkisi de sessiz geçilirse defter bir muhasebe aracı
        olmaktan çıkıp bir günlüğe döner.
        """
        if not ad:
            raise ProgramHatasi(
                "hipotez bir programa ait olmalı: program kaydı olmadan araştırma "
                "programı koşturulamaz (K-051/2)"
            )
        durum = self.butce(ad, hipotezler)
        if durum["kalan"] <= 0:
            raise ProgramHatasi(
                f"{ad!r}: arama bütçesi doldu ({durum['harcanan']}/{durum['azami_cekilis']}). "
                "Bütçeyi sonucu gördükten sonra büyütmek K-042'nin durma kuralının "
                "yasakladığı şeydir; yeni bir program kaydı ve yeni bir gerekçe gerekir"
            )
        return durum


# ------------------------------------------------------------------ LLM / leak


@dataclass(frozen=True, slots=True)
class LlmTuretimi:
    """Dondurulmuş bir LLM türetiminin kimliği ve sızıntı durumu. (K-049)"""

    model: str
    egitim_kesim_ms: int
    """Modelin eğitim verisinin kesim tarihi. **Beyandır**, ölçülemez — ve bu yüzden
    kayıtlı olmak zorunda: yazılmayan bir kesim tarihi, olmayan bir kesim tarihidir."""

    kapsam_baslangic_ms: int
    kapsam_bitis_ms: int
    """Türetimin **kapsadığı** dönem (üretildiği an değil)."""

    prompt_hash: str
    girdi_hash: str

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ProgramHatasi("LLM türetimi model kimliği taşımalı (K-049/5)")
        if self.kapsam_bitis_ms < self.kapsam_baslangic_ms:
            raise ProgramHatasi("kapsam bitişi başlangıcından önce olamaz")
        if not self.prompt_hash or not self.girdi_hash:
            raise ProgramHatasi(
                "LLM çıktısı prompt hash'i ve girdi hash'iyle **dondurulmuş** olmalı: "
                "backtest içinde hesaplanan bir LLM çıktısı K-009'u düşürür (K-049/5)"
            )

    @property
    def leak_riski(self) -> bool:
        """Türetim, modelin eğitim kesiminden **önceki** bir dönemi kapsıyor mu?

        Kapsıyorsa model o dönemden sonra ne olduğunu biliyor ve türetim bir tahmin değil
        bir hatırlamadır. Sızıntı ağırlıklarda olduğu için look-ahead testi yakalayamaz;
        engel bu yüzden beyana dayanır ve **mutlaktır** (K-049/4, K-054).
        """
        return self.kapsam_baslangic_ms < self.egitim_kesim_ms

    def sozluk(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "egitim_kesim_ms": self.egitim_kesim_ms,
            "egitim_kesim_utc": utc_str(self.egitim_kesim_ms),
            "kapsam_baslangic_ms": self.kapsam_baslangic_ms,
            "kapsam_bitis_ms": self.kapsam_bitis_ms,
            "prompt_hash": self.prompt_hash,
            "girdi_hash": self.girdi_hash,
            "leak_riski": self.leak_riski,
        }


def leak_riski_var_mi(turetimler: Mapping[str, Any] | list[LlmTuretimi] | None) -> bool:
    """Verilen türetimlerin herhangi biri sızıntı riski taşıyor mu."""
    if not turetimler:
        return False
    if isinstance(turetimler, Mapping):
        return bool(turetimler.get("leak_riski"))
    return any(t.leak_riski for t in turetimler)


__all__ = [
    "AD_DESENI",
    "ASGARI_METIN",
    "VARSAYILAN_YOL",
    "LlmTuretimi",
    "ProgramDefteri",
    "ProgramHatasi",
    "ProgramKapanisi",
    "ProgramKaydi",
    "leak_riski_var_mi",
]
