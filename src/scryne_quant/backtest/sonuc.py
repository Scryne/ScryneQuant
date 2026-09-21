"""Backtest sonuç kaydı: bir koşunun yeniden üretilebilir kimliği. (K-009, K-006)

K-009'un istediği altı alan burada: commit SHA, `dirty` bayrağı, veri seti hash'i, config
hash'i, seed, kütüphane sürümleri. Hiçbiri isteğe bağlı değil — biri eksikse o sonuç
"şu kodla, şu veriyle üretildi" diyemez, yalnızca "bir zamanlar üretildi" der.

**`sonuc_hash` ile `config_hash` farklı şeyler.** `config_hash` girdiyi (strateji,
parametreler, maliyet modeli, sermaye) özetler; `sonuc_hash` çıktıyı (metrikler, işlem
defteri, equity eğrisi). Determinizm iddiası ikisinin **birlikte** sabit kalmasıdır: aynı
config_hash + aynı veri hash'i → aynı sonuc_hash. Yalnızca birini tutmak iddianın yarısını
kanıtlar.

**Ortam ve git durumu hash'e girmez.** Girseydi aynı veri ve aynı config'le yapılan iki
koşu, arada tek bir commit atıldığı için farklı hash verirdi — ve determinizm testi hiçbir
zaman yeşile dönmezdi. Onlar kayıtta durur, kimliğin içinde değil.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import numpy as np

from scryne_quant.backtest.fill import AtlamaSebebi
from scryne_quant.backtest.metrikler import Islem, Metrikler
from scryne_quant.common.hash import git_durumu, nesne_hash, ortam_kaydi
from scryne_quant.common.zaman import utc_str

#: `ok` olmayan bar oranı bu eşiği aşarsa sonuç `data_quality_warning` alır (K-006).
#:
#: **Bu sayı geçicidir.** K-006 "bir eşiği aşarsa" diyor ama eşiği vermiyor; promotion
#: kapılarının sayısal eşikleri K-019'un konusu ve Faz 4 sonunda gerçek veriyle kalibre
#: edilecek. Buradaki %1, ölçülen gerçeğe (BTC/USDT 1h, 5,2 yıl: 4/45.576 = %0,0088) 100
#: kat pay bırakıyor — yani bugünkü veri için bağlayıcı değil, ama sessizce de geçmiyor.
VARSAYILAN_KALITE_ESIGI: Final = 0.01


@dataclass(frozen=True, slots=True)
class VeriKimligi:
    """Backtest'in okuduğu veri: neyi, nereden, ne kadarını."""

    sembol: str
    timeframe: str
    sha256: str
    bar_sayisi: int
    ilk_ms: int
    son_ms: int
    ok_olmayan_bar: int
    ok_olmayan_oran: float
    kalite_sayimi: dict[str, int]

    def sozluk(self) -> dict[str, Any]:
        return {
            "sembol": self.sembol,
            "timeframe": self.timeframe,
            "sha256": self.sha256,
            "bar_sayisi": self.bar_sayisi,
            "ilk_ms": self.ilk_ms,
            "son_ms": self.son_ms,
            "ilk_utc": utc_str(self.ilk_ms),
            "son_utc": utc_str(self.son_ms),
            "ok_olmayan_bar": self.ok_olmayan_bar,
            "ok_olmayan_oran": self.ok_olmayan_oran,
            "kalite_sayimi": dict(sorted(self.kalite_sayimi.items())),
        }


@dataclass(frozen=True, slots=True)
class Sonuc:
    """Bir backtest koşusunun tamamı: kimlik, girdi, çıktı."""

    veri: VeriKimligi
    strateji: dict[str, Any]
    maliyet: dict[str, Any]
    baslangic_sermaye: float
    seed: int
    metrikler: Metrikler
    islemler: list[Islem]
    ozkaynak: np.ndarray = field(repr=False)
    maruziyet: np.ndarray = field(repr=False)
    zamanlar: np.ndarray = field(repr=False)
    atlanan: dict[str, int] = field(default_factory=dict)
    uretilen_sinyal: int = 0
    acik_pozisyon_sonda: bool = False
    kalite_esigi: float = VARSAYILAN_KALITE_ESIGI

    leak_riski: bool = False
    """Bu koşu, eğitim kesimi öncesi dönem için üretilmiş bir LLM türetimi okudu mu?
    (K-049/4, K-054)

    **Hash'e girmiyor**, çünkü bir provenans beyanı — `dirty` ve `commit` gibi. Sonucun
    sayılarını değiştirmez, ama promotion'un **mutlak** engelidir: sızıntı ağırlıklarda
    olduğu için look-ahead testi onu yakalayamaz ve engel bu yüzden beyana dayanır.

    Varsayılan `False` "sızıntı yok" demek değil, "LLM türetimi kullanılmadı" demek.
    Kullanan taraf (`research/program.py:LlmTuretimi`) hesaplayıp buraya geçiriyor.
    """

    evren: dict[str, Any] | None = None
    """Çok enstrümanlı koşunun evren kimliği; tek sembollü koşuda `None`. (Faz 10)

    İçeriği: evren kuralının hash'i, enstrüman sayısı ve enstrüman başına veri kimliği
    (sha256, bar sayısı, üye bar sayısı, `ok` olmayan bar). `veri` alanı çok enstrümanlı
    koşuda evrenin **toplamını** anlatır; hangi sembolün hangi dosyadan geldiği burada.

    `risk` ile aynı kural: hash'e yalnızca **varsa** giriyor. `"evren": None` yazmak Faz
    1-7'de kaydedilmiş her sonucun hash'ini değiştirirdi (K-009).
    """

    maliyetler: dict[str, Any] | None = None
    """Enstrüman-başı maliyet bloğu `{sembol: {"id", "govde"}}`; tek modelli koşuda `None`.
    (K-084/U14)

    `risk`/`evren` ile aynı kural: `config_hash`e ve kayda **yalnız varsa** girer — Binance
    spot (tek model) kayıtlarının kimliği değişmez. `maliyet` alanı her durumda tek modeli
    taşımaya devam eder (eski biçim)."""

    gecici: bool | None = None
    """Koşunun maliyet modeli geçici mi. `None` = tek modelin `maliyet["gecici"]` bayrağı
    (eski kayıt biçimi); çok modelde herhangi biri geçiciyse `True` (K-084/6). Hash'e
    girmez — `promotion_engelleri` okur."""

    risk: dict[str, Any] | None = None
    """Risk motoru özeti (`RiskMotoru.ozet()`); motor devre dışıysa `None`. (Faz 5)

    `None` ile boş sözlük arasındaki fark anlamlı: `None` "risk motoru yoktu", boş sözlük
    "vardı ama hiçbir şey kaydetmedi" olurdu. Promotion zincirinin `risk_incelemesi`
    aşaması bu alanın varlığına bakıyor — risksiz bir koşu o aşamayı **ölçülemedi** olarak
    geçer, geçmiş olarak değil."""

    # ------------------------------------------------------------- kimlikler

    @property
    def config_hash(self) -> str:
        """Girdiyi özetler: strateji + parametreler + maliyet + sermaye + seed.

        `maliyetler` yalnız varsa girer (K-084): tek modelli kayıtların hash'i değişmez.
        """
        govde: dict[str, Any] = {
            "strateji": self.strateji,
            "maliyet": self.maliyet,
            "baslangic_sermaye": self.baslangic_sermaye,
            "seed": self.seed,
            "sembol": self.veri.sembol,
            "timeframe": self.veri.timeframe,
        }
        if self.maliyetler is not None:
            govde["maliyetler"] = self.maliyetler
        return nesne_hash(govde)

    @property
    def sonuc_hash(self) -> str:
        """Çıktıyı özetler. Determinizm testinin karşılaştırdığı sayı bu."""
        govde: dict[str, Any] = {
            "metrikler": self.metrikler.sozluk(),
            "islemler": [i.sozluk(sembol_yaz=self.coklu) for i in self.islemler],
            "ozkaynak": self.ozkaynak.tolist(),
            "maruziyet": self.maruziyet.tolist(),
            # **Yalnızca sıfır olmayanlar.** `atlama_sayimi` kaydın okunabilirliği için
            # sıfır sayaçları da yazıyor ("yokluk da bir bilgi") ama o liste `AtlamaSebebi`
            # enum'unun **bugünkü** hâlinden türüyor: yeni bir atlama sebebi eklemek, o
            # sebebi hiç üretmemiş eski koşuların hash'ini de değiştiriyordu. Ölçüldü —
            # Faz 4'ün tarama kayıtları Faz 5/6'da eklenen `risk_reddetti` ve `veri_bayat`
            # yüzünden zaten yeniden üretilemiyordu; ekonomik değerlerin **hepsi** aynıydı,
            # yalnızca hash kaymıştı (Faz 10 raporu §3). Sıfırı hash'e sokmamak, davranışın
            # tamamını kapsamaya devam ederken kaydı sebep listesinin büyümesine karşı
            # dayanıklı yapıyor.
            "atlanan": {a: d for a, d in sorted(self.atlanan.items()) if d},
        }
        # Risk özeti hash'e yalnızca **varsa** giriyor. `"risk": None` yazmak, Faz 1-4'te
        # kaydedilmiş her sonucun hash'ini değiştirirdi — yani risk motorunu eklemek, onu
        # hiç kullanmayan eski deneyleri yeniden üretilemez yapardı (`sq lab dogrula`).
        if self.evren is not None:
            govde["evren"] = _kanonik(self.evren)
        if self.risk is not None:
            govde["risk"] = _kanonik(self.risk)
        return nesne_hash(govde)

    @property
    def coklu(self) -> bool:
        """Bu koşu çok enstrümanlı mı? İşlem satırına sembol yazılıp yazılmayacağını belirler."""
        return self.evren is not None

    @property
    def data_quality_warning(self) -> bool:
        """K-006: eşiği aşan `ok` olmayan bar oranı promotion'a engeldir (K-010)."""
        return self.veri.ok_olmayan_oran > self.kalite_esigi

    @property
    def promotion_engelleri(self) -> list[str]:
        """Bu sonucun promotion zincirine giremeyeceği sebepler. Boşsa engel yok.

        Kapının **kendisi** değil, kapının okuyacağı liste (K-010 Faz 5'te uygulanacak).
        Burada üretilmesinin sebebi, engelin sonucun içinde taşınması: sonuç dosyası elden
        ele geçerken "bu neden geçemez" bilgisi kaybolmasın.
        """
        engeller: list[str] = []
        if self.dirty:
            engeller.append("dirty")  # K-009
        if self.data_quality_warning:
            engeller.append("data_quality_warning")  # K-006
        gecici = self.maliyet.get("gecici") if self.gecici is None else self.gecici
        if gecici:
            engeller.append("gecici_maliyet_modeli")  # K-021, K-084/6
        if self.leak_riski:
            engeller.append("leak_riski")  # K-049/4, K-054
        return engeller

    @property
    def dirty(self) -> bool:
        return bool(self._git.get("dirty"))

    @property
    def _git(self) -> dict[str, Any]:
        return git_durumu()

    # ------------------------------------------------------------------ kayıt

    def sozluk(self, *, islem_listesi: bool = True, egri: bool = False) -> dict[str, Any]:
        """Sonuç kaydının tam gösterimi.

        `egri=False` varsayılan: 45.000 barlık bir equity eğrisi JSON'da ~1 MB tutar ve
        özeti okunmaz hâle getirir. Eğri gerektiğinde açıkça istenir; kimliği zaten
        `sonuc_hash` taşıyor.
        """
        git = self._git
        kayit: dict[str, Any] = {
            "kimlik": {
                "config_hash": self.config_hash,
                "sonuc_hash": self.sonuc_hash,
                "veri_sha256": self.veri.sha256,
                "commit": git.get("commit"),
                "dirty": git.get("dirty"),
                "seed": self.seed,
                "ortam": ortam_kaydi(),
            },
            "veri": self.veri.sozluk(),
            "config": {
                "strateji": self.strateji,
                "maliyet": self.maliyet,
                "baslangic_sermaye": self.baslangic_sermaye,
                "kalite_esigi": self.kalite_esigi,
                # Yalnız çok modelde (K-084): tek modelli kaydın biçimi Faz 3-16 ile aynı.
                **({"maliyetler": self.maliyetler} if self.maliyetler is not None else {}),
            },
            "metrikler": self.metrikler.sozluk(),
            "akis": {
                "uretilen_sinyal": self.uretilen_sinyal,
                "islenen_sinyal": sum(1 for i in self.islemler for _ in range(i.fill_sayisi)),
                "atlanan": dict(sorted(self.atlanan.items())),
                "acik_pozisyon_sonda": self.acik_pozisyon_sonda,
            },
            "promotion": {
                "gecebilir": not self.promotion_engelleri,
                "engeller": self.promotion_engelleri,
                "data_quality_warning": self.data_quality_warning,
                "leak_riski": self.leak_riski,
            },
        }
        if self.evren is not None:
            kayit["evren"] = self.evren
        if self.risk is not None:
            kayit["risk"] = self.risk
        if islem_listesi:
            kayit["islemler"] = [i.sozluk(sembol_yaz=self.coklu) for i in self.islemler]
        if egri:
            kayit["egri"] = {
                "zamanlar": self.zamanlar.tolist(),
                "ozkaynak": self.ozkaynak.tolist(),
                "maruziyet": self.maruziyet.tolist(),
            }
        return kayit

    def yaz(self, yol: str | Path, *, egri: bool = False) -> Path:
        """Sonuç kaydını JSON olarak yazar. Anahtarlar sıralı — byte düzeyinde kararlı."""
        p = Path(yol)
        p.parent.mkdir(parents=True, exist_ok=True)
        icerik = json.dumps(
            self.sozluk(egri=egri), ensure_ascii=False, indent=2, sort_keys=True
        )
        p.write_text(icerik + "\n", encoding="utf-8", newline="\n")
        return p


def _kanonik(nesne: Any) -> Any:
    """Sözlükleri anahtara göre sıralar (içiçe). Hash'in sözlük sırasından bağımsızlığı için.

    `nesne_hash` `sort_keys=True` kullanıyor, yani bu aslında gereksiz — ama risk özeti
    iç içe sözlükler taşıyor ve ileride bir alanın listeye dönmesi hâlinde sıranın
    nereden geldiğinin açık olması iyi. Maliyeti yok, belirsizliği kaldırıyor.
    """
    if isinstance(nesne, dict):
        return {a: _kanonik(d) for a, d in sorted(nesne.items())}
    if isinstance(nesne, list):
        return [_kanonik(x) for x in nesne]
    return nesne


def atlama_sayimi(sebepler: list[AtlamaSebebi]) -> dict[str, int]:
    """Atlama sebeplerini sayar. Sıfır olanlar da yazılır — yokluk da bir bilgi."""
    sayim = dict.fromkeys((s.value for s in AtlamaSebebi), 0)
    for s in sebepler:
        sayim[s.value] += 1
    return sayim
