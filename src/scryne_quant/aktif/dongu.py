"""Aktif bot döngüsü: her bar kapanışında tek tur. (K-134)

Bir tur:
1. Özkaynak aracıdan okunur; fren durumu güncellenir.
2. Her sembol için kapanmış barlar → strateji yönü + ATR oranı. Veri bayatsa (piyasa
   kapalı, bağlantı) o sembol bu turda **işlem görmez** (engelleyen katman, K-037).
3. `risk.agirlik_adimi` hedef ağırlıkları verir; mevcut ağırlıklar aracının pozisyonundan
   okunur (durum tahmin edilmez).
4. Önce azaltan emirler (nakit/marjin açar), sonra artıranlar.

Hedef ile mevcut arasındaki fark `asgari_emir`in altındaysa emir yok (kırıntı).
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scryne_quant.aktif import strateji as strateji_mod
from scryne_quant.aktif.araci import Araci, AraciHatasi
from scryne_quant.aktif.defter import Defter
from scryne_quant.aktif.risk import ESIK, RiskAyari, agirlik_adimi
from scryne_quant.common.zaman import simdi_ms, timeframe_ms


@dataclass(frozen=True)
class HesapAyari:
    ad: str
    araci: str
    semboller: tuple[str, ...]
    timeframe: str
    strateji: str
    parametreler: dict[str, Any]
    risk: RiskAyari
    asgari_emir: float = 10.0
    bar_sayisi: int = 400
    ekstra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def sozlukten(cls, ad: str, d: dict[str, Any], risk: dict[str, Any]) -> HesapAyari:
        bilinen = {"araci", "semboller", "timeframe", "strateji", "parametreler", "risk",
                   "asgari_emir", "bar_sayisi"}
        return cls(
            ad=ad,
            araci=str(d["araci"]),
            semboller=tuple(d["semboller"]),
            timeframe=str(d["timeframe"]),
            strateji=str(d["strateji"]),
            parametreler=dict(d.get("parametreler", {})),
            risk=RiskAyari.sozlukten({**risk, **d.get("risk", {})}),
            asgari_emir=float(d.get("asgari_emir", 10.0)),
            bar_sayisi=int(d.get("bar_sayisi", 400)),
            ekstra={k: v for k, v in d.items() if k not in bilinen and not k.startswith("_")},
        )


def bayat_mi(son_acilis_ms: int, adim_ms: int, simdi: int) -> bool:
    """Son kapanmış bar, bir önceki bar kapanışından daha eskiyse veri bayattır."""
    return son_acilis_ms + 2 * adim_ms < simdi - adim_ms // 10


def tur(araci: Araci, ayar: HesapAyari, defter: Defter, simdi: int | None = None) -> dict[str, Any]:
    simdi = simdi_ms() if simdi is None else simdi
    adim = timeframe_ms(ayar.timeframe)
    ozk = araci.ozkaynak()
    fren_durum = defter.fren_oku()
    fren = fren_durum.guncelle(ozk, simdi, ayar.risk)
    defter.fren_yaz(fren_durum)
    if fren:
        defter.olay(simdi, "fren", {"sebep": fren, "ozkaynak": ozk})

    yonler: dict[str, float] = {}
    atr_oran: dict[str, float] = {}
    fiyatlar: dict[str, float] = {}
    atlanan: dict[str, str] = {}
    for s in ayar.semboller:
        try:
            df = araci.barlar(s, ayar.timeframe, ayar.bar_sayisi)
        except Exception as hata:  # noqa: BLE001 — sembol atlanır, tur sürer
            atlanan[s] = f"veri: {hata}"
            continue
        if len(df) < strateji_mod.ISINMA.get(ayar.strateji, 0):
            atlanan[s] = f"az bar ({len(df)})"
            continue
        if bayat_mi(int(df.index[-1]), adim, simdi):
            atlanan[s] = "bayat veri"
            continue
        yon = strateji_mod.yon_serisi(
            ayar.strateji, df, ayar.parametreler, yalniz_long=araci.yalniz_long
        )
        a = strateji_mod.atr(df).iloc[-1]
        c = float(df["close"].iloc[-1])
        yonler[s] = float(yon.iloc[-1])
        atr_oran[s] = float(a) / c if a == a and c > 0 else 0.0
        fiyatlar[s] = c

    pozlar = araci.pozisyonlar()
    onceki: dict[str, float] = {}
    for s, adet in pozlar.items():
        if s not in ayar.semboller:
            continue
        f = fiyatlar.get(s) or araci.fiyat(s)
        fiyatlar.setdefault(s, f)
        onceki[s] = adet * araci.birim_notional(s, f) / ozk
    hedef = agirlik_adimi(onceki, yonler, atr_oran, ayar.risk, fren=fren is not None)

    emirler: list[tuple[str, float, str]] = []
    for s, w in hedef.items():
        w0 = onceki.get(s, 0.0)
        if abs(w - w0) <= ESIK:
            continue
        birim = araci.birim_notional(s, fiyatlar[s])
        hedef_adet = 0.0 if w == 0.0 else araci.adet_yuvarla(s, w * ozk / birim)
        delta = round(hedef_adet - pozlar.get(s, 0.0), 8)
        # Çıkış kırıntı sınırına takılmaz: pozisyon tamamen kapanır.
        if delta == 0 or (w != 0.0 and abs(delta) * birim < ayar.asgari_emir):
            continue
        neden = ("fren" if fren else "cikis" if w == 0.0 else "donus" if w * w0 < 0 else "giris")
        emirler.append((s, delta, neden))
    # Önce riski azaltanlar (nakit/marjin açar), sonra girişler.
    emirler.sort(key=lambda e: 1 if e[2] == "giris" else 0)

    yapilan = []
    for s, delta, neden in emirler:
        try:
            dolum = araci.emir(s, delta, neden)
        except AraciHatasi as hata:
            defter.olay(simdi, "emir_hatasi", {"sembol": s, "delta": delta, "hata": str(hata)})
            continue
        defter.islem(simdi, dolum, dolum.adet * araci.birim_notional(s, dolum.fiyat), neden)
        yapilan.append({"sembol": s, "adet": dolum.adet, "fiyat": dolum.fiyat, "neden": neden})

    son_ozk = araci.ozkaynak()
    defter.ozkaynak(simdi, son_ozk)
    return {"zaman_ms": simdi, "ozkaynak": son_ozk, "fren": fren, "emirler": yapilan,
            "atlanan": atlanan, "yonler": yonler}


def calistir(araci: Araci, ayar: HesapAyari, dizin: Path, *, gecikme_s: float = 8.0,
             yaz: Any = print) -> None:
    """Bar kapanışlarına hizalı sonsuz döngü; `dizin/dur` dosyası görülünce temiz biter."""
    from scryne_quant.live.kilit import KosuKilidi

    dizin.mkdir(parents=True, exist_ok=True)
    kilit = KosuKilidi(dizin / "aktif")
    kilit.al()
    defter = Defter(dizin)
    adim = timeframe_ms(ayar.timeframe)
    dur = dizin / "dur"
    try:
        defter.olay(simdi_ms(), "basla", {"hesap": ayar.ad, "strateji": ayar.strateji})
        while not dur.exists():
            try:
                rapor = tur(araci, ayar, defter)
                yaz(f"{rapor['zaman_ms']} özkaynak {rapor['ozkaynak']:.2f} "
                    f"emir {len(rapor['emirler'])} atlanan {len(rapor['atlanan'])}"
                    + (f" FREN {rapor['fren']}" if rapor["fren"] else ""))
            except Exception as hata:  # noqa: BLE001 — tur hatası döngüyü öldürmez, kaydedilir
                defter.olay(simdi_ms(), "tur_hatasi",
                            {"hata": repr(hata), "iz": traceback.format_exc()[-2000:]})
                yaz(f"tur hatası: {hata!r}")
            sonraki = (simdi_ms() // adim + 1) * adim
            while not dur.exists() and simdi_ms() < sonraki + gecikme_s * 1000:
                time.sleep(min(5.0, max(0.5, (sonraki + gecikme_s * 1000 - simdi_ms()) / 1000)))
        defter.olay(simdi_ms(), "dur", {})
        dur.unlink(missing_ok=True)
    finally:
        defter.kapat()
        kilit.kapat()
