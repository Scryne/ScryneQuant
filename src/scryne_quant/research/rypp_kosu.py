"""RYPP koşusunun saf hesapları: kripto OOS girdisi ve B-3 bağımsız veride aynı kural. (K-130)

Koşu aracı `tools/rypp_kos.py` motoru çalıştırır ve dosyaları yazar; bu modül yalnız hesaplar
(I/O yok, testli). İki yol:

- **Kripto (ana kanıt):** motorun gerçek özkaynakları (strateji, kıyas, 2x maliyetli strateji) P1/P2/
  S1/R'ler için; P3 plasebosu için stratejinin **zamanlama takvimi** (`g_t` ∈ {0, 1}: risk açık mı)
  kıyasın bar getirisine uygulanır ve dairesel kaydırılır (`risk_protokolu.plasebo_mar`, tek boyut).
  Aday kıyastan yalnız zamanlamayla ayrıldığı için doğru sıfır noktası budur: aynı işlem sayısı,
  aynı tutma süreleri, aynı maruziyet bütçesi, aynı maliyet, rastgele zaman.
- **Bağımsız veri (French, K-128/4 eşleme sözleşmesi):** enstrümanlar 12 VW sektör; kıyas eşit
  ağırlık, stratejinin brüt tavanında (1,0), aynı dengeleme takvimi; kripto parametreleri **takvim
  süresi** olarak taşınır (bar/24 gün × 252/365,25); rejim sinyali piyasa endeksi (Mkt-RF + RF)
  kendi ortalamasının üstünde mi; karar gün kapanışında, pozisyon ertesi gün kapanışında kurulur ve
  sonraki günün getirisini alır (gecikme 2, K-124: veri yalnız getiri); maliyet taraf başı 5 bps;
  epizot eşiği 0,10; nakit getirisi 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

import numpy as np
import pandas as pd

from scryne_quant.research import risk_protokolu as rp

#: K-128/4 eşleme sözleşmesi (bağımsız veri). Değişikliği yeni K ister.
SEKTOR_MALIYET_BPS: Final = 5.0
EPIZOT_HISSE: Final = 0.10
EPIZOT_KRIPTO: Final = 0.20
YIL_GUN: Final = 252.0
KRIPTO_YIL_BAR: Final = 24 * 365.25
GECIKME_GUN: Final = 2
PLASEBO_ORNEK: Final = 500


def takvim_gunu(bar_1h: int) -> int:
    """1h bar sayısını aynı takvim süresindeki işlem günü sayısına çevirir (en az 1)."""
    return max(1, int(round(bar_1h / 24 * YIL_GUN / 365.25)))


@dataclass(frozen=True)
class Esleme:
    """Kripto kuralının bağımsız verideki karşılığı (işlem günü cinsinden)."""

    rejim_gun: int
    kontrol_gun: int
    dengele_gun: int
    maliyet_bps: float = SEKTOR_MALIYET_BPS

    @classmethod
    def kripto_parametrelerinden(cls, p: dict[str, Any]) -> Esleme:
        return cls(rejim_gun=takvim_gunu(int(p["rejim_pencere"])),
                   kontrol_gun=takvim_gunu(int(p["kontrol_bar"])),
                   dengele_gun=takvim_gunu(int(p["yeniden_dengele_bar"])))

    def sozluk(self) -> dict[str, Any]:
        return {"rejim_gun": self.rejim_gun, "kontrol_gun": self.kontrol_gun,
                "dengele_gun": self.dengele_gun, "maliyet_bps": self.maliyet_bps,
                "gecikme_gun": GECIKME_GUN, "epizot_esigi": EPIZOT_HISSE,
                "yil_gun": YIL_GUN, "brut": 1.0, "nakit_getirisi": 0.0}


def sektor_kiyasi(getiri: np.ndarray, dengele_gun: int, maliyet_orani: float) -> np.ndarray:
    """Eşit ağırlıklı sektör portföyünün günlük net getirisi; her `dengele_gun`de eşite döner,
    arada ağırlıklar kayar. Dengeleme devri (|Δw| toplamı) × `maliyet_orani` düşülür. İlk gün
    kuruluş (devir 1,0) maliyetlidir."""
    r = np.asarray(getiri, dtype=np.float64)
    t, n = r.shape
    esit = np.full(n, 1.0 / n)
    w = np.zeros(n)
    out = np.empty(t)
    for i in range(t):
        devir = 0.0
        if i % dengele_gun == 0:
            devir = float(np.abs(esit - w).sum())
            w = esit.copy()
        brut = float(w @ r[i])
        out[i] = brut - devir * maliyet_orani
        deger = w * (1.0 + r[i])
        w = deger / deger.sum() if deger.sum() > 0 else esit.copy()
    return out


def piyasa_rejimi(piyasa_getiri: np.ndarray, rejim_gun: int, kontrol_gun: int) -> np.ndarray:
    """Gün `t` kapanışında risk açık mı: piyasa endeksi son `rejim_gun` günün basit ortalamasının
    üstünde mi. Karar her `kontrol_gun`de güncellenir, arada korunur. Ortalama ısınmadan `False`."""
    seviye = np.cumprod(1.0 + np.asarray(piyasa_getiri, dtype=np.float64))
    ort = pd.Series(seviye).rolling(rejim_gun, min_periods=rejim_gun).mean().to_numpy()
    ham = np.where(np.isnan(ort), False, seviye > ort)
    out = np.zeros_like(ham, dtype=bool)
    durum = False
    for i in range(len(ham)):
        if i % kontrol_gun == 0:
            durum = bool(ham[i])
        out[i] = durum
    return out


def gecikmeli(g: np.ndarray, gecikme: int) -> np.ndarray:
    """`g`yi `gecikme` gün kaydırır: gün `t`nin getirisini `t − gecikme` kapanışındaki karar alır."""
    out = np.zeros(len(g), dtype=np.float64)
    out[gecikme:] = np.asarray(g, dtype=np.float64)[: len(g) - gecikme]
    return out


def zamanlanmis_getiri(r_kiyas: np.ndarray, g: np.ndarray, maliyet_orani: float) -> np.ndarray:
    """Kıyası `g` oranında taşıyan stratejinin getirisi; geçişte devir × maliyet."""
    devir = np.abs(np.diff(g, prepend=0.0))
    return g * r_kiyas - devir * maliyet_orani


def ozkaynak(getiri: np.ndarray) -> np.ndarray:
    return np.concatenate([[1.0], np.cumprod(1.0 + np.asarray(getiri, dtype=np.float64))])


def bagimsiz_girdi(
    cerceve: pd.DataFrame, esleme: Esleme, *, aile_sayisi: int, aile_program: str,
    sektorler: tuple[str, ...], tohum: int = 0,
) -> tuple[rp.RyppGirdisi, dict[str, Any]]:
    """French çerçevesinden (getiriler kesir) RYPP girdisi. Ölçüm, rejim ısındıktan ve gecikme
    dolduktan sonra başlar; strateji ve kıyas aynı günlerde ölçülür."""
    r_sek = cerceve[list(sektorler)].to_numpy(dtype=np.float64)
    piyasa = (cerceve["Mkt-RF"] + cerceve["RF"]).to_numpy(dtype=np.float64)
    m1, m2 = esleme.maliyet_bps / 1e4, 2 * esleme.maliyet_bps / 1e4
    r_k1 = sektor_kiyasi(r_sek, esleme.dengele_gun, m1)
    r_k2 = sektor_kiyasi(r_sek, esleme.dengele_gun, m2)
    g = gecikmeli(piyasa_rejimi(piyasa, esleme.rejim_gun, esleme.kontrol_gun), GECIKME_GUN)
    bas = esleme.rejim_gun + GECIKME_GUN
    rk, rk2, gg = r_k1[bas:], r_k2[bas:], g[bas:]
    s1 = zamanlanmis_getiri(rk, gg, m1)
    s2 = zamanlanmis_getiri(rk2, gg, m2)
    girdi = rp.RyppGirdisi(
        strateji=ozkaynak(s1), kiyas=ozkaynak(rk), strateji_2x_maliyet=ozkaynak(s2),
        yil_bar=YIL_GUN, epizot_esigi=EPIZOT_HISSE,
        plasebo=rp.plasebo_mar(rk, gg, maliyet_orani=m1, yil_bar=YIL_GUN, ornek=PLASEBO_ORNEK,
                               tohum=tohum),
        aile_sayisi=aile_sayisi, aile_program=aile_program, tohum=tohum,
    )
    tarih = cerceve["tarih"].to_numpy()
    meta = {"esleme": esleme.sozluk(), "olcum_ilk": int(tarih[bas]), "olcum_son": int(tarih[-1]),
            "gun": int(len(tarih) - bas), "risk_acik_orani": float(gg.mean()),
            "gecis": int(np.abs(np.diff(gg)).sum())}
    return girdi, meta


def kripto_girdi(
    strateji: Any, kiyas: Any, strateji_2x: Any, *, maliyet_orani: float, aile_sayisi: int,
    aile_program: str, tohum: int = 0,
) -> tuple[rp.RyppGirdisi, dict[str, Any]]:
    """Motor sonuçlarından (`Sonuc`) RYPP girdisi. Seriler aynı barlarda olmalı."""
    if not np.array_equal(strateji.zamanlar, kiyas.zamanlar) or not np.array_equal(
        strateji.zamanlar, strateji_2x.zamanlar
    ):
        raise rp.ProtokolHatasi("strateji, kıyas ve 2x koşusu aynı barlarda değil")
    oz_k = np.asarray(kiyas.ozkaynak, dtype=np.float64)
    r_k = np.diff(oz_k) / oz_k[:-1]
    oz_s = np.asarray(strateji.ozkaynak, dtype=np.float64)
    # Zamanlama takvimi: bar kapanışında brüt maruziyet (motor bunu **kesir** olarak verir,
    # `PortfoyDurumu.brut_maruziyet`, [0, 1]) > 0,5 → risk açık. Bar `t`nin getirisini
    # (`t−1` → `t`) `t` barında tutulan pozisyon alır; `t` kapanışındaki maruziyet o.
    # K-131: ilk sürüm kesri bir de özkaynağa bölüyordu → takvim hep 0, P3 anlamsızdı.
    maruz = np.asarray(strateji.maruziyet, dtype=np.float64)
    if np.nanmax(maruz, initial=0.0) > 1.5:
        raise rp.ProtokolHatasi("maruziyet kesir değil (> 1,5): birim sözleşmesi bozuk")
    g = (np.nan_to_num(maruz, nan=0.0) > 0.5).astype(np.float64)[1:]
    if strateji.metrikler.islem_sayisi > 0 and not g.any():
        raise rp.ProtokolHatasi("strateji işlem yaptı ama zamanlama takvimi hep kapalı: "
                                "takvim çıkarımı bozuk (K-131)")
    plasebo = rp.plasebo_mar(r_k, g, maliyet_orani=maliyet_orani, yil_bar=KRIPTO_YIL_BAR,
                             ornek=PLASEBO_ORNEK, tohum=tohum)
    girdi = rp.RyppGirdisi(
        strateji=oz_s, kiyas=oz_k, strateji_2x_maliyet=np.asarray(strateji_2x.ozkaynak, float),
        yil_bar=KRIPTO_YIL_BAR, epizot_esigi=EPIZOT_KRIPTO, plasebo=plasebo,
        aile_sayisi=aile_sayisi, aile_program=aile_program, tohum=tohum,
    )
    dogrusal = rp.olc(ozkaynak(zamanlanmis_getiri(r_k, g, maliyet_orani)), KRIPTO_YIL_BAR)
    motor = rp.olc(oz_s, KRIPTO_YIL_BAR)
    meta = {"bar": int(len(r_k)), "risk_acik_orani": float(g.mean()),
            "gecis": int(np.abs(np.diff(g)).sum()),
            "dogrusal_model_mar": dogrusal.mar, "motor_mar": motor.mar,
            "plasebo_gercek_mar": float(plasebo[0])}
    return girdi, meta


__all__ = [
    "EPIZOT_HISSE",
    "EPIZOT_KRIPTO",
    "GECIKME_GUN",
    "KRIPTO_YIL_BAR",
    "SEKTOR_MALIYET_BPS",
    "YIL_GUN",
    "Esleme",
    "bagimsiz_girdi",
    "gecikmeli",
    "kripto_girdi",
    "ozkaynak",
    "piyasa_rejimi",
    "sektor_kiyasi",
    "takvim_gunu",
    "zamanlanmis_getiri",
]
