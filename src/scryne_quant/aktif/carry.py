"""Funding carry demo botu (K-139): spot long + USDT-M perp short, simüle iki bacak.

Kural backtest'le (`tools/carry_arastirma.py`, ön kayıt `2026-09-23-carry-onkayit.md`) aynı:
günlük karar (00:00 UTC sonrası ilk tur), sinyal = son 3 günün funding toplamı / 3 × 365,
giriş ≥ %20, çıkış < %5, en fazla 8 pozisyon, notional = özkaynak / (1,5 × 8), spot 30 günlük
medyan hacim ≥ 20 milyon USDT. Canlı sapma: 3 günlük geçmiş yalnız anlık yıllık funding'i
≥ %10 olan perp'ler için çekilir (API yükü); geri kalanı zaten girişe aday olamaz.

Muhasebe (nakit tabanlı, notional sabit): giriş → nakit −= spot_adet × spot_dolum + ücret;
perp short'un gerçekleşmemiş K/Z'si `perp_adet × (perp_giris − perp_fiyat)`. Funding her
olayda nakde işlenir (`perp_adet × mark × oran`; pozitif oran short'a öder). Fiyat yönü
iki bacakta birbirini götürür; kalan premium farkı ve funding'dir.

Hiçbir gerçek emir yok; yalnız Binance public uçları okunur.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import statistics
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Protocol

from scryne_quant.aktif.araci import AraciHatasi, Dolum
from scryne_quant.aktif.defter import Defter
from scryne_quant.common.zaman import simdi_ms

GUN_MS: Final = 86_400_000
SAAT_MS: Final = 3_600_000
FAPI: Final = "https://fapi.binance.com"
SPOT: Final = "https://data-api.binance.vision"


@dataclass(frozen=True)
class CarryAyari:
    giris_yillik: float = 0.20
    cikis_yillik: float = 0.05
    azami_poz: int = 8
    sermaye_carpani: float = 1.5
    asgari_hacim: float = 20e6
    sinyal_gun: int = 3
    on_filtre_yillik: float = 0.10
    spot_ucret_bps: float = 10.0
    perp_ucret_bps: float = 5.0
    kayma_bps: float = 2.0
    tasfiye_sicrama: float = 0.45
    tasfiye_kayip: float = 0.06


class CarryVeri(Protocol):
    def perp_ozet(self) -> dict[str, dict[str, float]]: ...
    def funding(self, sembol: str, bas_ms: int) -> list[tuple[int, float, float]]: ...
    def spot_hacim_medyan(self, sembol: str, gun: int) -> float | None: ...
    def spot_fiyat(self, sembol: str) -> float: ...
    def perp_fiyat(self, sembol: str) -> float: ...


class BinanceCarryVeri:
    """Public uçlar: fapi (perp) + data-api (spot). Anahtar yok, emir yok."""

    def __init__(self) -> None:
        import requests

        from scryne_quant.exchange.binance import ipv4_zorla

        ipv4_zorla()
        self._s = requests.Session()
        self._spot_semboller: set[str] | None = None

    def _al(self, url: str, **params: Any) -> Any:
        son: Exception | None = None
        for deneme in range(4):
            try:
                r = self._s.get(url, params=params, timeout=15)
                r.raise_for_status()
                return r.json()
            except Exception as hata:  # noqa: BLE001 — okuma: yeniden denenir
                son = hata
                time.sleep(1.5 * (deneme + 1))
        raise AraciHatasi(f"{url}: {son}")

    def perp_ozet(self) -> dict[str, dict[str, float]]:
        """USDT perp'ler: anlık funding oranı ve mark fiyatı (spot eşi olanlar)."""
        if self._spot_semboller is None:
            bilgi = self._al(f"{SPOT}/api/v3/exchangeInfo", permissions="SPOT")
            self._spot_semboller = {s["symbol"] for s in bilgi["symbols"]
                                    if s.get("status") == "TRADING"}
        cikti = {}
        for p in self._al(f"{FAPI}/fapi/v1/premiumIndex"):
            s = p["symbol"]
            if s.endswith("USDT") and s in self._spot_semboller:
                cikti[s] = {"oran": float(p["lastFundingRate"] or 0.0),
                            "mark": float(p["markPrice"]), "sonraki_ms": int(p["nextFundingTime"])}
        return cikti

    def funding(self, sembol: str, bas_ms: int) -> list[tuple[int, float, float]]:
        ham = self._al(f"{FAPI}/fapi/v1/fundingRate", symbol=sembol, startTime=bas_ms, limit=1000)
        return [(int(r["fundingTime"]), float(r["fundingRate"]), float(r.get("markPrice") or 0.0))
                for r in ham]

    def spot_hacim_medyan(self, sembol: str, gun: int) -> float | None:
        ham = self._al(f"{SPOT}/api/v3/klines", symbol=sembol, interval="1d", limit=gun + 1)
        kapanmis = [float(k[7]) for k in ham[:-1]]  # son (açık) gün hariç
        return statistics.median(kapanmis) if len(kapanmis) >= 20 else None

    def spot_fiyat(self, sembol: str) -> float:
        return float(self._al(f"{SPOT}/api/v3/ticker/price", symbol=sembol)["price"])

    def perp_fiyat(self, sembol: str) -> float:
        return float(self._al(f"{FAPI}/fapi/v1/premiumIndex", symbol=sembol)["markPrice"])


class CarryHesap:
    """İki bacaklı simüle hesap; durum `paper.json` (aktif pano uyumlu: `adet` = spot adedi)."""

    def __init__(self, dizin: Path, sermaye: float) -> None:
        self._yol = Path(dizin) / "paper.json"
        if self._yol.is_file():
            d = json.loads(self._yol.read_text(encoding="utf-8"))
            self.nakit = float(d["nakit"])
            self.poz: dict[str, dict[str, float]] = d.get("ek", {}).get("carry", {})
            self.ek: dict[str, Any] = d.get("ek", {})
        else:
            self.nakit, self.poz, self.ek = float(sermaye), {}, {}
            self.yaz()

    def yaz(self) -> None:
        self.ek["carry"] = self.poz
        d = {"nakit": self.nakit, "adet": {s: p["spot_adet"] for s, p in self.poz.items()},
             "doviz": {}, "ek": self.ek}
        self._yol.parent.mkdir(parents=True, exist_ok=True)
        gecici = self._yol.with_suffix(".tmp")
        gecici.write_text(json.dumps(d, indent=1), encoding="utf-8")
        os.replace(gecici, self._yol)

    def deger(self, spot: dict[str, float], perp: dict[str, float]) -> float:
        toplam = self.nakit
        for s, p in self.poz.items():
            toplam += p["spot_adet"] * spot[s] + p["perp_adet"] * (p["perp_giris"] - perp[s])
        return toplam


def _gun(ms: int) -> int:
    return ms // GUN_MS


def carry_tur(veri: CarryVeri, hesap: CarryHesap, defter: Defter, ayar: CarryAyari,
              simdi: int) -> dict[str, Any]:
    """Bir saatlik tur: funding tahakkuku, tasfiye kontrolü, (gün döndüyse) seçim, değerleme."""
    maliyet_spot = (ayar.spot_ucret_bps + ayar.kayma_bps) / 1e4
    maliyet_perp = (ayar.perp_ucret_bps + ayar.kayma_bps) / 1e4
    olaylar: list[str] = []

    # 1) Funding tahakkuku: tutulan her sembolde son işlenenden sonraki olaylar.
    for s, p in hesap.poz.items():
        for zaman, oran, mark in veri.funding(s, int(p["son_funding_ms"]) + 1):
            if zaman > simdi:
                continue
            tutar = p["perp_adet"] * (mark or p["perp_giris"]) * oran
            hesap.nakit += tutar
            p["funding_toplam"] = p.get("funding_toplam", 0.0) + tutar
            p["son_funding_ms"] = zaman
    hesap.yaz()

    spot = {s: veri.spot_fiyat(s) for s in hesap.poz}
    perp = {s: veri.perp_fiyat(s) for s in hesap.poz}

    # 2) Tasfiye vekili: perp fiyatı son günlük dengelemeden bu yana ≥ %45 yükseldiyse.
    for s in list(hesap.poz):
        p = hesap.poz[s]
        if perp[s] / p["dengeleme"] - 1 >= ayar.tasfiye_sicrama:
            _kapat(hesap, defter, s, spot[s], perp[s], maliyet_spot, maliyet_perp, simdi, "tasfiye")
            hesap.nakit -= p["notional"] * ayar.tasfiye_kayip
            olaylar.append(f"tasfiye {s}")
            defter.olay(simdi, "tasfiye", {"sembol": s})

    # 3) Günlük karar (00:00 UTC'den sonraki ilk tur).
    if hesap.ek.get("son_karar_gun") != _gun(simdi):
        ozk = hesap.deger(spot, perp)
        ozet = veri.perp_ozet()
        bas = (_gun(simdi) - ayar.sinyal_gun) * GUN_MS
        son = _gun(simdi) * GUN_MS
        sinyal: dict[str, float] = {}
        adaylar = [s for s, o in ozet.items()
                   if o["oran"] * 3 * 365 >= ayar.on_filtre_yillik or s in hesap.poz]
        for s in adaylar:
            olay = [r for r in veri.funding(s, bas) if bas <= r[0] < son]
            if olay:
                sinyal[s] = sum(r[1] for r in olay) / ayar.sinyal_gun * 365
        # Çıkışlar
        for s in list(hesap.poz):
            if sinyal.get(s, 0.0) < ayar.cikis_yillik:
                sp, pp = veri.spot_fiyat(s), veri.perp_fiyat(s)
                _kapat(hesap, defter, s, sp, pp, maliyet_spot, maliyet_perp, simdi, "cikis")
                olaylar.append(f"çıkış {s} ({sinyal.get(s, 0.0):.1%})")
        # Girişler
        bos = ayar.azami_poz - len(hesap.poz)
        for s, y in sorted(sinyal.items(), key=lambda x: -x[1]):
            if bos <= 0 or y < ayar.giris_yillik or s in hesap.poz:
                continue
            hacim = veri.spot_hacim_medyan(s, 30)
            if hacim is None or hacim < ayar.asgari_hacim:
                continue
            gecmis = veri.funding(s, simdi - 31 * GUN_MS)
            if len({_gun(r[0]) for r in gecmis}) < 30:
                continue
            sp, pp = veri.spot_fiyat(s), veri.perp_fiyat(s)
            n = ozk / (ayar.sermaye_carpani * ayar.azami_poz)
            _ac(hesap, defter, s, n, sp, pp, maliyet_spot, maliyet_perp, simdi,
                max(r[0] for r in gecmis))
            olaylar.append(f"giriş {s} ({y:.1%})")
            bos -= 1
        # Günlük dengeleme referansı
        for s, p in hesap.poz.items():
            p["dengeleme"] = veri.perp_fiyat(s)
        hesap.ek["son_karar_gun"] = _gun(simdi)
        hesap.ek["son_sinyal"] = {s: round(v, 4) for s, v in
                                  sorted(sinyal.items(), key=lambda x: -x[1])[:10]}
        hesap.yaz()
        spot = {s: veri.spot_fiyat(s) for s in hesap.poz}
        perp = {s: veri.perp_fiyat(s) for s in hesap.poz}

    deger = hesap.deger(spot, perp)
    defter.ozkaynak(simdi, deger)
    return {"zaman_ms": simdi, "ozkaynak": deger, "poz": len(hesap.poz), "olaylar": olaylar}


def _ac(hesap: CarryHesap, defter: Defter, s: str, n: float, sp: float, pp: float,
        ms: float, mp: float, zaman: int, son_funding: int) -> None:
    # Dolum referans fiyattan; kayma ve ücret notional üzerinden bps (backtest'le aynı).
    spot_dolum, perp_dolum = sp, pp
    spot_adet = n / spot_dolum
    perp_adet = n / perp_dolum
    ucret = n * (ms + mp)
    hesap.nakit -= spot_adet * spot_dolum + ucret
    hesap.poz[s] = {"notional": n, "spot_adet": spot_adet, "perp_adet": perp_adet,
                    "spot_giris": spot_dolum, "perp_giris": perp_dolum, "dengeleme": perp_dolum,
                    "son_funding_ms": son_funding, "funding_toplam": 0.0, "giris_ms": zaman}
    defter.islem(zaman, Dolum(s, spot_adet, spot_dolum, n * ms), n, "giris")
    defter.islem(zaman, Dolum(s, -perp_adet, perp_dolum, n * mp), -n, "giris_perp")
    hesap.yaz()


def _kapat(hesap: CarryHesap, defter: Defter, s: str, sp: float, pp: float,
           ms: float, mp: float, zaman: int, neden: str) -> None:
    p = hesap.poz.pop(s)
    ucret = p["notional"] * (ms + mp)
    hesap.nakit += p["spot_adet"] * sp + p["perp_adet"] * (p["perp_giris"] - pp) - ucret
    defter.islem(zaman, Dolum(s, -p["spot_adet"], sp, p["notional"] * ms), -p["notional"], neden)
    defter.islem(zaman, Dolum(s, p["perp_adet"], pp, p["notional"] * mp), p["notional"],
                 neden + "_perp")
    hesap.yaz()


def calistir_carry(dizin: Path, sermaye: float, ayar: CarryAyari | None = None,
                   veri: CarryVeri | None = None, yaz: Any = print) -> None:
    """Saat başına hizalı döngü; `dizin/dur` görülünce biter (aktif döngüyle aynı sözleşme)."""
    from scryne_quant.live.kilit import KosuKilidi

    ayar = ayar or CarryAyari()
    veri = veri or BinanceCarryVeri()
    dizin.mkdir(parents=True, exist_ok=True)
    kilit = KosuKilidi(dizin / "aktif")
    kilit.al()
    defter = Defter(dizin)
    hesap = CarryHesap(dizin, sermaye)
    dur = dizin / "dur"
    try:
        defter.olay(simdi_ms(), "basla", {"strateji": "carry"})
        while not dur.exists():
            try:
                r = carry_tur(veri, hesap, defter, ayar, simdi_ms())
                yaz(f"{dt.datetime.now(dt.UTC):%H:%M} özkaynak {r['ozkaynak']:.2f} "
                    f"poz {r['poz']} {'; '.join(r['olaylar'])}")
            except Exception as hata:  # noqa: BLE001 — tur hatası döngüyü öldürmez
                defter.olay(simdi_ms(), "tur_hatasi",
                            {"hata": repr(hata), "iz": traceback.format_exc()[-2000:]})
                yaz(f"tur hatası: {hata!r}")
            sonraki = (simdi_ms() // SAAT_MS + 1) * SAAT_MS + 20_000
            while not dur.exists() and simdi_ms() < sonraki:
                time.sleep(min(5.0, max(0.5, (sonraki - simdi_ms()) / 1000)))
        defter.olay(simdi_ms(), "dur", {})
        dur.unlink(missing_ok=True)
    finally:
        defter.kapat()
        kilit.kapat()
