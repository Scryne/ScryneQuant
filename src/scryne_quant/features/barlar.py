"""Bar DataFrame'i → numpy dizileri. **Bu paketteki tek pandas kullanıcısı.**

Ayrı bir modülde duruyor çünkü pandas dosya okuyabilen bir kütüphanedir
(`read_parquet`, `read_csv`). Strateji katmanının import edebildiği bir modülde bulunması,
K-003'ün kapattığı I/O yüzeyini dolaylı yoldan geri açardı. İzolasyon testi bu modülü
strateji için **yasaklı** kabul eder: `features.indikator` ve `features.motor` serbest,
`features.barlar` değil.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from scryne_quant.data.semalar import BAR_SUTUNLARI

#: Diziye çevrilirken float64'e zorlanan sütunlar.
SAYISAL: tuple[str, ...] = ("open", "high", "low", "close", "volume", "quote_volume")

#: **Opsiyonel** sayısal sütunlar: varsa diziye çevrilir, yoksa sessizce atlanır.
#:
#: `funding` kanonik bar şemasının parçası **değil** ve olmamalı: depodaki parquet
#: dosyaları Faz 1'de dondurulmuş ve dosya hash'i veri seti kimliğinin kendisi (K-009).
#: Şemaya sütun eklemek o kimliği değiştirir, yani Faz 1-6'nın bütün sonuç kayıtlarını
#: geçersiz kılardı. Bunun yerine funding, laboratuvar boru hattında çerçeveye
#: **eklenerek** geliyor (`data/funding.py::barlara_hizala`) ve burada varsa alınıyor.
#:
#: "Varsa al" davranışı yumuşak görünüyor ama sessiz değil: funding isteyen bir özellik,
#: alan yoksa `features/motor.py`'de açık bir hatayla karşılaşır.
EK_SAYISAL: tuple[str, ...] = (
    "funding",
    "funding_odeme",
    "basis",
    # Makro persentil alanları (Faz 12, `data/makro.py`): seri × önceden sabit pencere.
    *(f"{s}_p{w}" for s in ("vix", "nfci") for w in (30, 90, 180, 365)),
)


class BarHatasi(ValueError):
    """Bar çerçevesi motorun beklediği biçimde değil."""


def bar_dizileri(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """Kanonik bar çerçevesini salt-okunur numpy dizilerine çevirir.

    Diziler `writeable=False` işaretlenir: aynı diziler hem özellik hesabına hem `ctx`'e
    gidiyor, ve tek bir yerde yapılan yerinde değişiklik backtest'in her yerine sessizce
    yayılırdı.

    Sıra kontrol edilir, düzeltilmez. Sıralamayı burada sessizce onarmak, deponun
    kanonikleştirme sözleşmesini (bkz. `data/depo.py`) ikinci bir yere kopyalamak olurdu;
    bozuksa sebebi yukarıda aranmalı.
    """
    eksik = [s for s in BAR_SUTUNLARI if s not in df.columns]
    if eksik:
        raise BarHatasi(f"eksik sütun(lar): {', '.join(eksik)}")
    if df.empty:
        raise BarHatasi("boş bar çerçevesi")

    zaman = df["open_time"].to_numpy(dtype="int64")
    if np.any(np.diff(zaman) <= 0):
        raise BarHatasi("open_time artan ve tekil olmalı — depo dışından gelen veri mi?")

    out: dict[str, np.ndarray] = {"open_time": zaman}
    for sutun in SAYISAL:
        out[sutun] = df[sutun].to_numpy(dtype="float64")
    for sutun in EK_SAYISAL:
        if sutun in df.columns:
            out[sutun] = df[sutun].to_numpy(dtype="float64")
    out["trades"] = df["trades"].to_numpy(dtype="int64")
    out["quality_status"] = df["quality_status"].astype("string").to_numpy(dtype=object)

    for dizi in out.values():
        dizi.flags.writeable = False
    return out
