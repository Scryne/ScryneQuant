"""Faz 12 program kayıtlarının kaynak ölçüsü (K-051/2). **Elle çalıştırılır.**

    uv run python tools/faz12_kaynak_olcumu.py

K-045 tek sembollü (BTCUSDT) yönlü aramayı kapattı; istisnası *"ölçüyle gerekçelendirilmiş
belirgin biçimde farklı bir bilgi kaynağı"*. `ProgramKaydi.kaynak_olcumu` bu ölçüyü ister.
Bu araç iki program için onu üretir:

- **kesitsel** — evren içi fiyat kesiti. Soru: evren üyelerinin günlük getiri varyansının
  ne kadarı BTC'nin kendi serisiyle açıklanamıyor? Açıklanamayan pay, K-045'in kapattığı
  kaynağın **göremediği** bilgi.
- **turev** — evren geneli funding. Soru: üyelerin funding'i BTC funding'inden (K-042'nin
  kapattığı tek-sembol türev kaynağı) ne kadar bağımsız, ve fiyat kesitinden ne kadar
  farklı bir sıralama veriyor?

## Bu araç bir çekiliş değildir — ve sınırı yazılı

**İleriye dönük hiçbir getiriye bakmaz.** Bütün istatistikler eşzamanlı (aynı gün) veya
geriye dönük: R², temel bileşen payı, kesit sapması, eşzamanlı sıra korelasyonu. Hiçbir
kural, sinyal veya getiri tahmini sınanmıyor; Spike 5'in "verinin kendisini ölç" kalıbı.
Bir sinyalin **gelecek getiriyle** ilişkisine bakan her şey çekiliştir ve program kaydından
sonra, bütçeden düşerek koşar (K-039).

Bir kaynağın farklı olması onun **değerli** olduğunu göstermez. Bu ölçü yalnızca K-045'in
istisna şartını sayıya bağlar; edge hakkında hiçbir şey söylemez.

## Kurallar

- Evren üyeliği PIT tablosundan, ay ay (K-052/3). Bugünkü listeden kurulmaz.
- Günlük kapanış = UTC 23:00 açılışlı 1h barın kapanışı, yalnızca `quality_status == ok`.
  Eksik gün uydurulmaz; getiri yalnızca ardışık iki gün de varsa hesaplanır.
- Kimlik kırılması şüphesi olan sembol-aylar (katalogdaki `kirilmalar`) dışarıda.
- Funding günlük toplamdır (aralık 8/4/1 saat olabilir; toplam günlük taşıma maliyetidir).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from scryne_quant.common.hash import dosya_hash, git_durumu
from scryne_quant.common.zaman import simdi_ms, utc_str

KOK = Path(__file__).resolve().parent.parent
EVREN = KOK / "data" / "evren"
TABLO = EVREN / "_evren" / "27b7a16ed0ed.parquet"
TABLO_OZET = EVREN / "_evren" / "27b7a16ed0ed.json"
FUNDING = KOK / "data" / "turev" / "funding"
MAKRO = KOK / "data" / "makro"
CIKTI = KOK / "runs" / "faz12" / "kaynak-olcumu.json"
MAKRO_CIKTI = KOK / "runs" / "faz12" / "kaynak-olcumu-makro.json"
#: Tam geçmişi olan seriler (2017'den beri vintage). DTWEXBGS'in vintage'ı 2019-02'de,
#: BAMLH0A0HYM2'ninki 2023-09'da başlıyor; onlar ayrı raporlanıyor, regresyona girmiyor.
MAKRO_TAM = ("VIXCLS", "DGS10", "T10Y2Y", "NFCI")
MAKRO_KISA = ("DTWEXBGS", "BAMLH0A0HYM2")

GUN_MS = 86_400_000
#: Aylık regresyon için asgari ortak gün. Bir ay 28-31 gün; 15'in altı gürültü.
ASGARI_GUN = 15
#: Kesitsel istatistik için asgari üye. Evrenin ilk ayları 1-10 üyeli.
ASGARI_UYE = 10
BTC = "BTCUSDT"


def _yuzdelik(x: list[float] | np.ndarray) -> dict[str, float | int]:
    a = np.asarray(x, dtype=float)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return {"n": 0}
    return {
        "n": int(a.size),
        "p10": float(np.percentile(a, 10)),
        "p25": float(np.percentile(a, 25)),
        "medyan": float(np.median(a)),
        "p75": float(np.percentile(a, 75)),
        "p90": float(np.percentile(a, 90)),
    }


def _gunluk_kapanis(sembol: str) -> pd.Series:
    df = pd.read_parquet(
        EVREN / sembol / "1h.parquet", columns=["open_time", "close", "quality_status"]
    )
    df = df[(df["quality_status"] == "ok") & (df["open_time"] % GUN_MS == 23 * 3_600_000)]
    gun = (df["open_time"] // GUN_MS).to_numpy()
    return pd.Series(np.log(df["close"].to_numpy()), index=gun, name=sembol)


def _gunluk_getiri(kapanis: pd.Series) -> pd.Series:
    fark = kapanis.diff()
    ardisik = pd.Series(kapanis.index, index=kapanis.index).diff() == 1
    return fark[ardisik]


def _ay_gunleri(ay: str) -> tuple[int, int]:
    bas = pd.Timestamp(f"{ay}-01", tz="UTC")
    son = bas + pd.offsets.MonthBegin(1)
    return int(bas.value // 10**6 // GUN_MS), int(son.value // 10**6 // GUN_MS)


def _kirik_aylar() -> set[tuple[str, str]]:
    ozet = json.loads(TABLO_OZET.read_text(encoding="utf-8"))
    kirik = set()
    for k in ozet.get("kirilmalar", []):
        for ms in (k["onceki_son_ms"], k["sonraki_ilk_ms"]):
            kirik.add((k["sembol"], pd.Timestamp(ms, unit="ms", tz="UTC").strftime("%Y-%m")))
    return kirik


def _r2(y: np.ndarray, x: np.ndarray) -> float:
    if y.std() == 0 or x.std() == 0:
        return float("nan")
    return float(np.corrcoef(y, x)[0, 1] ** 2)


def kesitsel(uyelik: pd.DataFrame, getiriler: dict[str, pd.Series], kirik: set) -> dict:
    btc = getiriler[BTC]
    idio, pc1, kesit_sd, aylar = [], [], [], 0
    for ay, grup in uyelik.groupby("ay"):
        bas, son = _ay_gunleri(str(ay))
        uyeler = [
            s for s in grup["sembol"] if s in getiriler and (s, ay) not in kirik and s != BTC
        ]
        if len(uyeler) < ASGARI_UYE:
            continue
        panel = pd.DataFrame(
            {s: getiriler[s][(getiriler[s].index >= bas) & (getiriler[s].index < son)]
             for s in uyeler}
        )
        b = btc[(btc.index >= bas) & (btc.index < son)]
        aylar += 1
        for s in uyeler:
            ortak = panel[s].dropna().index.intersection(b.index)
            if len(ortak) >= ASGARI_GUN:
                idio.append(1.0 - _r2(panel[s].loc[ortak].to_numpy(), b.loc[ortak].to_numpy()))
        tam = panel.dropna(axis=1, thresh=len(panel) - 1).dropna(axis=0)
        if tam.shape[1] >= ASGARI_UYE and tam.shape[0] >= ASGARI_GUN:
            oz = np.linalg.eigvalsh(np.corrcoef(tam.to_numpy().T))
            pc1.append(float(oz[-1] / oz.sum()))
        sd = panel.std(axis=1, ddof=1)
        kesit_sd.extend(sd[panel.count(axis=1) >= ASGARI_UYE].tolist())
    return {
        "soru": "Evren üyelerinin günlük getiri varyansının BTC ile açıklanamayan payı",
        "aylik_uye_regresyonu_1_eksi_r2": _yuzdelik(idio),
        "pc1_varyans_payi": _yuzdelik(pc1),
        "gunluk_kesit_sapmasi": _yuzdelik(kesit_sd),
        "btc_gunluk_sapma": float(btc.std(ddof=1)),
        "olculen_ay": aylar,
    }


def _gunluk_funding(sembol: str) -> pd.Series | None:
    yol = FUNDING / f"{sembol}.parquet"
    if not yol.exists():
        return None
    df = pd.read_parquet(yol)
    gun = df["calc_time"] // GUN_MS
    return df.groupby(gun)["last_funding_rate"].sum().rename(sembol)


def turev(uyelik: pd.DataFrame, getiriler: dict[str, pd.Series], kirik: set) -> dict:
    fundingler = {s: f for s in uyelik["sembol"].unique() if (f := _gunluk_funding(s)) is not None}
    if BTC not in fundingler:
        raise SystemExit("BTCUSDT funding yok — önce tools/faz12_funding_indir.py")
    btc = fundingler[BTC]
    idio, kesit_sd, sira_kor = [], [], []
    uye_ay, kapsanan = 0, 0
    for ay, grup in uyelik.groupby("ay"):
        bas, son = _ay_gunleri(str(ay))
        uyeler = [s for s in grup["sembol"] if (s, ay) not in kirik]
        uye_ay += len(uyeler)
        var = [s for s in uyeler if s in fundingler]
        kapsanan += len(var)
        b = btc[(btc.index >= bas) & (btc.index < son)]
        for s in var:
            if s == BTC:
                continue
            f = fundingler[s]
            f = f[(f.index >= bas) & (f.index < son)]
            ortak = f.index.intersection(b.index)
            if len(ortak) >= ASGARI_GUN:
                idio.append(1.0 - _r2(f.loc[ortak].to_numpy(), b.loc[ortak].to_numpy()))
        if len(var) < ASGARI_UYE:
            continue
        fp = pd.DataFrame({s: fundingler[s][(fundingler[s].index >= bas)
                                            & (fundingler[s].index < son)] for s in var})
        sd = fp.std(axis=1, ddof=1)
        kesit_sd.extend(sd[fp.count(axis=1) >= ASGARI_UYE].tolist())
        # Eşzamanlı/geriye dönük sıra: gün d funding sırası ↔ [d-6, d] toplam getiri sırası.
        gp = pd.DataFrame({s: getiriler[s] for s in var if s in getiriler})
        if gp.shape[1] < ASGARI_UYE:
            continue
        gp = gp.reindex(range(bas - 7, son)).rolling(7, min_periods=7).sum()
        for d in fp.index:
            if d not in gp.index:
                continue
            ikili = pd.concat([fp.loc[d], gp.loc[d]], axis=1, keys=["f", "g"]).dropna()
            if len(ikili) >= ASGARI_UYE:
                sira_kor.append(float(ikili["f"].rank().corr(ikili["g"].rank())))
    return {
        "soru": "Üyelerin funding'i BTC funding'inden ne kadar bağımsız, fiyat kesitinden "
        "ne kadar farklı sıralıyor",
        "kapsam_uye_ay_orani": kapsanan / uye_ay if uye_ay else None,
        "uye_ay": uye_ay,
        "perp_sembol": len(fundingler),
        "aylik_uye_regresyonu_1_eksi_r2": _yuzdelik(idio),
        "gunluk_kesit_sapmasi": _yuzdelik(kesit_sd),
        "btc_gunluk_funding_sapmasi": float(btc.std(ddof=1)),
        "funding_sirasi_ile_7g_getiri_sirasi_spearman": _yuzdelik(sira_kor),
    }


def _pit_seri(sid: str, gunler: np.ndarray) -> np.ndarray:
    """Gün `d`nin sonunda **bilinen** en son gözlem değeri (K-052/5).

    Bir vintage satırı `d`de görülebilir ⇔ `realtime_start ≤ d ≤ realtime_end`. Available
    time gün çözünürlüğünde ve gün sonuna yuvarlanıyor: `realtime_start` günü biten barın
    kapanışında değer bilinir, o günün içindeki bir barda bilinmez.
    """
    df = pd.read_parquet(MAKRO / f"{sid}.parquet").dropna(subset=["value"])
    def gun(x: pd.Series) -> np.ndarray:
        # Çözünürlükten bağımsız: pandas 3 tarih dizgesini µs'e çözebiliyor, `astype(int64)`
        # birimi sessizce değiştirirdi (ilk koşuda bütün günler eşleşmedi — ölçüldü).
        return ((pd.to_datetime(x) - pd.Timestamp("1970-01-01")) // pd.Timedelta(days=1)).to_numpy()

    bas, bit, gozlem = gun(df["realtime_start"]), gun(df["realtime_end"].replace(
        "9999-12-31", "2262-01-01")), gun(df["date"])
    deger = df["value"].to_numpy()
    out = np.full(gunler.size, np.nan)
    for k, d in enumerate(gunler):
        m = (bas <= d) & (bit >= d)
        if m.any():
            j = np.flatnonzero(m)[np.argmax(gozlem[m])]
            out[k] = deger[j]
    return out


def _revizyon(sid: str) -> dict:
    df = pd.read_parquet(MAKRO / f"{sid}.parquet").dropna(subset=["value"])
    ilk = df.sort_values("realtime_start").groupby("date")["value"].first()
    son = df.sort_values("realtime_start").groupby("date")["value"].last()
    fark = (son - ilk).abs()
    gecikme = (pd.to_datetime(df.groupby("date")["realtime_start"].min())
               - pd.to_datetime(ilk.index)).dt.days
    return {
        "gozlem": int(ilk.size),
        "revize_edilen_oran": float((fark > 1e-12).mean()),
        "medyan_mutlak_revizyon_bolu_sapma": float(fark.median() / son.std(ddof=1)),
        "p90_mutlak_revizyon_bolu_sapma": float(fark.quantile(0.9) / son.std(ddof=1)),
        "ilk_yayin_gecikmesi_gun": _yuzdelik(gecikme.to_numpy()),
    }


def makro() -> dict:
    btc = _gunluk_getiri(_gunluk_kapanis(BTC))
    gunler = np.arange(int(btc.index.min()), int(btc.index.max()) + 1)
    seviye = {sid: _pit_seri(sid, gunler) for sid in (*MAKRO_TAM, *MAKRO_KISA)}
    degisim = pd.DataFrame({sid: np.r_[np.nan, np.diff(v)] for sid, v in seviye.items()},
                           index=gunler)
    r = btc.reindex(gunler)
    panel = pd.concat([r.rename("btc"), r.shift(1).rename("btc_1"), degisim], axis=1)

    def r2(y: pd.Series, X: pd.DataFrame) -> tuple[float, int]:
        d = pd.concat([y, X], axis=1).dropna()
        # Değişmeyen günler (hafta sonu, tatil) regresyona girmez: orada makro gözlem yok.
        d = d[(d[X.columns].abs().sum(axis=1) > 0) if y.name == "btc" else d[y.name] != 0]
        A = np.c_[np.ones(len(d)), d[X.columns].to_numpy()]
        b = d[y.name].to_numpy()
        katsayi, *_ = np.linalg.lstsq(A, b, rcond=None)
        artik = b - A @ katsayi
        return float(1 - artik.var() / b.var()), int(len(d))

    btc_r2, btc_n = r2(panel["btc"], panel[list(MAKRO_TAM)])
    ters = {}
    for sid in (*MAKRO_TAM, *MAKRO_KISA):
        v, n = r2(panel[sid], panel[["btc", "btc_1"]])
        ters[sid] = {"1_eksi_r2": 1 - v, "gun": n}
    return {
        "soru": "Makro risk iştahı göstergelerinin günlük değişimi kripto fiyatından ne kadar "
        "üretilebiliyor; revizyon PIT'i ne kadar gerektiriyor",
        "btc_getirisi_makro_degisimle_r2": {"r2": btc_r2, "gun": btc_n, "seriler": list(MAKRO_TAM)},
        "makro_degisim_btc_getirisiyle_1_eksi_r2": ters,
        "revizyon": {sid: _revizyon(sid) for sid in (*MAKRO_TAM, *MAKRO_KISA)},
        "kisa_seriler": {
            "DTWEXBGS": "ALFRED vintage'ı 2019-02-04'te başlıyor; öncesi PIT değil",
            "BAMLH0A0HYM2": "FRED'de yalnızca 2023-09-18'den beri (lisans kısıtı); walk-forward "
            "kurulamaz, elendi",
        },
    }


def main() -> int:
    if "--makro" in sys.argv:
        govde = {
            "arac": "tools/faz12_kaynak_olcumu.py --makro",
            "ileriye_donuk_getiri": False,
            "makro": makro(),
            "uretildi": utc_str(simdi_ms()),
            "git": git_durumu(),
        }
        MAKRO_CIKTI.write_text(
            json.dumps(govde, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(govde["makro"], ensure_ascii=False, indent=1))
        return 0
    uyelik = pd.read_parquet(TABLO, columns=["ay", "sembol"])
    kirik = _kirik_aylar()
    getiriler = {}
    for s in sorted(uyelik["sembol"].unique()):
        if (EVREN / s / "1h.parquet").exists():
            getiriler[s] = _gunluk_getiri(_gunluk_kapanis(s))
    govde = {
        "arac": "tools/faz12_kaynak_olcumu.py",
        "ileriye_donuk_getiri": False,
        "tablo": str(TABLO.relative_to(KOK)),
        "tablo_sha256": dosya_hash(TABLO),
        "kirik_sembol_ay": len(kirik),
        "kesitsel": kesitsel(uyelik, getiriler, kirik),
        "turev": turev(uyelik, getiriler, kirik),
        "uretildi": utc_str(simdi_ms()),
        "git": git_durumu(),
    }
    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    CIKTI.write_text(
        json.dumps(govde, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: govde[k] for k in ("kesitsel", "turev")}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
