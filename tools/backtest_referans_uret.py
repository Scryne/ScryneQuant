"""Backtest referans senaryosunu üretir. **Testlerde çalışmaz, elle çalıştırılır.**

Faz 3'ün bitti kriteri: "≥10 işlemlik bir referans senaryonun beklenen P&L'i **motordan
bağımsız** olarak hesaplanıp `tests/fixtures/` altına sabitlenmiş... Referans motorun kendi
çıktısından türetilemez — türetilirse test hiçbir şey kanıtlamaz."

Bu dosya `scryne_quant.backtest`, `scryne_quant.portfolio` veya `scryne_quant.strategy`
paketlerinden **hiçbir şey import etmez**. Bu bir söz değil, testle zorlanan bir kısıt:
`test_backtest_referans.py::test_referans_ureticisi_motoru_import_etmiyor` bu dosyanın
import grafiğini tarar (K-027'nin izolasyon tarayıcısının aynısı).

    uv run python tools/backtest_referans_uret.py

## Bağımsızlık nereye kadar gerçek

Dürüst olmak gerekirse iki farklı bağımsızlık var ve ikisini karıştırmamak lazım:

1. **Sayısal bağımsızlık — tam.** Referans `Decimal` ile 50 basamak hassasiyette
   hesaplanıyor; motor `float64` kullanıyor. Aynı kayan nokta hatasını iki tarafta birden
   yapmak mümkün değil.
2. **Cebirsel bağımsızlık — asıl kanıt burada.** Senaryo A'nın her işlemi "tüm nakitle
   gir, tamamen çık" biçiminde. Böyle bir turun sonucu döngü çalıştırmadan, **kapalı
   formülle** yazılabilir:

       C_son / C_ilk = (o_çıkış / o_giriş) × (1−s)(1−f) / [(1+s)(1+f)]

   Bu formül ne motorun kodundan ne de aşağıdaki defterden türetildi; K-004 ve K-007'nin
   metninden cebirle çıkarıldı. Üretici, defter sonucu ile kapalı formülü **birbirine
   karşı** doğrulamadan dosya yazmayı reddeder. Yani fixture'ın içine giren her sayı iki
   bağımsız yoldan aynı çıkmış demektir.

Senaryo B (kısmi maruziyet) kapalı formüle uymaz — orada yalnızca defter var, ve testin
kanıt gücü o senaryo için daha zayıf. Bu bilinçli bir kabul, gizlenmiş bir varsayım değil.

## Fixture kendi kendine yeter

Barlar, sinyal takvimi, maliyet modeli ve beklenen çıktı aynı dosyada. Yalnızca beklenen
çıktıyı saklamak, girdiyi üreten bir yardımcı değiştiğinde referansı sessizce yanlış hâle
getirirdi.
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
HEDEF = KOK / "tests" / "fixtures" / "backtest_referans.json"

BAR_MS = 3_600_000
BASLANGIC_MS = 1_699_999_200_000  # 2023-11-14 22:00 UTC, 1h ızgarasına hizalı
SERMAYE = D("10000")
FEE_BPS = D("10")
SLIP_BPS = D("5")
BPS = D("0.0001")

#: Senaryo A: her tur "tüm nakitle gir, tamamen çık". 12 tur, 6 kazanç 6 kayıp.
#: Fiyatlar bilerek yuvarlak: ilk turun aritmetiği hesap makinesiyle kontrol edilebilsin.
#: Giriş fill'i bar `2+5k`, çıkış fill'i bar `4+5k`.
TURLAR: list[tuple[str, str]] = [
    ("20000", "20600"),  # +3,00 %  → kazanç
    ("20500", "20300"),  # −0,98 %  → kayıp
    ("20200", "21000"),  # +3,96 %  → kazanç
    ("21000", "20800"),  # −0,95 %  → kayıp
    ("20800", "20800"),  #  0,00 %  → kayıp (yalnızca maliyet)
    ("20900", "22000"),  # +5,26 %  → kazanç
    ("21800", "21500"),  # −1,38 %  → kayıp
    ("21600", "22400"),  # +3,70 %  → kazanç
    ("22300", "22100"),  # −0,90 %  → kayıp
    ("22000", "23000"),  # +4,55 %  → kazanç
    ("22800", "22600"),  # −0,88 %  → kayıp
    ("22500", "23400"),  # +4,00 %  → kazanç
]

#: Senaryo B: kısmi maruziyet. Kapalı formül burada geçerli değil; yalnızca defter.
#: `(bar, hedef_maruziyet)` — sinyal bu barda üretilir, bir sonraki barın açılışında dolar.
B_TAKVIM: list[tuple[int, str]] = [
    (1, "0.5"),
    (4, "0.75"),
    (7, "0.25"),
    (10, "1.0"),
    (13, "0.0"),
    (16, "0.6"),
    (19, "0.6"),  # aynı hedef: fiyat kaydığı için yeniden dengeleme yolunu tetikler
    (22, "0.3"),
    (25, "0.0"),
    (28, "0.9"),
    (31, "0.45"),
    (34, "0.0"),
]

B_ACILISLAR: list[str] = [
    "30000", "30200", "30500", "30300", "30800", "31200", "31000", "30700",
    "30400", "30900", "31500", "31800", "31600", "31100", "30600", "30200",
    "29800", "30100", "30500", "31000", "31400", "31900", "32300", "32000",
    "31600", "31200", "30900", "31300", "31700", "32200", "32600", "33000",
    "32700", "32300", "31900", "31500", "31100", "30800",
]


def _q(x: D) -> str:
    """Kayan noktaya çevrilirken bilgi kaybı olmasın diye string olarak yazılıyor.

    JSON'a `float(x)` yazmak Decimal'in fazladan basamaklarını atardı — ve testin
    karşılaştırdığı sayı, üretilen sayı olmaktan çıkardı.
    """
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
    """Bar listesi. `close[i] = open[i+1]` — Spike 2'nin ölçtüğü gerçeğe uygun.

    K-020'nin çürütülmesinde ölçülmüştü: kripto 7/24 kesintisiz olduğu için `open[t+1]`
    ile `close[t]` vakaların %52'sinde birebir aynı. Referans senaryonun bunu izlemesi
    hem gerçekçi hem de her sayıyı yuvarlak tutuyor.
    """
    n = len(acilislar)
    return [
        _bar(i, acilislar[i], acilislar[i + 1] if i + 1 < n else acilislar[i]) for i in range(n)
    ]


# --------------------------------------------------------------------- defter


class Defter:
    """Decimal defteri: K-004 ve K-007'nin metninden yazıldı, motorun kodundan değil."""

    def __init__(self, fee_bps: D, slip_bps: D, sermaye: D) -> None:
        self.f = fee_bps * BPS
        self.s = slip_bps * BPS
        self.nakit = sermaye
        self.miktar = D(0)
        self.ort_maliyet = D(0)
        self.fill_ler: list[dict[str, Any]] = []
        self.turlar: list[dict[str, Any]] = []
        self._acik: dict[str, Any] | None = None

    def fill(self, bar: int, zaman_ms: int, acilis: D, hedef: D) -> str:
        """Bir sinyali `t+1` açılışında uygular; ne olduğunu döndürür."""
        deger = self.miktar * acilis
        ozkaynak = self.nakit + deger
        fark = ozkaynak * hedef - deger
        if abs(fark) <= D("1e-30"):
            return "hedef_zaten_tutturulmus"

        if fark > 0:
            yon = "AL"
            fiyat = acilis * (1 + self.s)
            notional = min(fark, self.nakit / (1 + self.f))
            if notional <= D("1e-30"):
                return "nakit_yok"
        else:
            yon = "SAT"
            fiyat = acilis * (1 - self.s)
            notional = min(-fark, self.miktar * fiyat)
            if notional <= D("1e-30"):
                return "pozisyon_yok"

        adet = notional / fiyat
        komisyon = notional * self.f
        slippage = abs(fiyat - acilis) * adet

        if yon == "AL":
            gider = notional + komisyon
            if self._acik is None:
                self._acik = {
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
                self.turlar.append(self._acik)
            self.ort_maliyet = (self.ort_maliyet * self.miktar + gider) / (self.miktar + adet)
            self.nakit -= gider
            self.miktar += adet
            self._acik["giris_notional"] += notional
            self._acik["miktar"] += adet
        else:
            assert self._acik is not None
            hasilat = notional - komisyon
            maliyet = adet * self.ort_maliyet
            self.nakit += hasilat
            self.miktar -= adet
            if self.miktar <= D("1e-30"):
                self.miktar = D(0)
                self.ort_maliyet = D(0)
            self._acik["cikis_notional"] += notional
            self._acik["net_pnl"] += hasilat - maliyet

        self._acik["komisyon"] += komisyon
        self._acik["slippage"] += slippage
        self._acik["fill_sayisi"] += 1

        self.fill_ler.append(
            {
                "bar": bar,
                "yon": yon,
                "referans_fiyat": _q(acilis),
                "fiyat": _q(fiyat),
                "miktar": _q(adet),
                "notional": _q(notional),
                "komisyon": _q(komisyon),
                "nakit_sonra": _q(self.nakit),
                "miktar_sonra": _q(self.miktar),
            }
        )

        if self.miktar == 0 and self._acik is not None:
            self._acik["kapanis_ms"] = zaman_ms
            self._acik = None
        return yon

    def ozkaynak(self, kapanis: D) -> D:
        return self.nakit + self.miktar * kapanis


def _kosu(barlar: list[dict[str, Any]], takvim: dict[int, D]) -> dict[str, Any]:
    """Defteri senaryo üzerinde çalıştırır."""
    d = Defter(FEE_BPS, SLIP_BPS, SERMAYE)
    n = len(barlar)
    egri: list[str] = []
    atlanan: list[str] = []
    bekleyen: D | None = None

    for i, bar in enumerate(barlar):
        if bekleyen is not None:
            sonuc = d.fill(i, bar["open_time"], D(bar["open"]), bekleyen)
            if sonuc not in ("AL", "SAT"):
                atlanan.append(sonuc)
            bekleyen = None
        if i in takvim:
            if i == n - 1:
                atlanan.append("sonraki_bar_yok")
            else:
                bekleyen = takvim[i]
        egri.append(_q(d.ozkaynak(D(bar["close"]))))

    kapali = [t for t in d.turlar if t["kapanis_ms"] is not None]
    return {
        "fill_ler": d.fill_ler,
        "turlar": [
            {
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
            "miktar": _q(d.miktar),
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
    """Her turun sonundaki sermayeyi cebirle hesaplar — defterden bağımsız.

    Tüm nakitle girip tamamen çıkan bir tur için:

        C_son = C_ilk × (o_çıkış / o_giriş) × (1−s)(1−f) / [(1+s)(1+f)]

    Türetme: girişte harcanabilir notional `C/(1+f)`, birim fiyat `o_giriş(1+s)`, yani
    `adet = C / [(1+f)·o_giriş·(1+s)]`. Çıkışta hasılat `adet·o_çıkış(1−s)(1−f)`. İkisini
    çarpınca yukarıdaki oran kalır; ara adımlarda hiçbir döngü yok.
    """
    f = FEE_BPS * BPS
    s = SLIP_BPS * BPS
    carpan = (1 - s) * (1 - f) / ((1 + s) * (1 + f))

    sermayeler: list[str] = []
    c = sermaye
    for giris, cikis in TURLAR:
        c = c * (D(cikis) / D(giris)) * carpan
        sermayeler.append(_q(c))
    return sermayeler, _q(carpan)


def _senaryo_a() -> dict[str, Any]:
    n = 5 * len(TURLAR) + 2
    acilislar = [D("20000")] * n
    for k, (giris, cikis) in enumerate(TURLAR):
        acilislar[2 + 5 * k] = D(giris)
        acilislar[4 + 5 * k] = D(cikis)
    # Fill dışı barlar: bir önceki fill fiyatını taşısınlar ki equity eğrisi
    # yapay dalgalanmasın ve turların P&L'i yalnızca fill fiyatlarından gelsin.
    for i in range(1, n):
        if i not in {2 + 5 * k for k in range(len(TURLAR))} | {
            4 + 5 * k for k in range(len(TURLAR))
        }:
            acilislar[i] = acilislar[i - 1]

    barlar = _barlar_kur(acilislar)
    takvim: dict[int, D] = {}
    for k in range(len(TURLAR)):
        takvim[1 + 5 * k] = D(1)
        takvim[3 + 5 * k] = D(0)

    kosu = _kosu(barlar, takvim)
    return {
        "ad": "tam_giris_cikis",
        "aciklama": (
            "12 tur, her biri tüm nakitle giriş ve tam çıkış. Kapalı formülle çapraz "
            "doğrulanabilen tek senaryo."
        ),
        "barlar": barlar,
        "sinyaller": [
            {
                "bar": b,
                "side": "BUY" if t > 0 else "FLAT",
                "target_exposure": _q(t),
            }
            for b, t in sorted(takvim.items())
        ],
        "beklenen": kosu,
    }


def _senaryo_b() -> dict[str, Any]:
    barlar = _barlar_kur([D(a) for a in B_ACILISLAR])
    takvim = {b: D(t) for b, t in B_TAKVIM}
    kosu = _kosu(barlar, takvim)
    return {
        "ad": "kismi_maruziyet",
        "aciklama": (
            "Kısmi hedef maruziyetler, artırma/azaltma, değişmeyen hedef ve tam çıkış. "
            "Kapalı formül geçerli değil; referans yalnızca Decimal defteri."
        ),
        "barlar": barlar,
        "sinyaller": [
            {
                "bar": b,
                "side": "BUY" if t > 0 else "FLAT",
                "target_exposure": _q(t),
            }
            for b, t in sorted(takvim.items())
        ],
        "beklenen": kosu,
    }


def main() -> int:
    a = _senaryo_a()
    b = _senaryo_b()

    # --- çapraz doğrulama: defter ile kapalı formül aynı sayıyı vermeli
    formul, carpan = _kapali_form(SERMAYE)
    defter = [D(t["cikis_notional"]) for t in a["beklenen"]["turlar"]]
    if len(defter) != len(TURLAR):
        sys.exit(f"senaryo A {len(defter)} tur üretti, {len(TURLAR)} bekleniyordu")

    # Tur sonundaki sermaye = tüm nakit (pozisyon kapalı), yani çıkış hasılatı komisyon
    # düşülmüş hâli. Defterin nakit izini kapalı formülle karşılaştır.
    nakit_izi: list[D] = []
    c = SERMAYE
    f = FEE_BPS * BPS
    for t in a["beklenen"]["turlar"]:
        c = c - D(t["giris_notional"]) * (1 + f) + D(t["cikis_notional"]) * (1 - f)
        nakit_izi.append(c)

    en_buyuk_fark = D(0)
    for i, (dd, ff) in enumerate(zip(nakit_izi, formul, strict=True)):
        fark = abs(dd - D(ff)) / D(ff)
        en_buyuk_fark = max(en_buyuk_fark, fark)
        if fark > D("1e-40"):
            sys.exit(f"tur {i}: defter {dd} ile kapalı formül {ff} uyuşmuyor (fark {fark})")

    a["kapali_form"] = {
        "formul": "C_son = C_ilk × (o_cikis / o_giris) × (1−s)(1−f) / [(1+s)(1+f)]",
        "carpan": carpan,
        "tur_sonu_sermaye": formul,
        "defter_ile_azami_bagil_fark": _q(en_buyuk_fark),
    }

    ilk = a["beklenen"]["fill_ler"][0]
    ikinci = a["beklenen"]["fill_ler"][1]
    belge = {
        "uretildi": dt.date.today().isoformat(),
        "ureten": "tools/backtest_referans_uret.py",
        "hassasiyet": f"Decimal, prec={getcontext().prec}",
        "not": (
            "Bağımsız referans (K-029). Motor float64, bu dosya Decimal; ayrıca senaryo A "
            "kapalı formülle çapraz doğrulandı. Sayılar string olarak yazılıyor ki "
            "JSON'a yazarken hassasiyet kaybolmasın."
        ),
        "maliyet": {"fee_taker_bps": float(FEE_BPS), "slippage_bps": float(SLIP_BPS)},
        "baslangic_sermaye": float(SERMAYE),
        "elle_kontrol": [
            "Senaryo A, ilk giriş (bar 2, açılış 20000):",
            f"  fill fiyatı = 20000 × (1 + 0,0005) = {ilk['fiyat']}",
            f"  harcanabilir notional = 10000 / (1 + 0,001) = {ilk['notional']}",
            f"  miktar = notional / fiyat = {ilk['miktar']}",
            f"  komisyon = notional × 0,001 = {ilk['komisyon']}",
            f"  nakit = 10000 − notional − komisyon = {ilk['nakit_sonra']}",
            "Senaryo A, ilk çıkış (bar 4, açılış 20600):",
            f"  fill fiyatı = 20600 × (1 − 0,0005) = {ikinci['fiyat']}",
            f"  notional = miktar × fiyat = {ikinci['notional']}",
            f"  komisyon = notional × 0,001 = {ikinci['komisyon']}",
            f"  nakit = notional − komisyon = {ikinci['nakit_sonra']}",
            f"Kapalı formül kontrolü: 10000 × (20600/20000) × {carpan} = {formul[0]}",
        ],
        "senaryolar": [a, b],
    }

    HEDEF.parent.mkdir(parents=True, exist_ok=True)
    HEDEF.write_text(
        json.dumps(belge, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"yazıldı: {HEDEF.relative_to(KOK)} ({HEDEF.stat().st_size / 1024:.0f} KB)")
    print(f"senaryo A: {a['beklenen']['ozet']['islem_sayisi']} islem, "
          f"bitis {a['beklenen']['ozet']['bitis_sermaye']}")
    print(f"senaryo B: {b['beklenen']['ozet']['islem_sayisi']} islem, "
          f"bitis {b['beklenen']['ozet']['bitis_sermaye']}")
    print(f"kapalı form ile azami bağıl fark: {en_buyuk_fark}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
