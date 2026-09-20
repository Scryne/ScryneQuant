"""Deney kaydı: bir laboratuvar koşusunun yeniden üretilebilir tarifi. (K-009, Faz 4)

Faz 4'ün bitti kriteri şunu istiyor: *"Herhangi bir deney, kaydından yeniden
üretilebiliyor (kanıt: rastgele seçilen bir deney yeniden çalıştırılıp hash'i
doğrulanır)."* Bu modül o kaydın hem yazıcısı hem okuyucusu.

**Kayıt bir tarif, bir özet değil.** Farkı şu: özet "SMA 20/50 ile Sharpe −0,34 çıktı"
der; tarif "şu commit'teki kodu, şu SHA-256'lı veri dosyasının şu bar aralığında, şu
maliyet modeliyle, şu ızgarayla, şu ölçütle, şu seed'le çalıştır" der. İkincisi çalıştırılıp
doğrulanabilir, birincisi yalnızca okunabilir.

Kaydın taşıdıkları K-009'un altı alanına ek olarak deney tipini (`tarama`, `walk_forward`,
`monte_carlo`, `stres`, `karsilastirma`), girdi tarifini ve çıktı hash'ini içerir.

**Yeniden üretim `dogrula()` ile yapılır ve `dirty` bir ağaçta bile çalışır** — ama o
durumda kayıt zaten promotion'a giremez (K-009). Yeniden üretilebilirlik ile promotion
uygunluğu ayrı sorular; ikisini karıştırmak, araştırma sırasında hiçbir şey
çalıştırılamaması demek olurdu.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from scryne_quant.common.hash import git_durumu, nesne_hash, ortam_kaydi

#: Deney kayıtlarının varsayılan kökü. `.gitignore`'da (`runs/`).
VARSAYILAN_KOK: Final = Path("runs/deneyler")

#: Tanınan deney tipleri. Serbest string kabul edilmiyor: kayıtları tipine göre aramak
#: ("tüm walk-forward'ları listele") ancak tip kümesi kapalıysa mümkün.
TIPLER: Final[frozenset[str]] = frozenset(
    {
        "tarama",
        "walk_forward",
        "monte_carlo",
        "stres",
        "karsilastirma",
        "degerlendirme",
        # Çoklu test düzeltmesi (K-039). Diğerlerinden farkı: girdisi veri değil
        # **defterin kendisi** — kaç çekiliş yapıldığını ölçüyor, bir stratejiyi değil.
        "coklu_test",
        # K-054'ün dört yeni kapısı, defterin her çekilişi için (Faz 11). `coklu_test` gibi
        # girdisi defterin kendisi; kaydından yeniden üretilmesi defterin o günkü hâline
        # bağlı olduğu için `tekrar.TEKRAR_EDILEBILIR` listesinde değil.
        "kapilar_v2",
    }
)


class DeneyHatasi(ValueError):
    """Deney kaydı geçersiz veya yeniden üretilemedi."""


@dataclass(frozen=True, slots=True)
class Deney:
    """Bir laboratuvar koşusunun tam kaydı."""

    tip: str
    strateji: str
    girdi: dict[str, Any]
    """Koşuyu tekrarlamak için gereken **her şey**: sembol, timeframe, pencere, ızgara,
    ölçüt, maliyet modeli, sermaye, seed."""

    cikti: dict[str, Any]
    """Sonucun kendisi. `cikti_hash` bunun üzerinden hesaplanır."""

    veri_sha256: str
    seed: int = 0
    etiket: str = ""
    zaman: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))
    veri_son_ms: int | None = None
    """Verinin son barının açılışı (K-080). Kimliğe **girmez** — `veri_sha256` zaten veriyi
    tanımlıyor; bu alan o veriye **geri dönmenin** adresi: depo uzatıldıysa
    `sq lab dogrula --geri-sar` depoyu `veri_son_ms + timeframe`e kırpıp hash'i yeniden
    kurar. Eski kayıtlarda yok (`None`); onlar için tarih elle verilir (`--veri-sonu`)."""

    def __post_init__(self) -> None:
        if self.tip not in TIPLER:
            raise DeneyHatasi(f"bilinmeyen deney tipi {self.tip!r}; geçerli: {sorted(TIPLER)}")
        if not self.veri_sha256:
            # Veri kimliği olmayan bir kayıt yeniden üretilemez: aynı komut altı ay sonra
            # farklı (daha uzun) bir veri setiyle çalışır ve sessizce farklı sonuç verir.
            raise DeneyHatasi("veri_sha256 zorunlu (K-009)")

    @property
    def girdi_hash(self) -> str:
        return nesne_hash({"tip": self.tip, "strateji": self.strateji, "girdi": self.girdi,
                           "veri_sha256": self.veri_sha256, "seed": self.seed})

    @property
    def cikti_hash(self) -> str:
        return nesne_hash(self.cikti)

    @property
    def kimlik(self) -> str:
        """Dosya adında kullanılan kısa kimlik: girdi + çıktı."""
        return f"{self.girdi_hash[:12]}-{self.cikti_hash[:12]}"

    def sozluk(self) -> dict[str, Any]:
        git = git_durumu()
        return {
            "kimlik": {
                "girdi_hash": self.girdi_hash,
                "cikti_hash": self.cikti_hash,
                "veri_sha256": self.veri_sha256,
                "veri_son_ms": self.veri_son_ms,
                "commit": git.get("commit"),
                "dirty": git.get("dirty"),
                "seed": self.seed,
                "ortam": ortam_kaydi(),
            },
            "tip": self.tip,
            "strateji": self.strateji,
            "etiket": self.etiket,
            "zaman": self.zaman,
            "girdi": self.girdi,
            "cikti": self.cikti,
        }

    def yaz(self, kok: str | Path = VARSAYILAN_KOK) -> Path:
        """Kaydı `<kok>/<tip>/<kimlik>.json` olarak yazar."""
        yol = Path(kok) / self.tip / f"{self.kimlik}.json"
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_text(
            json.dumps(self.sozluk(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return yol


def oku(yol: str | Path) -> dict[str, Any]:
    """Kaydı okur. Sözlük döner — `Deney` değil, çünkü kayıt geçmişe ait bir belgedir."""
    return json.loads(Path(yol).read_text(encoding="utf-8"))


def listele(kok: str | Path = VARSAYILAN_KOK, tip: str | None = None) -> list[Path]:
    """Kayıtlı deneyleri listeler; `tip` verilirse yalnızca o tipi."""
    p = Path(kok)
    if not p.exists():
        return []
    desen = f"{tip}/*.json" if tip else "*/*.json"
    return sorted(p.glob(desen))


def dogrula(kayit: Mapping[str, Any], yeniden_cikti: Mapping[str, Any]) -> tuple[bool, str]:
    """Yeniden üretilen çıktının kayıttakiyle aynı olup olmadığını söyler.

    Karşılaştırma **hash üzerinden**: alan alan karşılaştırma, hangi alanların kimliğe
    dahil olduğu sorusunu her çağrı yerinde yeniden sorardı ve biri er ya da geç
    unutulurdu.

    Dönen ikinci değer insan için açıklama — "aynı" ya da hangi hash'lerin uyuşmadığı.
    """
    beklenen = kayit.get("kimlik", {}).get("cikti_hash")
    if not beklenen:
        raise DeneyHatasi("kayıtta cikti_hash yok; bu bir deney kaydı değil")

    bulunan = nesne_hash(dict(yeniden_cikti))
    if bulunan == beklenen:
        return True, f"aynı ({bulunan[:16]})"
    return False, f"uyuşmuyor: kayıt {beklenen[:16]}, yeniden üretim {bulunan[:16]}"


#: `farklar()` sınıfları. Karar bu ayrıma göre veriliyor (K-080, R1(b)):
#: - `yalniz_sonuc_hash`: ekonomik alanlar birebir, yalnız `sonuc_hash` alanları farklı —
#:   K-057/6'nın atlama sayacı değişimi; kayıt bugünkü hash algoritmasıyla **yenilenebilir**.
#: - `semantik`: metrik/parametre/alan düzeyinde fark — kod o günden beri değişmiş; kayıt
#:   tarihsel kalır, "bugünkü kodla yeniden üretilemez" etiketi alır.
YALNIZ_SONUC_HASH: Final = "yalniz_sonuc_hash"
SEMANTIK: Final = "semantik"


def farklar(kayit_cikti: Mapping[str, Any], yeni_cikti: Mapping[str, Any]) -> list[str]:
    """İki çıktı arasındaki farklı alan yolları (`/a/b[3]/c`). Boş liste = birebir aynı.

    `dogrula()` hash üzerinden karar verir ve öyle kalır; bu fonksiyon **neden** sorusuna
    cevap: fark yalnız `sonuc_hash` alanlarındaysa (K-057/6) ekonomik sonuç aynıdır.
    """
    out: list[str] = []

    def gez(a: Any, b: Any, yol: str) -> None:
        if isinstance(a, Mapping) and isinstance(b, Mapping):
            for k in sorted(set(a) | set(b)):
                if k not in a or k not in b:
                    out.append(f"{yol}/{k} (yalnız {'kayıtta' if k in a else 'yenide'})")
                else:
                    gez(a[k], b[k], f"{yol}/{k}")
        elif isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                out.append(f"{yol} (uzunluk {len(a)} vs {len(b)})")
            else:
                for i, (x, y) in enumerate(zip(a, b, strict=True)):
                    gez(x, y, f"{yol}[{i}]")
        elif a != b:
            out.append(yol)

    gez(kayit_cikti, yeni_cikti, "")
    return out


def fark_sinifi(farklar_listesi: list[str]) -> str | None:
    """`None` = fark yok; aksi hâlde `YALNIZ_SONUC_HASH` ya da `SEMANTIK`."""
    if not farklar_listesi:
        return None
    if all(f.endswith("/sonuc_hash") for f in farklar_listesi):
        return YALNIZ_SONUC_HASH
    return SEMANTIK
