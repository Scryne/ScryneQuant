"""Çok enstrümanlı backtest referansını üretir. **Testlerde çalışmaz, elle çalıştırılır.**

Faz 10'un bitti kriteri: *"≥2 enstrüman, ≥10 işlem içeren senaryonun beklenen P&L'i
motordan bağımsız hesaplanıp `tests/fixtures/` altına sabitlenmiş; motorun çıktısı birebir
uyuşuyor. Üretici `scryne_quant`ı import etmiyor (K-029)."*

Bu dosya `scryne_quant`tan **hiçbir şey** import etmez ve bu bir söz değil, testle zorlanan
bir kısıt: `test_coklu_referans.py::test_ureticisi_motoru_import_etmiyor` import grafiğini
`ast` ile tarar (Faz 3'ün referans üreticisiyle aynı kalıp).

    uv run python tools/coklu_referans_uret.py

## Bağımsızlık nereye kadar gerçek

Faz 3'teki iki katmanın aynısı, bir üçüncüsüyle:

1. **Sayısal bağımsızlık.** Referans `Decimal` (50 basamak), motor `float64`. Aynı kayan
   nokta hatasını iki tarafta birden yapmak mümkün değil.
2. **Cebirsel bağımsızlık.** Senaryo C'nin her turu "tüm nakitle **tek** bir enstrümana
   gir, tamamen çık". Böyle bir turun sonucu portföy döngüsünden bağımsız, kapalı formülle
   yazılabilir — ve formül Faz 3'ünkiyle **birebir aynı**:

       C_son / C_ilk = (o_çıkış / o_giriş) × (1−s)(1−f) / [(1+s)(1+f)]

   Aynı olması tesadüf değil, kanıtın kendisi: iki enstrüman arasında dönüşümlü işlem
   yapmak tek enstrümanla işlem yapmaktan **farklı bir aritmetik gerektirmiyor**. K-052/2
   tam olarak bunu iddia ediyor.
3. **Yapısal bağımsızlık.** Senaryo D aynı barda hem satış hem alım içeriyor; sıra
   (önce satış), tek özkaynak anlık görüntüsü ve nakit tavanı kuralları buraya
   `coklu_motor.py`nin kodundan değil, docstring'inde yazan **kuralların metninden**
   yazıldı. Kapalı formül D'de geçerli değil; kanıt gücü orada daha zayıf ve bu bilinçli
   bir kabul, gizlenmiş bir varsayım değil.

## Fixture kendi kendine yeter

Barlar, hedef takvimi, maliyet modeli ve beklenen çıktı aynı dosyada — Faz 3'teki gerekçe:
yalnızca beklenen çıktıyı saklamak, girdiyi üreten bir yardımcı değiştiğinde referansı
sessizce yanlış hâle getirirdi.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from decimal import Decimal as D
from decimal import getcontext
from pathlib import Path
from typing import Any

getcontext().prec = 50

KOK = Path(__file__).resolve().parent.parent
HEDEF = KOK / "tests" / "fixtures" / "coklu_referans.json"

BAR_MS = 3_600_000
BASLANGIC_MS = 1_699_999_200_000  # 2023-11-14 22:00 UTC, 1h ızgarasına hizalı
SERMAYE = D("10000")
FEE_BPS = D("10")
SLIP_BPS = D("5")
BPS = D("0.0001")
SIFIR = D("1e-30")

AAA = "AAAUSDT"
BBB = "BBBUSDT"
SEMBOLLER = (AAA, BBB)

#: Senaryo C: 12 tur, her biri **tek** bir enstrümana tüm nakitle giriş ve tam çıkış.
#: Turlar iki enstrüman arasında dönüşümlü; kapalı formülle çapraz doğrulanabilen tek
#: senaryo. `(sembol, giriş açılışı, çıkış açılışı)`.
C_TURLAR: list[tuple[str, str, str]] = [
    (AAA, "20000", "20600"),  # +3,00 %
    (BBB, "1500", "1470"),    # −2,00 %
    (AAA, "20500", "21320"),  # +4,00 %
    (BBB, "1480", "1465"),    # −1,01 %
    (AAA, "21000", "21000"),  #  0,00 % (yalnızca maliyet)
    (BBB, "1450", "1537"),    # +6,00 %
    (AAA, "21400", "21186"),  # −1,00 %
    (BBB, "1520", "1596"),    # +5,00 %
    (AAA, "21800", "21582"),  # −1,00 %
    (BBB, "1580", "1659"),    # +5,00 %
    (AAA, "22000", "21780"),  # −1,00 %
    (BBB, "1640", "1738"),    # +5,98 %
]

#: Senaryo D: aynı barda çok hedefli yeniden dengeleme. `(bar, {sembol: hedef})`.
#: Kapalı formül geçerli değil; yalnızca Decimal defteri.
D_TAKVIM: list[tuple[int, dict[str, str]]] = [
    (1, {AAA: "0.5", BBB: "0.3"}),
    (4, {AAA: "0.2", BBB: "0.6"}),   # aynı barda AAA satışı + BBB alımı
    (7, {AAA: "0.6", BBB: "0.2"}),   # ters yön
    (10, {AAA: "0.0", BBB: "0.0"}),  # tam çıkış — iki tur birden kapanır
    (13, {AAA: "0.45", BBB: "0.45"}),
    (16, {AAA: "0.45", BBB: "0.45"}),  # değişmeyen hedef: fiyat kaydığı için dengeleme
    (19, {AAA: "0.9"}),                # BBB bahsedilmiyor → pozisyonu **korunur**
    (22, {BBB: "0.0"}),                # yalnızca BBB kapanır
    (25, {AAA: "0.0"}),
    (28, {AAA: "0.35", BBB: "0.35"}),
    (31, {AAA: "0.7", BBB: "0.0"}),
    (34, {AAA: "0.0", BBB: "0.0"}),
]

D_ACILISLAR: dict[str, list[str]] = {
    AAA: [
        "30000", "30200", "30500", "30300", "30800", "31200", "31000", "30700",
        "30400", "30900", "31500", "31800", "31600", "31100", "30600", "30200",
        "29800", "30100", "30500", "31000", "31400", "31900", "32300", "32000",
        "31600", "31200", "30900", "31300", "31700", "32200", "32600", "33000",
        "32700", "32300", "31900", "31500", "31100", "30800",
    ],
    BBB: [
        "1500", "1512", "1495", "1520", "1538", "1525", "1550", "1544",
        "1560", "1575", "1568", "1590", "1602", "1588", "1610", "1625",
        "1618", "1640", "1655", "1648", "1670", "1682", "1665", "1690",
        "1705", "1698", "1720", "1735", "1728", "1750", "1762", "1745",
        "1770", "1785", "1778", "1800", "1812", "1795",
    ],
}


def _q(x: D) -> str:
    """Hassasiyet kaybolmasın diye string. `float(x)` Decimal'in basamaklarını atardı."""
    return str(+x)


def _bar(i: int, acilis: D, kapanis: D) -> dict[str, Any]:
    return {
        "open_time": BASLANGIC_MS + i * BAR_MS,
        "open": _q(acilis),
        "high": _q(max(acilis, kapanis) + D("50")),
        "low": _q(min(acilis, kapanis) - D("50")),
        "close": _q(kapanis),
        "volume": "10",
        "quote_volume": _q(acilis * D("10")),
        "trades": 100,
        "quality_status": "ok",
    }


def _barlar_kur(acilislar: list[D]) -> list[dict[str, Any]]:
    """`close[i] = open[i+1]` — Spike 2'nin ölçtüğü gerçeğe uygun (Faz 3 ile aynı kalıp)."""
    n = len(acilislar)
    return [
        _bar(i, acilislar[i], acilislar[i + 1] if i + 1 < n else acilislar[i]) for i in range(n)
    ]


# --------------------------------------------------------------------- defter


class Defter:
    """Decimal defteri. Kuralların **metninden** yazıldı, motorun kodundan değil.

    Uygulanan kurallar ve kaynakları:

    - `t` barında verilen hedef `t+1` açılışından dolar (K-004).
    - Slippage her zaman aleyhte: alışta yukarı, satışta aşağı (K-007).
    - Bir barın hedefleri **tek** bir özkaynak anlık görüntüsüne göre ölçülür; o görüntü
      barın açılışında, hiçbir emir uygulanmadan alınır.
    - Aynı barda önce satışlar, sonra alımlar; grup içinde sembol adına göre.
    - Alımda harcanabilir tavan `nakit/(1+fee)`, satışta `elde × kayan fiyat`.
    - Bahsedilmeyen sembolün pozisyonu değişmez.
    """

    def __init__(self, fee_bps: D, slip_bps: D, sermaye: D) -> None:
        self.f = fee_bps * BPS
        self.s = slip_bps * BPS
        self.nakit = sermaye
        self.miktar: dict[str, D] = dict.fromkeys(SEMBOLLER, D(0))
        self.ort_maliyet: dict[str, D] = dict.fromkeys(SEMBOLLER, D(0))
        self.fill_ler: list[dict[str, Any]] = []
        self.turlar: list[dict[str, Any]] = []
        self._acik: dict[str, dict[str, Any]] = {}

    def ozkaynak(self, fiyatlar: dict[str, D]) -> D:
        return self.nakit + sum(
            (self.miktar[s] * fiyatlar[s] for s in sorted(SEMBOLLER)), D(0)
        )

    def bar(
        self, i: int, zaman_ms: int, acilislar: dict[str, D], hedefler: dict[str, D]
    ) -> list[str]:
        """Bir barın tüm hedeflerini uygular; atlama sebeplerini döndürür."""
        ozkaynak = self.ozkaynak(acilislar)
        farklar = {
            s: ozkaynak * h - self.miktar[s] * acilislar[s] for s, h in hedefler.items()
        }
        satislar = sorted(s for s, d in farklar.items() if d <= 0)
        alimlar = sorted(s for s, d in farklar.items() if d > 0)

        atlanan: list[str] = []
        for sembol in (*satislar, *alimlar):
            sebep = self._emir(i, zaman_ms, sembol, acilislar[sembol], farklar[sembol], ozkaynak)
            if sebep:
                atlanan.append(sebep)
        return atlanan

    def _emir(
        self, i: int, zaman_ms: int, sembol: str, acilis: D, fark: D, ozkaynak: D
    ) -> str:
        pay = SIFIR * max(ozkaynak, D(1))
        if abs(fark) <= pay:
            return "hedef_zaten_tutturulmus"

        if fark > 0:
            yon = "AL"
            fiyat = acilis * (1 + self.s)
            notional = min(fark, self.nakit / (1 + self.f))
            if notional <= pay:
                return "nakit_yok"
        else:
            yon = "SAT"
            fiyat = acilis * (1 - self.s)
            notional = min(-fark, self.miktar[sembol] * fiyat)
            if notional <= pay:
                return "pozisyon_yok"

        adet = notional / fiyat
        komisyon = notional * self.f
        slippage = abs(fiyat - acilis) * adet

        if yon == "AL":
            gider = notional + komisyon
            tur = self._acik.get(sembol)
            if tur is None:
                tur = {
                    "sembol": sembol,
                    "acilis_ms": zaman_ms,
                    "kapanis_ms": None,
                    "giris_notional": D(0),
                    "cikis_notional": D(0),
                    "miktar": D(0),
                    "komisyon": D(0),
                    "slippage": D(0),
                    "net_pnl": D(0),
                    "fill_sayisi": 0,
                }
                self._acik[sembol] = tur
                self.turlar.append(tur)
            self.ort_maliyet[sembol] = (
                self.ort_maliyet[sembol] * self.miktar[sembol] + gider
            ) / (self.miktar[sembol] + adet)
            self.nakit -= gider
            self.miktar[sembol] += adet
            tur["giris_notional"] += notional
            tur["miktar"] += adet
        else:
            tur = self._acik[sembol]
            hasilat = notional - komisyon
            maliyet = adet * self.ort_maliyet[sembol]
            self.nakit += hasilat
            self.miktar[sembol] -= adet
            if self.miktar[sembol] <= SIFIR:
                self.miktar[sembol] = D(0)
                self.ort_maliyet[sembol] = D(0)
            tur["cikis_notional"] += notional
            tur["net_pnl"] += hasilat - maliyet

        tur["komisyon"] += komisyon
        tur["slippage"] += slippage
        tur["fill_sayisi"] += 1

        self.fill_ler.append(
            {
                "bar": i,
                "sembol": sembol,
                "yon": yon,
                "referans_fiyat": _q(acilis),
                "fiyat": _q(fiyat),
                "miktar": _q(adet),
                "notional": _q(notional),
                "komisyon": _q(komisyon),
                "nakit_sonra": _q(self.nakit),
                "miktar_sonra": _q(self.miktar[sembol]),
            }
        )

        if self.miktar[sembol] == 0 and sembol in self._acik:
            self._acik[sembol]["kapanis_ms"] = zaman_ms
            del self._acik[sembol]
        return ""


def _kosu(
    barlar: dict[str, list[dict[str, Any]]], takvim: dict[int, dict[str, D]]
) -> dict[str, Any]:
    d = Defter(FEE_BPS, SLIP_BPS, SERMAYE)
    n = len(barlar[AAA])
    egri: list[str] = []
    atlanan: list[str] = []
    bekleyen: dict[str, D] | None = None

    for i in range(n):
        if bekleyen is not None:
            acilislar = {s: D(barlar[s][i]["open"]) for s in SEMBOLLER}
            atlanan.extend(d.bar(i, barlar[AAA][i]["open_time"], acilislar, bekleyen))
            bekleyen = None
        if i in takvim:
            if i == n - 1:
                atlanan.extend(["sonraki_bar_yok"] * len(takvim[i]))
            else:
                bekleyen = takvim[i]
        egri.append(_q(d.ozkaynak({s: D(barlar[s][i]["close"]) for s in SEMBOLLER})))

    kapali = [t for t in d.turlar if t["kapanis_ms"] is not None]
    return {
        "fill_ler": d.fill_ler,
        "turlar": [
            {
                "sembol": t["sembol"],
                "acilis_ms": t["acilis_ms"],
                "kapanis_ms": t["kapanis_ms"],
                "giris_notional": _q(t["giris_notional"]),
                "cikis_notional": _q(t["cikis_notional"]),
                "miktar": _q(t["miktar"]),
                "komisyon": _q(t["komisyon"]),
                "slippage": _q(t["slippage"]),
                "net_pnl": _q(t["net_pnl"]),
                "fill_sayisi": t["fill_sayisi"],
            }
            for t in d.turlar
        ],
        "ozkaynak": egri,
        "ozet": {
            "bitis_sermaye": egri[-1],
            "nakit": _q(d.nakit),
            "islem_sayisi": len(kapali),
            "kazanan": sum(1 for t in kapali if t["net_pnl"] > 0),
            "kaybeden": sum(1 for t in kapali if t["net_pnl"] <= 0),
            "toplam_komisyon": _q(sum((t["komisyon"] for t in d.turlar), D(0))),
            "toplam_slippage": _q(sum((t["slippage"] for t in d.turlar), D(0))),
            "net_pnl_toplam": _q(sum((t["net_pnl"] for t in kapali), D(0))),
        },
        "atlanan": sorted(atlanan),
    }


# ------------------------------------------------------------- kapalı formül


def _kapali_form(sermaye: D) -> tuple[list[str], str]:
    """Senaryo C'nin tur sonu sermayeleri — defterden bağımsız, cebirle.

    Formül Faz 3'ünkiyle **aynı** ve aynı olması kanıtın kendisi: tüm nakitle tek bir
    enstrümana girip tamamen çıkmak, hangi enstrüman olduğuna bakmayan bir aritmetik.
    Türetme `tools/backtest_referans_uret.py`de.
    """
    f = FEE_BPS * BPS
    s = SLIP_BPS * BPS
    carpan = (1 - s) * (1 - f) / ((1 + s) * (1 + f))
    sermayeler: list[str] = []
    c = sermaye
    for _, giris, cikis in C_TURLAR:
        c = c * (D(cikis) / D(giris)) * carpan
        sermayeler.append(_q(c))
    return sermayeler, _q(carpan)


def _senaryo_c() -> dict[str, Any]:
    n = 5 * len(C_TURLAR) + 2
    acilislar = {s: [D("1")] * n for s in SEMBOLLER}
    # Her sembol kendi başlangıç fiyatından başlar; işlem görmediği barlarda fiyatı sabit
    # kalır ki equity eğrisi yalnızca fill fiyatlarından etkilensin (Faz 3'ün kalıbı).
    baslangic = {AAA: D("20000"), BBB: D("1500")}
    fill_barlari: dict[str, set[int]] = {s: set() for s in SEMBOLLER}
    for k, (sembol, giris, cikis) in enumerate(C_TURLAR):
        acilislar[sembol][2 + 5 * k] = D(giris)
        acilislar[sembol][4 + 5 * k] = D(cikis)
        fill_barlari[sembol].update({2 + 5 * k, 4 + 5 * k})
    for sembol in SEMBOLLER:
        acilislar[sembol][0] = baslangic[sembol]
        for i in range(1, n):
            if i not in fill_barlari[sembol]:
                acilislar[sembol][i] = acilislar[sembol][i - 1]

    barlar = {s: _barlar_kur(acilislar[s]) for s in SEMBOLLER}
    takvim: dict[int, dict[str, D]] = {}
    for k, (sembol, _, _) in enumerate(C_TURLAR):
        takvim[1 + 5 * k] = {sembol: D(1)}
        takvim[3 + 5 * k] = {sembol: D(0)}

    return {
        "ad": "donusumlu_tam_giris_cikis",
        "aciklama": (
            "12 tur, her biri tek bir enstrümana tüm nakitle giriş ve tam çıkış; turlar "
            "iki enstrüman arasında dönüşümlü. Kapalı formülle çapraz doğrulanabilen tek "
            "senaryo — ve formül tek enstrümanlı referansınkiyle birebir aynı."
        ),
        "barlar": barlar,
        "hedefler": [
            {"bar": b, "agirliklar": {s: _q(h) for s, h in sorted(hedef.items())}}
            for b, hedef in sorted(takvim.items())
        ],
        "beklenen": _kosu(barlar, takvim),
    }


def _senaryo_d() -> dict[str, Any]:
    barlar = {s: _barlar_kur([D(a) for a in D_ACILISLAR[s]]) for s in SEMBOLLER}
    takvim = {b: {s: D(h) for s, h in hedef.items()} for b, hedef in D_TAKVIM}
    return {
        "ad": "eszamanli_dengeleme",
        "aciklama": (
            "Aynı barda hem satış hem alım, bahsedilmeyen sembol, değişmeyen hedef ve tam "
            "çıkış. Kapalı formül geçerli değil; referans yalnızca Decimal defteri. "
            "Ölçtüğü şey sıralama kuralı: önce satışlar, tek özkaynak anlık görüntüsü, "
            "nakit tavanı."
        ),
        "barlar": barlar,
        "hedefler": [
            {"bar": b, "agirliklar": {s: _q(h) for s, h in sorted(hedef.items())}}
            for b, hedef in sorted(takvim.items())
        ],
        "beklenen": _kosu(barlar, takvim),
    }


def main() -> int:
    c = _senaryo_c()
    d = _senaryo_d()

    formul, carpan = _kapali_form(SERMAYE)
    turlar = c["beklenen"]["turlar"]
    if len(turlar) != len(C_TURLAR):
        sys.exit(f"senaryo C {len(turlar)} tur üretti, {len(C_TURLAR)} bekleniyordu")

    # Tur sonunda pozisyon kapalı, yani sermaye = nakit. Defterin nakit izini kapalı
    # formülle karşılaştır.
    f = FEE_BPS * BPS
    nakit_izi: list[D] = []
    cc = SERMAYE
    for t in turlar:
        cc = cc - D(t["giris_notional"]) * (1 + f) + D(t["cikis_notional"]) * (1 - f)
        nakit_izi.append(cc)

    en_buyuk_fark = D(0)
    for i, (dd, ff) in enumerate(zip(nakit_izi, formul, strict=True)):
        fark = abs(dd - D(ff)) / D(ff)
        en_buyuk_fark = max(en_buyuk_fark, fark)
        if fark > D("1e-40"):
            sys.exit(f"tur {i}: defter {dd} ile kapalı formül {ff} uyuşmuyor (fark {fark})")

    c["kapali_form"] = {
        "formul": "C_son = C_ilk × (o_cikis / o_giris) × (1−s)(1−f) / [(1+s)(1+f)]",
        "carpan": carpan,
        "tur_sonu_sermaye": formul,
        "defter_ile_azami_bagil_fark": _q(en_buyuk_fark),
    }

    # Senaryo D'nin kanıt gücünü görünür kılan iki sayı: aynı barda kaç kez hem satış hem
    # alım oldu, ve kaç tur kapandı. Sıfırsa senaryo ölçmek istediği şeyi ölçmüyor demektir.
    barlar_fill = {}
    for fill in d["beklenen"]["fill_ler"]:
        barlar_fill.setdefault(fill["bar"], set()).add(fill["yon"])
    karisik = sum(1 for yonler in barlar_fill.values() if len(yonler) > 1)
    if karisik == 0:
        sys.exit("senaryo D aynı barda satış+alım üretmedi: sıralama kuralı test edilmiyor")
    d["olcum"] = {"ayni_barda_satis_ve_alim": karisik}

    belge = {
        "uretildi": dt.date.today().isoformat(),
        "ureten": "tools/coklu_referans_uret.py",
        "hassasiyet": f"Decimal, prec={getcontext().prec}",
        "not": (
            "Çok enstrümanlı bağımsız referans (Faz 10, K-029/K-052-2). Motor float64, bu "
            "dosya Decimal; senaryo C ayrıca kapalı formülle çapraz doğrulandı. Sayılar "
            "string olarak yazılıyor ki JSON'a yazarken hassasiyet kaybolmasın."
        ),
        "semboller": list(SEMBOLLER),
        "timeframe": "1h",
        "maliyet": {"fee_taker_bps": float(FEE_BPS), "slippage_bps": float(SLIP_BPS)},
        "baslangic_sermaye": float(SERMAYE),
        "senaryolar": [c, d],
    }

    HEDEF.parent.mkdir(parents=True, exist_ok=True)
    HEDEF.write_text(
        json.dumps(belge, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"yazıldı: {HEDEF.relative_to(KOK)} ({HEDEF.stat().st_size / 1024:.0f} KB)")
    for s in (c, d):
        ozet = s["beklenen"]["ozet"]
        print(
            f"senaryo {s['ad']}: {ozet['islem_sayisi']} islem, "
            f"bitis {ozet['bitis_sermaye']}"
        )
    print(f"kapalı form ile azami bağıl fark: {en_buyuk_fark}")
    print(f"senaryo D, aynı barda satış+alım olan bar sayısı: {karisik}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
