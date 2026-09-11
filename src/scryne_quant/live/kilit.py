"""Koşu kilidi: bir koşu dosyasını aynı anda **tek** süreç yazabilir. (Faz 6)

**Neden var:** `sq paper baslat` aynı koşu için iki kez çağrılabiliyordu ve hiçbir şey
engellemiyordu — zamanlanmış görev koşuyu tutarken elle bir `sq paper baslat` yazmak
yeterliydi. SQLite yazımları serileştirdiği için sonuç bir çökme **olmazdı**; tehlikeli
olan da bu. İki trader döngüsü aynı barları işleseydi fill defteri çiftlenir, kontrol
noktası birbirinin üstüne yazılır ve hata ancak bir sonraki toparlanmada, üstelik **yanlış
sebeple** ("portföy fill defteriyle ayrıştı") görünürdü. Yani sistemin en iyi teşhis aracı
yanlış yeri gösterirdi.

**Mekanizma: işletim sistemi düzeyinde tavsiye kilidi, veritabanı satırı değil.**
Bir `kilit` tablosuna pid yazmak cazipti ama yanlış: süreç çökünce satır kalır ve
"kilitli mi yoksa ölü mü" sorusu cevapsızdır — tam olarak `temiz_kapanmadi`nin
çözmek zorunda kaldığı problemin ikinci kopyası. İşletim sistemi kilidini ise süreç
öldüğünde çekirdek bırakır; bayat kilit diye bir durum yoktur.

Kilit koşu dosyasının yanında ayrı bir `.lock` dosyasında tutuluyor, SQLite dosyasının
kendisinde değil: SQLite'ın kendi kilitleme protokolüne müdahale etmek, WAL'ın çok
okuyuculu çalışmasını (dashboard) bozardı.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import TracebackType
from typing import Final

#: Kilit dosyasının uzantısı. Koşu dosyasının yanında yaşıyor ve `.gitignore`'da
#: (`runs/paper/` zaten dışlanmış).
UZANTI: Final = ".lock"

#: Kilit baytının dosyadaki yeri — içeriğin dışında, ki yazılan pid kilitli aralığa
#: düşmesin. **Bunun dış okuyucuya faydası yok ve bu ölçüldü:** Windows'ta dosyanın
#: kendisi başka bir süreç tarafından zaten açılamıyor (paylaşım kipi), bayt aralığı
#: kilidinden bağımsız olarak. Yani pid, kilit tutulurken dışarıdan okunamıyor.
#:
#: Pid yine de yazılıyor ama **ölüm sonrası** için: süreç gittikten sonra dosya okunabilir
#: hâle geliyor ve "en son kim tutuyordu" sorusu cevaplanabiliyor. Kilit **tutulurken**
#: sorulan sorunun cevabı zaten `KilitAlinamadi` mesajı.
KILIT_OFSETI: Final = 4096


class KilitAlinamadi(RuntimeError):
    """Koşu başka bir süreç tarafından tutuluyor."""


def _kilitle(tanitici: int) -> None:
    """Dosya tanıtıcısını **bloklamadan** kilitler. Alınamazsa `OSError`."""
    if sys.platform == "win32":
        import msvcrt

        os.lseek(tanitici, KILIT_OFSETI, os.SEEK_SET)
        msvcrt.locking(tanitici, msvcrt.LK_NBLCK, 1)
    else:  # pragma: no cover - bu proje Windows'ta koşuyor
        import fcntl

        fcntl.flock(tanitici, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _coz(tanitici: int) -> None:
    if sys.platform == "win32":
        import msvcrt

        os.lseek(tanitici, KILIT_OFSETI, os.SEEK_SET)
        msvcrt.locking(tanitici, msvcrt.LK_UNLCK, 1)
    else:  # pragma: no cover
        import fcntl

        fcntl.flock(tanitici, fcntl.LOCK_UN)


class KosuKilidi:
    """Bir koşu dosyası için tek-yazıcı kilidi.

    Bağlam yöneticisi olarak da kullanılabilir. `kapat()` iki kez çağrılabilir —
    kapanış yollarının (düzgün çıkış, istisna, sinyal) hepsinin aynı metodu çağırması
    isteniyor ve ikinci çağrının patlaması o basitliği bozardı.
    """

    __slots__ = ("yol", "_tanitici")

    def __init__(self, kosu_yolu: str | Path) -> None:
        self.yol = Path(str(kosu_yolu)).with_suffix(
            Path(str(kosu_yolu)).suffix + UZANTI
        )
        self._tanitici: int | None = None

    def al(self) -> KosuKilidi:
        """Kilidi alır. Başka bir süreç tutuyorsa `KilitAlinamadi`.

        Kilit dosyasına pid yazılıyor ama **kimlik olarak değil, ölüm sonrası iz olarak**:
        kilidi tutan şey işletim sistemi, dosyanın içeriği değil. İçeriğe güvenmek, dosyayı
        elle düzenleyen birinin kilidi atlatabilmesi demek olurdu. Windows dosyayı kilit
        tutulurken zaten başka bir sürece açtırmıyor; pid ancak süreç öldükten sonra
        okunabiliyor ve orada işe yarıyor (`KILIT_OFSETI` notu).
        """
        self.yol.parent.mkdir(parents=True, exist_ok=True)
        tanitici = os.open(self.yol, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            _kilitle(tanitici)
        except OSError as hata:
            os.close(tanitici)
            raise KilitAlinamadi(
                f"koşu zaten çalışıyor: {self.yol.name} başka bir süreç tarafından "
                "tutuluyor. Aynı koşuyu iki süreçle işlemek fill defterini çiftler ve "
                "hata ancak bir sonraki toparlanmada, üstelik yanlış sebeple görünür."
            ) from hata

        self._tanitici = tanitici
        os.lseek(tanitici, 0, os.SEEK_SET)
        os.write(tanitici, f"pid={os.getpid()}\n".encode())
        os.fsync(tanitici)
        return self

    def kapat(self) -> None:
        if self._tanitici is None:
            return
        try:
            _coz(self._tanitici)
        finally:
            os.close(self._tanitici)
            self._tanitici = None

    @property
    def tutuluyor(self) -> bool:
        return self._tanitici is not None

    def __enter__(self) -> KosuKilidi:
        return self.al()

    def __exit__(
        self,
        tur: type[BaseException] | None,
        deger: BaseException | None,
        iz: TracebackType | None,
    ) -> None:
        self.kapat()


__all__ = ["KILIT_OFSETI", "UZANTI", "KilitAlinamadi", "KosuKilidi"]
