"""Aktif bot risk kuralları: boyut, kaldıraç tavanı, kayıp freni. (K-134)

Ağırlık = pozisyon notional'ı / özkaynak (işaretli). Canlı döngü ve backtest aynı
`agirlik_adimi` fonksiyonunu çağırır; iki yolun işlem sayısı bu yüzden aynıdır.

Kurallar:
- **Boyut yalnız girişte belirlenir.** Yön değişmedikçe mevcut pozisyona dokunulmaz
  (sürekli yeniden boyutlandırma maliyeti yer, işlem sayısını anlamsız şişirir).
- Giriş ağırlığı: `islem_riski / (atr_carpan × ATR/fiyat)` — `atr_carpan × ATR`'lik aleyhte
  hareket özkaynağın `islem_riski` kadarını kaybettirir; `sembol_kaldirac` ile tavanlı.
- Toplam brüt ağırlık `toplam_kaldirac`ı aşamaz; aşarsa yeni girişler sığacak kadar küçülür.
- **Fren (K-050 asimetrisi):** gün başına göre `gunluk_kayip` ya da hafta başına göre
  `haftalik_kayip` kadar düşüşte bütün pozisyonlar kapanır ve gün/hafta dönene kadar yeni
  giriş yok. Fren yalnız riski azaltır; kendiliğinden gevşeyen tek şey takvimdir.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

#: Bu kadar küçük ağırlık farkı "işlem" sayılmaz (kayan nokta ve kırıntı).
ESIK: float = 1e-9


@dataclass(frozen=True)
class RiskAyari:
    islem_riski: float = 0.01
    atr_carpan: float = 2.0
    sembol_kaldirac: float = 0.3
    toplam_kaldirac: float = 1.0
    gunluk_kayip: float = 0.03
    haftalik_kayip: float = 0.08

    def __post_init__(self) -> None:
        for ad in ("islem_riski", "atr_carpan", "sembol_kaldirac", "toplam_kaldirac"):
            if not getattr(self, ad) > 0:
                raise ValueError(f"{ad} pozitif olmalı")
        for ad in ("gunluk_kayip", "haftalik_kayip"):
            if not 0 < getattr(self, ad) < 1:
                raise ValueError(f"{ad} (0, 1) aralığında olmalı")
        if self.sembol_kaldirac > self.toplam_kaldirac:
            raise ValueError("sembol_kaldirac toplam_kaldirac'tan büyük olamaz")

    @classmethod
    def sozlukten(cls, d: dict[str, Any]) -> RiskAyari:
        return cls(**{k: float(v) for k, v in d.items() if not k.startswith("_")})


def giris_agirligi(yon: float, atr_oran: float, ayar: RiskAyari) -> float:
    """Yeni pozisyonun işaretli ağırlığı. ATR ölçülemiyorsa giriş yok."""
    if yon == 0 or not atr_oran > 0:
        return 0.0
    return yon * min(ayar.islem_riski / (ayar.atr_carpan * atr_oran), ayar.sembol_kaldirac)


def agirlik_adimi(
    onceki: dict[str, float],
    yonler: dict[str, float],
    atr_oranlari: dict[str, float],
    ayar: RiskAyari,
    *,
    fren: bool,
) -> dict[str, float]:
    """Bir bar kapanışında hedef ağırlıklar.

    `yonler`de olmayan sembol (veri bayat/yok) için önceki ağırlık aynen kalır: engelleyen
    katman işlem yaptırmaz (K-037). Fren açıkken hepsi 0.
    """
    if fren:
        return {s: 0.0 for s in set(onceki) | set(yonler)}
    hedef: dict[str, float] = dict(onceki)
    yeni: dict[str, float] = {}
    for s, yon in yonler.items():
        w0 = onceki.get(s, 0.0)
        if yon == 0:
            hedef[s] = 0.0
        elif abs(w0) > ESIK and (w0 > 0) == (yon > 0):
            hedef[s] = w0
        else:
            hedef[s] = 0.0
            yeni[s] = giris_agirligi(yon, atr_oranlari.get(s, 0.0), ayar)
    mevcut = sum(abs(w) for w in hedef.values())
    talep = sum(abs(w) for w in yeni.values())
    bos = max(ayar.toplam_kaldirac - mevcut, 0.0)
    olcek = 1.0 if talep <= bos else (bos / talep if talep > 0 else 0.0)
    for s, w in yeni.items():
        hedef[s] = w * olcek
    return hedef


@dataclass
class FrenDurumu:
    """Gün ve hafta başı özkaynağı; `guncelle` her turda çağrılır."""

    gun: str = ""
    gun_basi: float = 0.0
    hafta: str = ""
    hafta_basi: float = 0.0

    def guncelle(self, ozkaynak: float, zaman_ms: int, ayar: RiskAyari) -> str | None:
        """Takvim döndüyse başlangıçları yeniler; fren sebebini ya da None döndürür."""
        an = dt.datetime.fromtimestamp(zaman_ms / 1000, tz=dt.UTC)
        gun = an.strftime("%Y-%m-%d")
        yil, hafta_no, _ = an.isocalendar()
        hafta = f"{yil}-W{hafta_no:02d}"
        if gun != self.gun:
            self.gun, self.gun_basi = gun, ozkaynak
        if hafta != self.hafta:
            self.hafta, self.hafta_basi = hafta, ozkaynak
        if ozkaynak < self.hafta_basi * (1.0 - ayar.haftalik_kayip):
            return "haftalik_kayip"
        if ozkaynak < self.gun_basi * (1.0 - ayar.gunluk_kayip):
            return "gunluk_kayip"
        return None

    def sozluk(self) -> dict[str, Any]:
        return {"gun": self.gun, "gun_basi": self.gun_basi,
                "hafta": self.hafta, "hafta_basi": self.hafta_basi}

    @classmethod
    def sozlukten(cls, d: dict[str, Any]) -> FrenDurumu:
        return cls(str(d.get("gun", "")), float(d.get("gun_basi", 0.0)),
                   str(d.get("hafta", "")), float(d.get("hafta_basi", 0.0)))
