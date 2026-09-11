"""Funding rate: indirme, depolama ve bar hizalaması. (K-042, Spike 5)

BTC/USDT perpetual'ın funding oranı, Faz 4'e dönüş 3'ün **tek** yeni bilgi kaynağı. Spike 5
diğer üç adayı (open interest, long/short oranı, taker hacmi) eledi: Binance onları ~31 gün
saklıyor ve walk-forward kurulamıyor.

**Funding bir maliyet değil, bir bilgidir.** Sistem spot işlem yapıyor; spot'ta funding
ödenmez. Maliyet modeline (K-016, K-021, K-025) dokunulmuyor. Bu cümle burada yazılı çünkü
sezgiye ters: "funding" kelimesi bir ödemeyi çağrıştırıyor ve bir gün biri onu maliyet
modeline eklerse backtest sonuçları sessizce bozulur.

**Hizalamanın tek kuralı: `fundingTime <= bar_acilisi`.** `fundingTime` ödemenin
*gerçekleştiği* andır, ilan edildiği an değil. `t` barı yalnızca o ana kadar **gerçekleşmiş**
ödemeleri görebilir. 8 saatlik bir seriyi 1 saatlik barlara yaymak, yön yanlış seçilirse
gelecekten bilgi sızdırır — ve sızıntı sessizdir: hiçbir şey çökmez, backtest sadece fazla
iyi çıkar. K-002'nin kapattığı hata sınıfı tam olarak bu.

`merge_asof(direction="backward")` bu kuralın kendisi: her bara, zamanı o bardan **büyük
olmayan** en son funding kaydını verir. Eşitlik durumu (`fundingTime == bar_acilisi`) dahil
ve doğru — o anda ödeme gerçekleşmiştir.

**Isınma penceresinde `NaN` bırakılır, uydurulmaz** (K-024'ün "boşluk uydurulmaz" kuralı).
Funding 2019-09-10'da başlıyor, 1h veri seti 2021-06-28'de; yani pratikte ısınma boşluğu
yok, ama kural veriye değil sözleşmeye ait.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Final

import pandas as pd
import requests

from scryne_quant.exchange.binance import ipv4_zorla

#: Funding geçmişi spot host'unda yok; türev API'sinde. Spike 5: erişilebilir, 451 yok.
FUTURES_HOST: Final = "https://fapi.binance.com"
FUNDING_YOLU: Final = "/fapi/v1/fundingRate"

#: Sayfa başına azami kayıt (Binance sınırı).
SAYFA_BOYU: Final = 1_000

#: Ölçülen periyot: medyan 8,0 saat, 7.675 kaydın **hiçbiri** bunun dışında değil (Spike 5).
PERIYOT_MS: Final = 8 * 3_600_000

#: Sapma toleransı: bu kadar milisaniyeden fazla sapan aralık anomali sayılır.
#: 1 dakika, ölçülen sapmanın (0) çok üstünde ama periyodun binde ikisi.
PERIYOT_TOLERANS_MS: Final = 60_000

#: Binance funding tavanı ±%0,3. Dışına taşan bir değer veri hatasıdır, piyasa olayı değil.
ORAN_TAVANI: Final = 0.003

#: Sayfalamanın başlangıcı. 2017-07-14; funding'den (2019-09) önce, yani tüm geçmiş gelir.
GECMIS_BASI_MS: Final = 1_500_000_000_000

VARSAYILAN_DEPO: Final = Path("data/funding")

TIMEOUT_S: Final = 20.0
DENEME_SAYISI: Final = 5
BEKLEME_TABANI_S: Final = 1.0

#: Depodaki kanonik sütunlar.
#:
#: `markPrice` **bilerek alınmıyor.** Yanıtta var ama geçmişin bir kısmında boş string
#: geliyor (ölçüldü: 2026-09-11, eski kayıtlar). Kullanmadığımız ve bir bölümü eksik olan
#: bir alanı depoda tutmak, ileride birini onu güvenilir sanıp kullanmaya davet eder —
#: ve o gün eksikliği bir NaN olarak değil, bir sıfır olarak fark edilir.
SUTUNLAR: Final[tuple[str, ...]] = ("funding_time", "funding_rate")


class FundingHatasi(ValueError):
    """Funding verisi sözleşmeyi sağlamıyor."""


def indir(
    sembol: str = "BTCUSDT",
    *,
    baslangic_ms: int = GECMIS_BASI_MS,
    oturum: Any = None,
    ipv4: bool = True,
) -> pd.DataFrame:
    """Tüm funding geçmişini çeker. İleri yönlü sayfalama, `startTime` ile.

    Geriye doğru sayfalamak (`endTime`) denendi ve **çalışmıyor**: `startTime=0` en eski
    kaydı değil en yenisini döndürüyor (Spike 5). İleri yönlü sayfalama tek güvenilir yol.

    Kapanmamış bar sorunu (K-015/1) burada **yok**: funding bir ödeme olayıdır, oluştuktan
    sonra değişmez. O yüzden ek bir filtreye gerek kalmıyor — ama bu durumun sebebi yazılı
    olmalı, yoksa eksikliği bir unutma gibi görünür.
    """
    if ipv4 and oturum is None:
        ipv4_zorla()
    s = oturum if oturum is not None else requests.Session()

    kayitlar: list[dict[str, Any]] = []
    imlec = baslangic_ms
    while True:
        sayfa = _sayfa(s, sembol, imlec)
        if not sayfa:
            break
        kayitlar.extend(sayfa)
        if len(sayfa) < SAYFA_BOYU:
            break
        imlec = int(sayfa[-1]["fundingTime"]) + 1

    if not kayitlar:
        raise FundingHatasi(f"{sembol}: funding kaydı gelmedi")
    return _cerceve(kayitlar)


def _sayfa(oturum: Any, sembol: str, baslangic_ms: int) -> list[dict[str, Any]]:
    son: Exception | None = None
    for deneme in range(DENEME_SAYISI):
        try:
            yanit = oturum.get(
                f"{FUTURES_HOST}{FUNDING_YOLU}",
                params={
                    "symbol": sembol,
                    "startTime": baslangic_ms,
                    "limit": SAYFA_BOYU,
                },
                timeout=TIMEOUT_S,
            )
        except requests.exceptions.RequestException as hata:
            son = hata
        else:
            if yanit.status_code == 200:
                return list(yanit.json())
            son = FundingHatasi(f"borsa {yanit.status_code}: {yanit.text[:200]}")
        if deneme + 1 < DENEME_SAYISI:
            time.sleep(BEKLEME_TABANI_S * (2**deneme))
    raise FundingHatasi(f"funding sayfası alınamadı ({baslangic_ms}): {son}")


def _cerceve(kayitlar: list[dict[str, Any]]) -> pd.DataFrame:
    """Ham kayıtları kanonik çerçeveye çevirir: tekilleştirilmiş, sıralı, tipli.

    Kanonikleştirme **burada** yapılıyor, doğrulamada değil: depoya giren şeyin biçimi
    tektir, ve doğrulama o biçimi varsayabilmeli (`data/depo.py` ile aynı ayrım).
    """
    df = pd.DataFrame(kayitlar)
    eksik = {"fundingTime", "fundingRate"} - set(df.columns)
    if eksik:
        raise FundingHatasi(f"yanıtta eksik alan: {', '.join(sorted(eksik))}")
    out = pd.DataFrame(
        {
            "funding_time": df["fundingTime"].astype("int64"),
            "funding_rate": pd.to_numeric(df["fundingRate"], errors="raise").astype(
                "float64"
            ),
        }
    )
    return (
        out.drop_duplicates("funding_time")
        .sort_values("funding_time")
        .reset_index(drop=True)
    )


def dogrula(df: pd.DataFrame) -> dict[str, Any]:
    """Kalite raporu üretir. Bozukluk bulursa **hata verir**, düzeltmez.

    Faz 1'in doğrulama katmanıyla aynı felsefe (K-006): bayrak borsanın beyanı değil bizim
    kararımız, ve sessizce onarılan bir veri bir daha sorgulanmaz. Spike 5 bu veride sıfır
    anomali ölçtü — ama Spike 2 de gerçek veride anomali bulamamış, Faz 1 pencereyi
    genişletince üç boşluk çıkmıştı. Dar pencerede görünmeyen şey yok değildir.
    """
    if df.empty:
        raise FundingHatasi("boş funding çerçevesi")
    eksik = [s for s in SUTUNLAR if s not in df.columns]
    if eksik:
        raise FundingHatasi(f"eksik sütun(lar): {', '.join(eksik)}")

    zaman = df["funding_time"].to_numpy()
    if (zaman[1:] <= zaman[:-1]).any():
        raise FundingHatasi("funding_time artan ve tekil olmalı")

    oran = df["funding_rate"]
    if oran.isna().any():
        raise FundingHatasi(f"{int(oran.isna().sum())} kayıtta funding_rate boş")
    tasan = oran[oran.abs() > ORAN_TAVANI + 1e-12]
    if len(tasan):
        raise FundingHatasi(
            f"{len(tasan)} kayıt ±{ORAN_TAVANI} tavanının dışında (ilk: {tasan.iloc[0]}). "
            f"Bu bir piyasa olayı değil, veri hatasıdır."
        )

    fark = zaman[1:] - zaman[:-1]
    anormal = [
        (int(zaman[i]), int(f))
        for i, f in enumerate(fark)
        if abs(int(f) - PERIYOT_MS) > PERIYOT_TOLERANS_MS
    ]
    return {
        "kayit": int(len(df)),
        "ilk_ms": int(zaman[0]),
        "son_ms": int(zaman[-1]),
        "kapsam_gun": float((zaman[-1] - zaman[0]) / 86_400_000),
        "periyot_medyan_saat": float(pd.Series(fark).median() / 3_600_000),
        "anormal_aralik": len(anormal),
        "anormal_ornekler": anormal[:5],
        "oran_min": float(oran.min()),
        "oran_max": float(oran.max()),
        "oran_medyan": float(oran.median()),
    }


def yaz(df: pd.DataFrame, sembol: str, *, depo: Path = VARSAYILAN_DEPO) -> Path:
    """Parquet'e yazar (zstd). Faz 1'in depo sözleşmesiyle aynı: sembol başına tek dosya."""
    depo.mkdir(parents=True, exist_ok=True)
    yol = depo / f"{sembol}.parquet"
    df.to_parquet(yol, engine="pyarrow", compression="zstd", index=False)
    return yol


def oku(sembol: str = "BTCUSDT", *, depo: Path = VARSAYILAN_DEPO) -> pd.DataFrame:
    yol = depo / f"{sembol}.parquet"
    if not yol.is_file():
        raise FundingHatasi(
            f"funding verisi yok: {yol}. Önce `sq funding indir {sembol}` çalıştır."
        )
    return pd.read_parquet(yol)


def barlara_hizala(
    barlar: pd.DataFrame, funding: pd.DataFrame, *, sutun: str = "funding"
) -> pd.DataFrame:
    """Funding serisini bar çerçevesine **nedensel** olarak ekler. (K-002, K-042/4)

    Her bara, `funding_time <= open_time` olan **en son** kaydı verir. Eşitlik dahil: o
    anda ödeme gerçekleşmiştir.

    Dönen çerçeve girdiye dokunmaz, kopyadır — bar çerçevesi hem özellik hesabına hem
    `ctx`'e gidiyor ve yerinde değiştirmek sessizce her yere yayılırdı
    (`features/barlar.py` ile aynı gerekçe).

    Isınma penceresinde (ilk funding kaydından önceki barlar) değer `NaN` kalır.
    Uydurulmaz — `ctx.hazir()` o barları zaten eler.
    """
    if sutun in barlar.columns:
        raise FundingHatasi(f"bar çerçevesinde `{sutun}` sütunu zaten var")
    if barlar.empty:
        raise FundingHatasi("boş bar çerçevesi")
    dogrula(funding)

    sol = barlar.sort_values("open_time")
    sag = funding[["funding_time", "funding_rate"]].sort_values("funding_time")

    birlesik = pd.merge_asof(
        sol,
        sag.rename(columns={"funding_time": "open_time", "funding_rate": sutun}),
        on="open_time",
        direction="backward",
        allow_exact_matches=True,
    )
    return birlesik.reset_index(drop=True)


__all__ = [
    "GECMIS_BASI_MS",
    "ORAN_TAVANI",
    "PERIYOT_MS",
    "SUTUNLAR",
    "VARSAYILAN_DEPO",
    "FundingHatasi",
    "barlara_hizala",
    "dogrula",
    "indir",
    "oku",
    "yaz",
]
