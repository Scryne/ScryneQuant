"""Duyuru/olay verisinin kaynak ölçüsü — K-045'in istisna şartı + K-068'in ek şartı. (Faz 16)

    uv run python tools/faz16_duyuru_olcum.py

**Soru:** Binance duyuruları (listeleme, marjin/vadeli ekleme, kaldırma, delist), evren
kıyasının **yapısı gereği göremediği** bir şey taşıyor mu?

Kıyasın evreni ayda bir yenilenir ve sıralama ölçütü önceki ayın hacmidir. Bir sembol ayın
ortasında listelendiğinde, marjine alındığında ya da delist edildiğinde kıyas bunu bir
sonraki ay başına kadar görmez. Bu ölçüm o boşluğun **ne kadar büyük** olduğunu ve boşlukta
ölçülebilir bir getiri farkı olup olmadığını sayıya bağlar.

## Bu araç bir çekiliş değildir — ama artık ileriye dönük getiriye bakıyor

K-068'in ek şartı gereği (kaynak farkı tek başına yetmiyor) bu ölçüm kesitteki ileriye dönük
göreli getiriyi de raporluyor. Sızıntıyı önleyen sınır K-068'in aynı gün eklenen maddesi:
**ileriye dönük getiriye yalnızca in-sample penceresinde bakılır** (bar 0-55.594). OOS
penceresi bu dosyada hiç açılmaz; §3'ün bütün sayıları IS'tir ve çıktı bunu yazar.

Çekiliş sayılmamasının şartı değişmedi: strateji koşmaz, parametre seçilmez, kapı hesaplanmaz.
Buradan bir program çıkarsa hipotezleri normal şekilde deftere yazılır ve bütçeden düşer
(K-039, K-051).

## Kurallar

- Evren üyeliği PIT tablosundan, ay ay (K-052/3). Olay anında üye olan ve olmayan
  semboller §3'te **ayrı kollar** olarak raporlanır; üyelik şartı konmaz.
- Duyurunun görülme anı `yayin_ms`; getiri **duyurudan sonra açılan ilk bardan** başlar
  (K-004'ün ruhu: duyuru barının kapanışından doldurulmaz).
- Göreli getiri = sembolün log getirisi − aynı pencerede evren üyelerinin **medyan** log
  getirisi. Kesitsel bir sıralama sorusu sorulduğu için piyasa yönü çıkarılır.
- Kotesi boş olan olay (`(ACE)` biçimi) §3'e girmez: hangi paritede işlem göreceği yazmıyor,
  uydurulmaz. Sayısı raporda.
- Eksik bar uydurulmaz; ufku veri bitişine taşan olay o ufukta sayılmaz.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from scryne_quant.common.hash import git_durumu
from scryne_quant.common.zaman import simdi_ms, utc_str

KOK = Path(__file__).resolve().parent.parent
EVREN = KOK / "data" / "evren"
TABLO = EVREN / "_evren" / "27b7a16ed0ed.parquet"
DUYURU = KOK / "data" / "duyuru"
CIKTI = KOK / "runs" / "faz16" / "kaynak-olcumu-duyuru.json"

SAAT_MS = 3_600_000
GUN_MS = 86_400_000
#: Koşu kaydındaki bölme (`runs/faz12/konumlanma_oi.json`): IS bar 0-55.594, OOS sonrası.
IS_BITIS_BAR = 55_594
#: Ölçülen ufuklar (bar = saat).
UFUKLAR = (24, 72, 168, 720)
#: Kesitsel medyan için bir barda asgari kaç üyenin getirisi olmalı.
ASGARI_UYE = 10


def _grid(semboller: list[str]) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Union saat ızgarası ve sembol başına kapanış dizisi (ızgaraya hizalı, boşluk NaN)."""
    ilk, son = [], []
    ham: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for s in semboller:
        yol = EVREN / s / "1h.parquet"
        if not yol.exists():
            continue
        t = pq.read_table(yol, columns=["open_time", "close"])
        ot = t.column("open_time").to_numpy()
        if ot.size == 0:
            continue
        ham[s] = (ot, t.column("close").to_numpy().astype(np.float64))
        ilk.append(int(ot[0]))
        son.append(int(ot[-1]))
    if not ham:
        raise SystemExit("evren deposunda okunabilir sembol yok")
    zamanlar = np.arange(min(ilk), max(son) + SAAT_MS, SAAT_MS, dtype=np.int64)
    kapanis: dict[str, np.ndarray] = {}
    for s, (ot, c) in ham.items():
        dizi = np.full(zamanlar.size, np.nan, dtype=np.float32)
        idx = ((ot - zamanlar[0]) // SAAT_MS).astype(np.int64)
        gecerli = (idx >= 0) & (idx < zamanlar.size)
        dizi[idx[gecerli]] = c[gecerli]
        kapanis[s] = dizi
    return zamanlar, kapanis


def _uyelik(tablo: pd.DataFrame, zamanlar: np.ndarray, semboller: list[str]) -> np.ndarray:
    """(sembol, bar) üyelik maskesi: ayın bütün barlarında o ayın listesi geçerli."""
    ts = pd.to_datetime(zamanlar, unit="ms", utc=True).tz_localize(None)
    aylar = ts.to_period("M").astype(str)
    sira = {s: i for i, s in enumerate(semboller)}
    maske = np.zeros((len(semboller), zamanlar.size), dtype=bool)
    for ay, grup in tablo.groupby("ay"):
        bar = np.flatnonzero(aylar == ay)
        if bar.size == 0:
            continue
        for s in grup["sembol"]:
            i = sira.get(s)
            if i is not None:
                maske[i, bar[0]:bar[-1] + 1] = True
    return maske


def _log(kapanis: dict[str, np.ndarray], semboller: list[str]) -> np.ndarray:
    m = np.full((len(semboller), next(iter(kapanis.values())).size), np.nan, dtype=np.float32)
    for i, s in enumerate(semboller):
        d = kapanis.get(s)
        if d is not None:
            with np.errstate(invalid="ignore", divide="ignore"):
                m[i] = np.log(d)
    return m


def _kesit_medyan(logc: np.ndarray, uye: np.ndarray, h: int) -> np.ndarray:
    """Bar i için, i→i+h penceresinde üyelerin medyan log getirisi (yoksa NaN)."""
    n = logc.shape[1]
    getiri = np.full(logc.shape, np.nan, dtype=np.float32)
    getiri[:, : n - h] = logc[:, h:] - logc[:, : n - h]
    getiri[~uye] = np.nan
    sayi = np.sum(np.isfinite(getiri), axis=0)
    med = np.full(n, np.nan, dtype=np.float64)
    dolu = np.flatnonzero(sayi >= ASGARI_UYE)
    if dolu.size:
        med[dolu] = np.nanmedian(getiri[:, dolu], axis=0)
    return med


def _isaret_p(pozitif: int, n: int) -> float:
    """İki yönlü işaret testi (normal yaklaşım; n<30 ise NaN)."""
    if n < 30:
        return float("nan")
    z = (pozitif - n / 2) / np.sqrt(n / 4)
    from math import erfc

    return float(erfc(abs(z) / np.sqrt(2)))


def _ozet(x: np.ndarray) -> dict[str, float | int]:
    x = x[np.isfinite(x)]
    if x.size == 0:
        return {"n": 0}
    poz = int(np.sum(x > 0))
    return {"n": int(x.size), "medyan": float(np.median(x)), "ortalama": float(np.mean(x)),
            "p25": float(np.percentile(x, 25)), "p75": float(np.percentile(x, 75)),
            "pozitif_oran": poz / x.size, "isaret_p": _isaret_p(poz, x.size)}


def main() -> int:
    tablo = pd.read_parquet(TABLO)
    olaylar = pd.read_parquet(DUYURU / "olaylar.parquet")
    duyurular = pd.read_parquet(DUYURU / "duyurular.parquet")
    semboller = sorted(set(tablo["sembol"]))
    zamanlar, kapanis = _grid(semboller)
    semboller = [s for s in semboller if s in kapanis]
    uye = _uyelik(tablo, zamanlar, semboller)
    logc = _log(kapanis, semboller)
    is_bitis_ms = int(zamanlar[min(IS_BITIS_BAR, zamanlar.size - 1)])
    sira = {s: i for i, s in enumerate(semboller)}

    rapor: dict = {
        "uretildi": utc_str(simdi_ms()),
        "git": git_durumu(),
        "cekilis_degil": True,
        "kapsam": {
            "evren_tablosu": TABLO.name,
            "sembol": len(semboller),
            "bar": int(zamanlar.size),
            "ilk_bar": utc_str(int(zamanlar[0])),
            "son_bar": utc_str(int(zamanlar[-1])),
            "is_bitis_bar": IS_BITIS_BAR,
            "is_bitis": utc_str(is_bitis_ms),
            "uyari": "Ileriye donuk getiri yalnizca IS'te olculdu (K-068 ek sart).",
        },
    }

    # ---- 1. PIT bütünlüğü -------------------------------------------------------------
    d = duyurular.copy()
    d["yil"] = pd.to_datetime(d["yayin_ms"], unit="ms", utc=True).dt.year
    gecikme = (d["ilk_gorulen_ms"] - d["yayin_ms"]) / GUN_MS
    rapor["pit"] = {
        "duyuru": int(len(d)),
        "govde": int(len(pd.read_parquet(DUYURU / "govdeler.parquet"))),
        "olay_satiri": int(len(olaylar)),
        "yil_dagilimi": {str(k): int(v) for k, v in d["yil"].value_counts().sort_index().items()},
        "ilk_gorulen_gecikme_gun": {
            "medyan": float(np.median(gecikme)), "azami": float(np.max(gecikme)),
            "not": "Arsivden indirildi: gecikme = bugun - yayin. PIT olan alan yayin_ms.",
        },
        "etkili_zamani_olan_oran": float(np.mean(np.isfinite(olaylar["etkili_ms"]))),
        "kotesi_bos_olay": int((olaylar["kote"] == "").sum()),
    }

    # ---- 2. Kıyasın körlüğü: duyuru ile evren üyeliği arasındaki gecikme ---------------
    ilk_ay = tablo.groupby("sembol")["ay"].min().to_dict()
    son_ay = tablo.groupby("sembol")["ay"].max().to_dict()
    giris, cikis = [], []
    for _, r in olaylar.iterrows():
        p = str(r["parite"])
        if p not in ilk_ay:
            continue
        gun = pd.Timestamp(int(r["yayin_ms"]), unit="ms", tz="UTC")
        if r["olay"] in ("spot_listeleme", "vadeli_listeleme", "marjin_ekleme"):
            hedef = pd.Period(ilk_ay[p], freq="M").to_timestamp().tz_localize("UTC")
            if hedef > gun:
                giris.append((hedef - gun).total_seconds() / 86_400)
        elif r["olay"] in ("delist", "spot_kaldirma", "vadeli_delist"):
            hedef = (pd.Period(son_ay[p], freq="M") + 1).to_timestamp().tz_localize("UTC")
            if hedef > gun:
                cikis.append((hedef - gun).total_seconds() / 86_400)
    rapor["kiyasin_korlugu"] = {
        "aciklama": "Duyurudan, kiyasin evreninde o sembolun ilk/son gorundugu ay sinirina "
                    "kadar gecen gun. Kiyas ayda bir yenilenir; bu sure onun kor kaldigi sure.",
        "giris_gecikmesi_gun": _ozet(np.array(giris, dtype=float)),
        "cikis_gecikmesi_gun": _ozet(np.array(cikis, dtype=float)),
    }

    # ---- 3. IS olay çalışması ----------------------------------------------------------
    medyanlar = {h: _kesit_medyan(logc, uye, h) for h in UFUKLAR}
    o = olaylar[(olaylar["kote"] != "") & olaylar["parite"].isin(sira)].copy()
    o = o[o["yayin_ms"] < is_bitis_ms]
    # Duyurudan **sonra** açılan ilk bar (K-004): searchsorted 'right'.
    o["bar"] = np.searchsorted(zamanlar, o["yayin_ms"].to_numpy(), side="right")
    o["i"] = o["parite"].map(sira)
    tablo_olay: dict[str, dict] = {}
    for olay, grup in o.groupby("olay"):
        satir: dict[str, dict] = {"n_olay": int(len(grup))}
        for h in UFUKLAR:
            bar = grup["bar"].to_numpy()
            idx = grup["i"].to_numpy()
            gecerli = (bar + h) < zamanlar.size
            bar, idx = bar[gecerli], idx[gecerli]
            if bar.size == 0:
                satir[f"h{h}"] = {"uye": {"n": 0}, "uye_degil": {"n": 0}}
                continue
            uyeydi = uye[idx, bar]
            ham = logc[idx, bar + h] - logc[idx, bar]
            goreli = ham - medyanlar[h][bar]
            # İki kol ayrı raporlanır. Listeleme duyurusunda sembol **tanım gereği** henüz
            # üye değildir; üyeliği şart koşmak, ölçülmek istenen kör bölgeyi silerdi (ilk
            # koşuda böyle oldu: spot_listeleme n=9'a düştü).
            satir[f"h{h}"] = {
                "uye": _ozet(np.where(uyeydi, goreli, np.nan)),
                "uye_degil": _ozet(np.where(~uyeydi, goreli, np.nan)),
            }
        tablo_olay[str(olay)] = satir
    rapor["is_olay_calismasi"] = {
        "pencere": "in_sample",
        "olcu": "sembol log getirisi - ayni pencerede evren uyelerinin medyan log getirisi",
        "baslangic": "duyurudan SONRA acilan ilk bar",
        "kollar": "uye = olay aninda evren uyesiydi; uye_degil = degildi (kiyasin kor bolgesi)",
        "olaylar": tablo_olay,
    }

    # ---- 4. Kör pencere: duyurudan evrene girişe kadar göreli getiri --------------------
    # Doğrudan iktisadi büyüklük: kıyas bu pencereyi kaçırıyor. Yalnızca IS, yalnızca
    # sembolün duyurudan sonraki **ilk** girişi (aynı sembolün tekrar girişleri sayılmaz).
    ay_baslangic = {
        ay: int(np.searchsorted(zamanlar, pd.Period(ay, freq="M").to_timestamp().value // 10**6))
        for ay in sorted(set(tablo["ay"]))
    }
    uye_aylari: dict[str, list[str]] = (
        tablo.groupby("sembol")["ay"].apply(lambda s: sorted(set(s))).to_dict()
    )
    medyan_onbellek: dict[int, np.ndarray] = dict(medyanlar)
    kor: list[float] = []
    kor_gun: list[float] = []
    # Seçim yanlılığı kontrolü: aynı duyurular, **sabit** 720 barlık (30 gün) ufukla, iki
    # gruba ayrılmış. "Sonradan evrene girdi" grubu, tam da girdiği için seçilmiştir —
    # evrene giriş ölçütü hacimdir ve hacim sıçraması fiyat sıçramasıyla gelir. Grupları
    # ayırmadan okunan bir "kör pencere getirisi" bu mekanizmayı alfa sanır.
    SABIT = 720
    sabit_med = medyan_onbellek.setdefault(SABIT, _kesit_medyan(logc, uye, SABIT))
    girdi: list[float] = []
    girmedi: list[float] = []
    giris_olaylari = ("spot_listeleme", "vadeli_listeleme", "marjin_ekleme")
    for _, r in o[o["olay"].isin(giris_olaylari)].iterrows():
        p, b0 = str(r["parite"]), int(r["bar"])
        i = sira[p]
        if uye[i, min(b0, uye.shape[1] - 1)]:
            continue  # zaten üyeydi: kör pencere yok
        sonraki = [ay_baslangic[a] for a in uye_aylari.get(p, []) if ay_baslangic[a] > b0]
        if b0 + SABIT < zamanlar.size and np.isfinite(sabit_med[b0]):
            g = float(logc[i, b0 + SABIT] - logc[i, b0] - sabit_med[b0])
            if np.isfinite(g):
                (girdi if sonraki else girmedi).append(g)
        if not sonraki:
            continue
        b1 = min(sonraki)
        if b1 >= zamanlar.size or not np.isfinite(logc[i, b0]) or not np.isfinite(logc[i, b1]):
            continue
        h = b1 - b0
        if h not in medyan_onbellek:
            medyan_onbellek[h] = _kesit_medyan(logc, uye, h)
        med = medyan_onbellek[h][b0]
        if not np.isfinite(med):
            continue
        kor.append(float(logc[i, b1] - logc[i, b0] - med))
        kor_gun.append(h / 24.0)
    rapor["kor_pencere"] = {
        "aciklama": "Duyurudan, sembolun evrene girdigi ilk ay basina kadar goreli log getiri "
                    "(evren medyani cikarilmis). Kiyasin yapisi geregi kacirdigi pencere.",
        "pencere": "in_sample",
        "goreli_getiri": _ozet(np.array(kor, dtype=float)),
        "uzunluk_gun": _ozet(np.array(kor_gun, dtype=float)),
        "secim_yanliligi_kontrolu": {
            "aciklama": "Ayni duyurular, sabit 720 bar (30 gun) ufuk. Fark yanliligin kendisi: "
                        "'sonradan girdi' grubu girdigi icin secilmistir.",
            "ufuk_bar": SABIT,
            "sonradan_girdi": _ozet(np.array(girdi, dtype=float)),
            "hic_girmedi": _ozet(np.array(girmedi, dtype=float)),
        },
    }
    rapor["coklu_karsilastirma"] = {
        "uyari": "Bu dosyada olay tipi x ufuk x kol seklinde cok sayida karsilastirma var; "
                 "tek bir p-degeri kapi degildir. Bir program acilirsa hipotez ONCE deftere "
                 "yazilir ve kapi esigi coklu testle olculur (K-039, K-044).",
        "karsilastirma_sayisi": len(UFUKLAR) * 2 * len(set(o["olay"])),
    }

    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    CIKTI.write_text(json.dumps(rapor, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"yazildi: {CIKTI}")
    print(f"IS bitişi: {rapor['kapsam']['is_bitis']} (bar {IS_BITIS_BAR})")
    nan = float("nan")
    for olay, satir in sorted(tablo_olay.items(), key=lambda x: -x[1]["n_olay"]):
        for kol in ("uye", "uye_degil"):
            par = " | ".join(
                f"h{h}: n={satir[f'h{h}'][kol].get('n', 0)}"
                f" med={satir[f'h{h}'][kol].get('medyan', nan):+.4f}"
                f" poz={satir[f'h{h}'][kol].get('pozitif_oran', nan):.3f}"
                f" p={satir[f'h{h}'][kol].get('isaret_p', nan):.3f}"
                for h in UFUKLAR
            )
            print(f"  {olay:18s} {kol:10s} {par}")
    k = rapor["kor_pencere"]
    print(f"  kor pencere: n={k['goreli_getiri'].get('n', 0)}"
          f" goreli medyan={k['goreli_getiri'].get('medyan', nan):+.4f}"
          f" poz={k['goreli_getiri'].get('pozitif_oran', nan):.3f}"
          f" p={k['goreli_getiri'].get('isaret_p', nan):.3f}"
          f" uzunluk medyan={k['uzunluk_gun'].get('medyan', nan):.1f} gun")
    return 0


if __name__ == "__main__":
    sys.exit(main())
