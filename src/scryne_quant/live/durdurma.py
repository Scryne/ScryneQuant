"""Süreçler arası **düzgün** durdurma isteği: bir bayrak dosyası. (Faz 6)

**Neden var.** `live/baslat.py` düzgün kapanışı `SIGINT`/`SIGTERM`e bağlamıştı ve o yol
bu koşunun gerçekte çalıştığı yerde — Windows'ta, bir zamanlanmış görevin altında —
ulaşılamaz: sinyali gönderecek bir terminal yok, ve başka bir sürecin konsol grubuna
`CTRL_BREAK` yollanamıyor. Geriye tek seçenek sert kill kalıyordu, ve sistem onu
(haklı olarak) `temiz_kapanmadi` diye kaydediyor — yani **kesinti** sayıyor.

Sonucu şuydu: kodu düzeltmek, makineyi güncellemek ya da diski değiştirmek için yapılan
her planlı yeniden başlatma, *"30 gün kesintisiz"* kriterine karşı bir kesinti olarak
yazılıyordu. Kriterin ölçmek istediği şey altyapının **beklenmedik** şekilde düşmesi;
planlı bir duruşu aynı kefeye koymak, 30 günü tek bir kesintisiz makine oturumuna
bağlamak olurdu.

**Neden bir dosya, neden bir HTTP ucu değil.** Dashboard salt okunur (`test_api.py`);
oraya koşuyu durduran bir uç koymak, arayüzü ölçümün üstünde bir yetkiye çıkarırdı.
Dosya ise kilidin (`live/kilit.py`) zaten kurduğu kalıbı izliyor: koşunun yanında yaşayan,
işletim sistemi düzeyinde, süreç kimliği gerektirmeyen bir iz.

**Bayrak bir istektir, bir kill değildir.** Koşturucu onu periyodik olarak yokluyor ve
kendi düzgün kapanış yolundan çıkıyor: bekleyen kontrol noktası yazılır, `durdu` satırı
sebebiyle birlikte kayda geçer, kilit bırakılır. Bayrağı silmek de kapanan sürecin işi —
kalırsa bir sonraki başlatma anında kendini durdururdu.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Final

from scryne_quant.common.zaman import simdi_ms, utc_str

#: Bayrak dosyasının uzantısı; koşu dosyasının yanında yaşıyor (`.gitignore`'da).
UZANTI: Final = ".dur"


def bayrak_yolu(kosu_yolu: str | Path) -> Path:
    yol = Path(str(kosu_yolu))
    return yol.with_suffix(yol.suffix + UZANTI)


def dur_iste(kosu_yolu: str | Path, *, sebep: str = "elle durduruldu") -> Path:
    """Düzgün durdurma ister. Sebep kayda geçsin diye dosyanın içinde taşınıyor.

    *"Kesinti olduysa sebebi kayıtlı"* kriterinin planlı duruştaki karşılığı bu: sebebi
    isteyen yazar, çünkü onu bilen tek taraf o. Süreç kendi kapanışına "bilinmiyor"
    yazmak zorunda kalmaz.
    """
    yol = bayrak_yolu(kosu_yolu)
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(
        json.dumps(
            {"sebep": sebep, "isteyen_pid": os.getpid(), "istendi_ms": simdi_ms()},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return yol


def istek(kosu_yolu: str | Path) -> dict[str, Any] | None:
    """Bekleyen durdurma isteği varsa ayrıntısı, yoksa `None`.

    Bozuk ya da yarım yazılmış bir dosya **istek sayılıyor**: bayrağın varlığı niyetin
    kendisi, içeriği yalnızca kaydın zenginliği. Ayrıştırılamayan bir dosyayı yok saymak,
    durdurma isteğini bir JSON ayrıntısına bağlamak olurdu.
    """
    yol = bayrak_yolu(kosu_yolu)
    if not yol.is_file():
        return None
    try:
        veri = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"sebep": "bilinmiyor (bayrak okunamadı)"}
    if not isinstance(veri, dict):
        return {"sebep": "bilinmiyor (bayrak beklenen biçimde değil)"}
    if "istendi_ms" in veri:
        veri["istendi_utc"] = utc_str(int(veri["istendi_ms"]))
    return veri


def temizle(kosu_yolu: str | Path) -> None:
    """Bayrağı siler. İki kez çağrılabilir."""
    bayrak_yolu(kosu_yolu).unlink(missing_ok=True)


__all__ = ["UZANTI", "bayrak_yolu", "dur_iste", "istek", "temizle"]
