"""Execution hattı: onaylı niyetten mutabık kalınmış portföye giden yol. (K-114, R9)

    OnayliNiyet → execution güvenliği (engelleyen) → miktar → EmirMotoru → borsa
                → emir mutabakatı → pozisyon mutabakatı → hesap görünümü

`EmirMotoru` (Faz 7) tek bir niyeti tek bir emre çevirir; bu modül onun etrafındaki
**koşu** düzeyidir: hangi niyet ne kadar miktara dönüşür, hangi koşulda hiç gönderilmez,
koşu başında ve sonunda mutabakat, acil iptal, ve panonun okuduğu durum. Paper, shadow,
testnet ve live için **aynı kod**: aralarındaki tek fark verilen `EmirAdaptoru`
(`PaperBorsa`, `GolgeAdaptoru`, testnet, canlı) — K-001'in execution'daki karşılığı.

**Bu katman yalnızca engeller ve küçültür; asla onaylamaz ve büyütmez (K-037).** Onay
risk motorunun (`OnayliNiyet`, mühürlü). Buradaki her kural ya niyeti **reddeder** ya da
miktarı **aşağı** çeker. Azaltan niyetler (SELL/FLAT) SAFE_MODE'da, bayat veride ve kayıp
limitinde de geçer (K-008/3) — ama durdurulmuş (halt) bir koşuda ve çözülmemiş `UNKNOWN`
varken **hiçbir** emir gitmez: orada borsanın gerçek durumu bilinmiyor ve her emir bir
tahmindir (K-038, K-046).

**Engeller, sırayla:**

| # | Engel | Kapsam | Kaynak |
| --- | --- | --- | --- |
| 1 | Mod emir yoluna kapalı (DISABLED) | hepsi | K-114 |
| 2 | Koşu durdurulmuş (halt) | hepsi | K-038, K-046 |
| 3 | Çözülmemiş `UNKNOWN` emir | hepsi | §33 |
| 4 | Aynı sembolde açık emir | hepsi | duplicate/yığılma |
| 5 | Aynı bar için ikinci emir | hepsi | §33 duplicate (bar düzeyi) |
| 6 | Sistem modu bu koşunun modunun altına inmiş / okunamıyor | artıran | K-050, K-114 |
| 7 | Son mutabakat hatasız tamamlanmamış | artıran | K-038, K-046 |
| 8 | SAFE_MODE işareti (`kosu.safemode`) | artıran | K-008, K-065 |
| 9 | Bayat karar (karar barı, gönderim anındaki son kapanmış bar değil) | artıran | K-004, §24 |
| 10 | Kayıp tavanı; günlük zarar / drawdown (defter + borsa, her bar) | artıran (+SAFE) | K-115 |
| 11 | Tavan: maruziyet, brüt, nakit; boyut tabanı ≤ sermaye | küçültür | risk.json, kademe |

**Hesap görünümü defterden türer, borsanın toplam bakiyesinden değil.** Koşunun sermayesi
(`sermaye_usdt`: paper'da açılış nakdi, canlıda kademe sermayesi) + defterdeki fill akışı =
koşunun nakdi ve pozisyonu. Hesapta sistemin dışında duran varlıklar (başka bakiyeler)
koşuya ait sayılmaz; defterin doğruluğunu ise pozisyon mutabakatı (çıpa + akış = borsa)
bağımsız olarak doğrular (K-046). Böylece strateji yalnızca kendi sermayesini görür ve
canlıda sermaye kademe tavanını aşamaz.

**Tek sembol.** `oms/pozisyon._akis` sembol ayırt etmiyor; çok sembollü bir koşu ortak kote
varlıkta farkları karıştırırdı. Execution hattı bu yüzden koşu başına tek sembol taşır.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

from scryne_quant.common.zaman import simdi_ms, utc_str
from scryne_quant.exchange.emir_adaptoru import BORSA_YONU, EmirAdaptoru
from scryne_quant.exchange.hatalar import BorsaHatasi
from scryne_quant.execution.mod import CalismaModu, sira
from scryne_quant.execution.motor import EmirMotoru, GonderimSonucu, golge_mi
from scryne_quant.oms.defter import EmirDefteri
from scryne_quant.oms.emir import ACIK, EmirDurumu
from scryne_quant.oms.mutabakat import mutabakat
from scryne_quant.oms.pozisyon import (
    CipaYok,
    PozisyonHatasi,
    cipa_at,
    pozisyon_mutabakati,
)
from scryne_quant.risk.audit import Defter, Olay, OlayTuru
from scryne_quant.risk.niyet import OnayliNiyet, dogrula

SAFE_ISARETI: Final = "kosu.safemode"
DURUM_DOSYASI: Final = "durum.json"
HAT_DURUMU: Final = "hat.json"

#: Pano ve durum dosyasında tutulan son emir/karar sayısı.
SON_KAYIT: Final = 50


class Engel(StrEnum):
    MOD = "mod_kapali"
    HALT = "halt"
    BELIRSIZ_EMIR = "belirsiz_emir"
    ACIK_EMIR = "acik_emir"
    AYNI_BAR = "ayni_bar"
    SAFE_MODE = "safe_mode"
    BAYAT_KARAR = "bayat_karar"
    GUNLUK_ZARAR = "gunluk_zarar"
    DRAWDOWN = "drawdown"
    KAYIP_TAVANI = "kayip_tavani"
    """K-115 pilot: özkaynak sermaye − azami kayıp altına indi; SAFE_MODE."""
    BAGLANTI = "baglanti"
    MUTABAKAT = "mutabakat_yok"
    """Son mutabakat hatasız tamamlanmadı: hesap doğrulanmamış, artıran emir yok."""

    HEDEFTE = "hedefte"
    """Pozisyon zaten hedefte; gönderilecek fark yok. Engel değil, sonuç — ama emir yok."""


@dataclass(frozen=True, slots=True)
class GuvenlikLimitleri:
    """Execution hattının tavanları. Sayıların hepsi mevcut kaynaklardan: yeni eşik yok."""

    sermaye_usdt: float
    """Koşunun yönettiği sermaye. Canlıda `CanliYetki.sermaye_usdt` (kademe, K-050/3)."""

    azami_maruziyet: float
    azami_brut_maruziyet: float
    gunluk_zarar_limiti: float
    drawdown_limiti: float
    azami_kayip_usdt: float | None = None
    """Mutlak kayıp tavanı (K-115 pilot): özkaynak ≤ sermaye − bu değer → SAFE_MODE. Tavan
    sermayeye göre sabittir (zirveye göre değil) ve özkaynak altında kaldıkça işaret kaldırılsa
    da yeniden konur — koşu bu sermayeyle bir daha artıran emir göndermez."""

    @classmethod
    def risk_limitlerinden(
        cls, limitler: Any, sermaye_usdt: float, *, azami_kayip_usdt: float | None = None
    ) -> GuvenlikLimitleri:
        if sermaye_usdt <= 0.0:
            raise ValueError(f"sermaye pozitif olmalı: {sermaye_usdt}")
        if azami_kayip_usdt is not None and not 0.0 < azami_kayip_usdt < sermaye_usdt:
            raise ValueError(f"azami kayıp (0, sermaye) aralığında olmalı: {azami_kayip_usdt}")
        return cls(
            sermaye_usdt=float(sermaye_usdt),
            azami_maruziyet=float(limitler.azami_maruziyet),
            azami_brut_maruziyet=float(limitler.azami_brut_maruziyet),
            gunluk_zarar_limiti=float(limitler.gunluk_zarar_limiti),
            drawdown_limiti=float(limitler.drawdown_limiti),
            azami_kayip_usdt=None if azami_kayip_usdt is None else float(azami_kayip_usdt),
        )

    def kayip_tavani_asildi(self, ozkaynak: float) -> bool:
        k = self.azami_kayip_usdt
        return k is not None and ozkaynak <= self.sermaye_usdt - k

    def sozluk(self) -> dict[str, float]:
        out = {
            "sermaye_usdt": self.sermaye_usdt,
            "azami_maruziyet": self.azami_maruziyet,
            "azami_brut_maruziyet": self.azami_brut_maruziyet,
            "gunluk_zarar_limiti": self.gunluk_zarar_limiti,
            "drawdown_limiti": self.drawdown_limiti,
        }
        if self.azami_kayip_usdt is not None:
            out["azami_kayip_usdt"] = self.azami_kayip_usdt
        return out


@dataclass(frozen=True, slots=True)
class HesapGorunumu:
    """Koşunun defterden türeyen hesabı (tek sembol)."""

    sembol: str
    nakit: float
    miktar: float
    fiyat: float
    komisyon_toplam: float

    @property
    def pozisyon_degeri(self) -> float:
        return self.miktar * self.fiyat

    @property
    def ozkaynak(self) -> float:
        return self.nakit + self.pozisyon_degeri

    @property
    def maruziyet(self) -> float:
        oz = self.ozkaynak
        return self.pozisyon_degeri / oz if oz > 0.0 else 0.0

    def sozluk(self) -> dict[str, Any]:
        return {
            "sembol": self.sembol,
            "nakit": self.nakit,
            "miktar": self.miktar,
            "fiyat": self.fiyat,
            "pozisyon_degeri": self.pozisyon_degeri,
            "ozkaynak": self.ozkaynak,
            "maruziyet": self.maruziyet,
            "komisyon_toplam": self.komisyon_toplam,
        }


@dataclass
class KayipIzleyici:
    """Borsa ölçümlü özkaynağın zirvesi ve gün başı — risk motorundan **bağımsız** ikinci göz.

    Risk motoru da drawdown ve günlük zararı izliyor; bu sınıf aynı limitleri defter+borsa
    ölçümlü hesaba uygular ve diske yazar. Engelleyen ikinci katman (K-037): risk motorunun
    gördüğü özkaynak bir hata yüzünden kayarsa bu katman onu tekrar etmez.
    """

    zirve: float = 0.0
    gun: int = -1
    gun_basi: float = 0.0

    def isle(self, ozkaynak: float, zaman_ms: int) -> None:
        gun = zaman_ms // 86_400_000
        if gun != self.gun:
            self.gun, self.gun_basi = gun, ozkaynak
        self.zirve = max(self.zirve, ozkaynak)

    def drawdown(self, ozkaynak: float) -> float:
        return 0.0 if self.zirve <= 0.0 else 1.0 - ozkaynak / self.zirve

    def gunluk(self, ozkaynak: float) -> float:
        return 0.0 if self.gun_basi <= 0.0 else ozkaynak / self.gun_basi - 1.0

    def sozluk(self) -> dict[str, Any]:
        return {"zirve": self.zirve, "gun": self.gun, "gun_basi": self.gun_basi}


@dataclass(frozen=True, slots=True)
class Uygulama:
    """Bir niyetin execution hattındaki sonucu."""

    sembol: str
    yon: str
    karar_ms: int
    onayli_maruziyet: float
    sonuc: str
    """`gonderildi`, `golge`, `zaten_var`, `kural_reddi`, `borsa_reddi`, `basarisiz`,
    `belirsiz` ya da `engellendi`."""

    engel: str = ""
    miktar: float = 0.0
    notional: float = 0.0
    kisitlayan: tuple[str, ...] = ()
    emir: dict[str, Any] | None = None

    def sozluk(self) -> dict[str, Any]:
        return {
            "sembol": self.sembol,
            "yon": self.yon,
            "karar_ms": self.karar_ms,
            "karar_utc": utc_str(self.karar_ms) if self.karar_ms else None,
            "onayli_maruziyet": self.onayli_maruziyet,
            "sonuc": self.sonuc,
            "engel": self.engel,
            "miktar": self.miktar,
            "notional": self.notional,
            "kisitlayan": list(self.kisitlayan),
            "emir": self.emir,
        }


class HatHatasi(RuntimeError):
    """Execution hattı sözleşmesi ihlal edildi."""


@dataclass
class ExecutionHatti:
    """Tek sembollü, tek koşuluk execution hattı. Durumu `kosu_dizini` altında."""

    mod: CalismaModu
    adaptor: EmirAdaptoru
    defter: EmirDefteri
    limitler: GuvenlikLimitleri
    sembol: str
    kosu_dizini: Path
    audit: Defter | None = None
    saat: Callable[[], int] = simdi_ms

    halt: str = ""
    izleyici: KayipIzleyici = field(default_factory=KayipIzleyici)
    son_kararlar: list[dict[str, Any]] = field(default_factory=list)
    son_mutabakat: dict[str, Any] = field(default_factory=dict)
    son_pozisyon: dict[str, Any] = field(default_factory=dict)
    baglanti_hatasi: str = ""
    mutabakat_tamam: bool = False
    """Son mutabakat hatasız bitti mi. Başlangıçta `False` (fail closed)."""

    mod_tavani: Callable[[], CalismaModu] | None = None
    """Sistem modunu **her artıran emirde** okuyan fonksiyon (K-114 denetimi). Verilirse ve
    sistem modu bu koşunun modunun altına indiyse (`sq execution indir`), çalışan koşu da
    artıran emir gönderemez; okuma hatası DISABLED sayılır. Canlıda zorunlu (kurulum verir)."""

    def _mod_tavani_izin_veriyor(self) -> bool:
        if self.mod_tavani is None:
            return self.mod is not CalismaModu.LIVE  # canlıda tavansız hat çalışmaz
        try:
            sistem = self.mod_tavani()
        except Exception:  # noqa: BLE001 — okunamayan mod DISABLED'dır (fail closed)
            return False
        return sira(sistem) >= sira(self.mod)

    def ozkaynak_isle(self, ozkaynak: float, zaman_ms: int) -> None:
        """Her barda çağrılır: kayıp izleyicisinin zirve/gün başı ölçümü emirden bağımsız."""
        self.izleyici.isle(ozkaynak, zaman_ms)
        if self.limitler.kayip_tavani_asildi(ozkaynak):
            self._kayip_tavani_isaretle(ozkaynak)
        self._durum_kaydet()

    def _kayip_tavani_isaretle(self, ozkaynak: float) -> None:
        self.safe_isaretle(
            f"kayıp tavanı: özkaynak {ozkaynak:.4f} ≤ sermaye {self.limitler.sermaye_usdt} − "
            f"{self.limitler.azami_kayip_usdt} USDT (K-115)"
        )

    def __post_init__(self) -> None:
        self.kosu_dizini = Path(self.kosu_dizini)
        self.kosu_dizini.mkdir(parents=True, exist_ok=True)
        if self.mod is CalismaModu.DISABLED:
            raise HatHatasi("DISABLED modda execution hattı kurulmaz")
        if self.mod is CalismaModu.SHADOW and not golge_mi(self.adaptor):
            raise HatHatasi("SHADOW modu yalnızca GolgeAdaptoru ile kurulur (K-114)")
        if self.mod is not CalismaModu.SHADOW and golge_mi(self.adaptor):
            raise HatHatasi(f"{self.mod} modu shadow adaptörüyle kurulamaz")
        if self.mod is CalismaModu.PAPER and getattr(self.adaptor, "GERCEK_EMIR", True):
            raise HatHatasi("PAPER modu yalnızca PaperBorsa ile kurulur")
        if self.mod in (CalismaModu.LIVE, CalismaModu.LIVE_PENDING_APPROVAL):
            if self.mod is CalismaModu.LIVE_PENDING_APPROVAL:
                raise HatHatasi("LIVE_PENDING_APPROVAL bir koşu modu değil; onay bekler")
            if not getattr(self.adaptor, "canli", False):
                raise HatHatasi("LIVE modu canlı adaptör ister")
        if self.mod is CalismaModu.TESTNET and getattr(self.adaptor, "canli", False):
            raise HatHatasi("TESTNET modu canlı adaptörle kurulamaz")
        onceki = self._oku(HAT_DURUMU)
        if onceki:
            self.halt = str(onceki.get("halt", ""))
            iz = onceki.get("izleyici") or {}
            self.izleyici = KayipIzleyici(
                float(iz.get("zirve", 0.0)), int(iz.get("gun", -1)), float(iz.get("gun_basi", 0.0))
            )

    # ================================================================ dosyalar

    def _oku(self, ad: str) -> dict[str, Any] | None:
        p = self.kosu_dizini / ad
        if not p.is_file():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _yaz(self, ad: str, veri: dict[str, Any]) -> None:
        p = self.kosu_dizini / ad
        gecici = p.with_suffix(".tmp")
        gecici.write_text(
            json.dumps(veri, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
        )
        gecici.replace(p)

    def _durum_kaydet(self) -> None:
        self._yaz(HAT_DURUMU, {"halt": self.halt, "izleyici": self.izleyici.sozluk()})

    def _olay(self, tur: str, govde: dict[str, Any], zaman_ms: int | None = None) -> None:
        if self.audit is None:
            return
        self.audit.yaz(
            Olay(
                tur=OlayTuru.EXECUTION,
                zaman_ms=int(zaman_ms if zaman_ms is not None else self.saat()),
                sembol=self.sembol,
                govde={"olay": tur, "mod": str(self.mod), **govde},
                durum={"halt": self.halt, "safe_mode": self.safe_mode},
            )
        )

    @property
    def safe_isareti(self) -> Path:
        return self.kosu_dizini / SAFE_ISARETI

    @property
    def safe_mode(self) -> bool:
        return self.safe_isareti.is_file()

    def safe_isaretle(self, sebep: str) -> None:
        """SAFE_MODE işareti. Kaldırmak yalnızca elle (`sq execution safe-kaldir`, K-008/4)."""
        if not self.safe_mode:
            self.safe_isareti.write_text(
                json.dumps({"sebep": sebep, "zaman_ms": self.saat()}, ensure_ascii=False),
                encoding="utf-8",
            )
            self._olay("safe_mode", {"sebep": sebep})

    def durdur(self, sebep: str) -> None:
        """Halt: bu koşuda hiçbir emir gitmez. Diske yazılır; yeniden başlatma da haltta açılır."""
        if not self.halt:
            self.halt = sebep
            self._durum_kaydet()
            self._olay("halt", {"sebep": sebep})

    # ================================================================ hesap

    def hesap(self, fiyat: float | None = None) -> HesapGorunumu:
        """Koşunun nakdi ve pozisyonu: sermaye + defterin fill akışı."""
        nakit = self.limitler.sermaye_usdt
        miktar = 0.0
        komisyon = 0.0
        kurallar = self.adaptor.sembol_kurallari(self.sembol)
        taban, kote = kurallar.taban_varlik, kurallar.kote_varlik
        for e in self.defter.tumu():
            if e.sembol != self.sembol or e.dolan_miktar <= 0.0:
                continue
            isaret = 1.0 if BORSA_YONU.get(e.yon.upper()) == "BUY" else -1.0
            miktar += isaret * e.dolan_miktar
            nakit -= isaret * e.dolan_miktar * e.ortalama_fiyat
            for varlik, m in e.komisyon:
                if varlik == kote:
                    nakit -= m
                    komisyon += m
                elif varlik == taban:
                    miktar -= m
                    komisyon += m * e.ortalama_fiyat
        if fiyat is None:
            fiyat = self.adaptor.son_fiyat(self.sembol)
        return HesapGorunumu(
            sembol=self.sembol,
            nakit=nakit,
            miktar=max(miktar, 0.0) if abs(miktar) < 1e-12 else miktar,
            fiyat=float(fiyat),
            komisyon_toplam=komisyon,
        )

    # ================================================================ başlangıç / bitiş

    def baslat(self) -> dict[str, Any]:
        """Başlangıç mutabakatı: çıpa (ilk kez), emir + pozisyon mutabakatı, yetim emir."""
        cipa = self.defter.acilis_oku()
        if cipa is None:
            if self.defter.tumu():
                self.durdur("çıpasız defterde emir var; pozisyon mutabakatı yapılamaz")
            else:
                cipa = cipa_at(self.defter, self.adaptor, not_metni=f"{self.mod} koşu açılışı")
        sonuc = self.mutabakat_yap(asama="baslangic")
        self._olay("baslangic", {"cipa": cipa is not None, **sonuc})
        return sonuc

    def kapat(self) -> dict[str, Any]:
        """Kapanış mutabakatı ve son durum. Açık emir bırakılıyorsa raporlanır, iptal edilmez."""
        sonuc = self.mutabakat_yap(asama="kapanis")
        self._olay("kapanis", sonuc)
        return sonuc

    def mutabakat_yap(self, *, asama: str = "dongu") -> dict[str, Any]:
        """Emir + pozisyon mutabakatı. Uyuşmazlıkta **halt**; tahmin yürütülmez (K-038).

        **Mutabakat yapılamadıysa da işlem yok (K-114 denetimi).** Uyuşmazlık halt'a götürür;
        ama mutabakatın *koşamaması* (borsa okunamadı, bozuk yanıt) önceden sessizdi ve
        artıran emirler doğrulanmamış bir hesap üzerinde gönderilebiliyordu. Artık
        `mutabakat_tamam` yalnızca emir + pozisyon mutabakatının ikisi de hatasız bittiğinde
        `True`; aksi hâlde artıran niyetler `Engel.MUTABAKAT` ile durur (fail closed). Koşu
        başında da `False`: başlangıç mutabakatı geçmeden hiçbir artıran emir gitmez.
        """
        self.mutabakat_tamam = False
        try:
            emir = mutabakat(self.defter, self.adaptor, self.sembol, durdur=False)
        except (BorsaHatasi, ValueError, KeyError, TypeError) as hata:
            # ValueError/KeyError/TypeError: borsanın bozuk/tanınmayan yanıtı
            # (`BilinmeyenDurum` bir ValueError). Tahmin yok: mutabakat yapılamadı.
            self.baglanti_hatasi = f"{type(hata).__name__}: {hata}"
            self._olay("mutabakat_yapilamadi", {"asama": asama, "hata": self.baglanti_hatasi})
            return {"asama": asama, "ok": False, "hata": self.baglanti_hatasi, "halt": self.halt}
        self.son_mutabakat = {"asama": asama, **emir.sozluk()}
        if emir.halt:
            self.durdur(f"emir mutabakatı uyuşmazlığı: {emir.ozet()}")
        try:
            poz = pozisyon_mutabakati(self.defter, self.adaptor, self.sembol, durdur=False)
            self.son_pozisyon = poz.sozluk()
            if poz.halt:
                self.durdur(f"pozisyon farkı açıklanamıyor: {poz.ozet()}")
        except CipaYok as hata:
            self.son_pozisyon = {"halt": True, "cipa_yok": True, "hata": str(hata)}
            self.durdur("çıpa yok")
        except (PozisyonHatasi, BorsaHatasi, ValueError, KeyError, TypeError) as hata:
            self.son_pozisyon = {"hata": f"{type(hata).__name__}: {hata}"}
            self.baglanti_hatasi = str(hata)
            self._olay("mutabakat_yapilamadi", {"asama": asama, "hata": self.baglanti_hatasi})
        hatasiz = not self.son_pozisyon.get("hata")
        self.baglanti_hatasi = "" if hatasiz else self.baglanti_hatasi
        self.mutabakat_tamam = hatasiz and not self.halt
        return {
            "asama": asama,
            "ok": self.mutabakat_tamam,
            "emir_mutabakati": self.son_mutabakat,
            "pozisyon_mutabakati": self.son_pozisyon,
            "halt": self.halt,
        }

    # ================================================================ niyet

    def _kaydet(self, u: Uygulama) -> Uygulama:
        self.son_kararlar.append(u.sozluk())
        del self.son_kararlar[:-SON_KAYIT]
        self._olay("niyet", u.sozluk(), zaman_ms=u.karar_ms or None)
        return u

    def _engel(self, n: OnayliNiyet, engel: Engel, **ek: Any) -> Uygulama:
        return self._kaydet(
            Uygulama(
                sembol=n.sinyal.symbol,
                yon=str(n.sinyal.side),
                karar_ms=n.karar_ms,
                onayli_maruziyet=n.onayli_maruziyet,
                sonuc="engellendi" if engel is not Engel.HEDEFTE else "hedefte",
                engel=str(engel),
                **ek,
            )
        )

    def uygula(self, niyet: OnayliNiyet, *, son_kapali_bar_ms: int) -> Uygulama:
        """Onaylı niyeti (engeller → miktar → emir) uygular. Modül docstring'indeki tablo."""
        n = dogrula(niyet)
        if n.sinyal.symbol != self.sembol:
            raise HatHatasi(f"bu hat {self.sembol} için; niyet {n.sinyal.symbol}")
        azaltan = n.azaltma

        # 1-5: yapısal engeller — azaltanlar dahil hepsi.
        if self.mod is CalismaModu.DISABLED:
            return self._engel(n, Engel.MOD)
        if self.halt:
            return self._engel(n, Engel.HALT)
        acik = [e for e in self.defter.acik_emirler() if e.sembol == self.sembol]
        if any(e.durum is EmirDurumu.UNKNOWN for e in acik):
            return self._engel(n, Engel.BELIRSIZ_EMIR)
        if acik:
            return self._engel(n, Engel.ACIK_EMIR)
        if any(
            e.sembol == self.sembol and e.karar_ms == n.karar_ms
            and e.durum is not EmirDurumu.FAILED
            for e in self.defter.tumu()
        ):
            return self._engel(n, Engel.AYNI_BAR)

        # 6-7: artıranlar için.
        if not azaltan and not self._mod_tavani_izin_veriyor():
            return self._engel(n, Engel.MOD)
        if not azaltan and not self.mutabakat_tamam:
            return self._engel(n, Engel.MUTABAKAT)
        if not azaltan and self.safe_mode:
            return self._engel(n, Engel.SAFE_MODE)
        if not azaltan and n.karar_ms != son_kapali_bar_ms:
            return self._engel(n, Engel.BAYAT_KARAR)

        try:
            h = self.hesap()
        except BorsaHatasi as hata:
            self.baglanti_hatasi = f"{type(hata).__name__}: {hata}"
            return self._engel(n, Engel.BAGLANTI)

        # 8: borsa ölçümlü kayıp limitleri.
        simdi = self.saat()
        self.izleyici.isle(h.ozkaynak, simdi)
        self._durum_kaydet()
        if not azaltan:
            if self.limitler.kayip_tavani_asildi(h.ozkaynak):
                self._kayip_tavani_isaretle(h.ozkaynak)
                return self._engel(n, Engel.KAYIP_TAVANI)
            if h.ozkaynak < self.izleyici.zirve * (1.0 - self.limitler.drawdown_limiti):
                self.safe_isaretle(
                    f"drawdown {self.izleyici.drawdown(h.ozkaynak):.4f} > "
                    f"{self.limitler.drawdown_limiti} (execution hattı ölçümü)"
                )
                return self._engel(n, Engel.DRAWDOWN)
            if h.ozkaynak < self.izleyici.gun_basi * (1.0 - self.limitler.gunluk_zarar_limiti):
                return self._engel(n, Engel.GUNLUK_ZARAR)

        # 9: miktar ve tavanlar (yalnızca aşağı).
        miktar, kisitlayan = self._miktar(n, h)
        if miktar <= 0.0:
            return self._engel(n, Engel.HEDEFTE, kisitlayan=kisitlayan)

        try:
            sonuc = EmirMotoru(self.defter, self.adaptor).gonder(n, miktar)
        except BorsaHatasi as hata:
            self.baglanti_hatasi = f"{type(hata).__name__}: {hata}"
            return self._engel(n, Engel.BAGLANTI)
        return self._kaydet(self._sonuc(n, sonuc, miktar, h.fiyat, kisitlayan))

    def _miktar(self, n: OnayliNiyet, h: HesapGorunumu) -> tuple[float, tuple[str, ...]]:
        """Hedef maruziyetten emir miktarı. Tavanlar yalnızca aşağı çeker."""
        kisit: list[str] = []
        yon = str(n.sinyal.side).upper()
        if h.fiyat <= 0.0 or h.ozkaynak <= 0.0:
            return 0.0, ("gecersiz_olcum",)
        if yon == "FLAT":
            return max(h.miktar, 0.0), ()
        hedef = n.onayli_maruziyet
        for ad, tavan in (
            ("azami_maruziyet", self.limitler.azami_maruziyet),
            ("azami_brut_maruziyet", self.limitler.azami_brut_maruziyet),
        ):
            if hedef > tavan:
                hedef, kisit = tavan, [*kisit, ad]
        # Boyut tabanı koşunun **sermayesiyle** sınırlı: kâr birikse de emir büyüklüğü
        # sermaye tavanını (canlıda kademe, K-050/3) aşamaz — sermaye artışı yalnız yeni
        # kademe + onayla (K-114 denetimi). Zararda taban özkaynaktır (küçülür).
        taban = min(h.ozkaynak, self.limitler.sermaye_usdt)
        if taban < h.ozkaynak:
            kisit = [*kisit, "sermaye_tavani"]
        hedef_deger = hedef * taban
        fark = hedef_deger - h.pozisyon_degeri
        if yon == "BUY":
            if fark <= 0.0:
                return 0.0, tuple(kisit)
            if fark > h.nakit:
                fark, kisit = max(h.nakit, 0.0), [*kisit, "nakit"]
            return fark / h.fiyat, tuple(kisit)
        # SELL: hedefe in; pozisyondan fazlası satılamaz.
        if fark >= 0.0:
            return 0.0, tuple(kisit)
        return min(-fark / h.fiyat, max(h.miktar, 0.0)), tuple(kisit)

    def _sonuc(
        self,
        n: OnayliNiyet,
        s: GonderimSonucu,
        miktar: float,
        fiyat: float,
        kisitlayan: tuple[str, ...],
    ) -> Uygulama:
        d = s.emir.durum
        if d is EmirDurumu.GOLGE:
            ad = "golge"
        elif not s.gonderildi and d is EmirDurumu.REJECTED:
            ad = "kural_reddi"
        elif not s.gonderildi and d is EmirDurumu.FAILED:
            ad = "basarisiz"
        elif not s.gonderildi:
            ad = "zaten_var"
        elif d is EmirDurumu.UNKNOWN:
            ad = "belirsiz"
        elif d is EmirDurumu.REJECTED:
            ad = "borsa_reddi"
        else:
            ad = "gonderildi"
        return Uygulama(
            sembol=n.sinyal.symbol,
            yon=str(n.sinyal.side),
            karar_ms=n.karar_ms,
            onayli_maruziyet=n.onayli_maruziyet,
            sonuc=ad,
            miktar=s.emir.miktar if ad != "zaten_var" else miktar,
            notional=s.emir.miktar * fiyat,
            kisitlayan=kisitlayan,
            emir=s.emir.sozluk(),
        )

    # ================================================================ acil

    def acil_iptal(self, sebep: str) -> dict[str, Any]:
        """SAFE_MODE işareti + defterdeki ve borsadaki açık emirlerin iptali + doğrulama.

        Borsada olup defterde olmayan (yetim) emirler de iptal edilir: acil durumda
        maruziyeti azaltmak, kaydını bilmediğimiz bir emri yerinde bırakmaktan güvenli.
        Sonuç "kalan açık emir" sayısıyla raporlanır; sıfır değilse başarısız.
        """
        self.safe_isaretle(f"acil iptal: {sebep}")
        rapor: dict[str, Any] = {"sebep": sebep, "iptaller": [], "hatalar": []}
        if golge_mi(self.adaptor):
            rapor["not"] = "shadow: gönderilmiş emir yok, iptal edilecek bir şey yok"
        motor = EmirMotoru(self.defter, self.adaptor)
        for e in self.defter.acik_emirler():
            if e.sembol != self.sembol or golge_mi(self.adaptor):
                continue
            try:
                s = motor.iptal(e.istemci_kimligi)
                rapor["iptaller"].append({"kimlik": e.istemci_kimligi, **s.sozluk()})
            except Exception as hata:  # noqa: BLE001 — acil yol her hatayı raporlar
                rapor["hatalar"].append(f"{e.istemci_kimligi}: {hata}")
        try:
            kalan = self.adaptor.acik_emirler(self.sembol)
            bilinen = {e.istemci_kimligi for e in self.defter.tumu()}
            for b in kalan:
                if golge_mi(self.adaptor):
                    break
                try:
                    self.adaptor.emir_iptal(sembol=self.sembol, istemci_kimligi=b.istemci_kimligi)
                    rapor["iptaller"].append(
                        {"kimlik": b.istemci_kimligi, "yetim": b.istemci_kimligi not in bilinen}
                    )
                except Exception as hata:  # noqa: BLE001
                    rapor["hatalar"].append(f"{b.istemci_kimligi}: {hata}")
            rapor["kalan_acik_emir"] = len(self.adaptor.acik_emirler(self.sembol))
        except BorsaHatasi as hata:
            rapor["hatalar"].append(f"açık emirler okunamadı: {hata}")
            rapor["kalan_acik_emir"] = None
        rapor["basarili"] = rapor.get("kalan_acik_emir") == 0 and not rapor["hatalar"]
        self._olay("acil_iptal", rapor)
        return rapor

    # ================================================================ durum

    def durum(self, *, ek: dict[str, Any] | None = None) -> dict[str, Any]:
        """Panonun okuduğu tam durum. Borsa okunamıyorsa hesap alanı hata taşır."""
        emirler = self.defter.tumu(limit=SON_KAYIT)
        sayim = self.defter.sayim()
        try:
            h = self.hesap()
            hesap: dict[str, Any] = h.sozluk()
            hesap["drawdown"] = self.izleyici.drawdown(h.ozkaynak)
            hesap["gunluk_getiri"] = self.izleyici.gunluk(h.ozkaynak)
            hesap["pnl"] = h.ozkaynak - self.limitler.sermaye_usdt
            bakiye = {k: v.sozluk() for k, v in self.adaptor.bakiye().items()
                      if k in {self.adaptor.sembol_kurallari(self.sembol).taban_varlik,
                               self.adaptor.sembol_kurallari(self.sembol).kote_varlik}}
            acik_borsa = [e.sozluk() for e in self.adaptor.acik_emirler(self.sembol)]
            baglanti = {"ok": True, "saat_sapmasi_ms": self.adaptor.saat_sapmasi_ms()}
        except BorsaHatasi as hata:
            hesap, bakiye, acik_borsa = {"hata": str(hata)}, {}, []
            baglanti = {"ok": False, "hata": str(hata)}
        return {
            "mod": str(self.mod),
            "sembol": self.sembol,
            "zaman_ms": self.saat(),
            "halt": self.halt,
            "safe_mode": self.safe_mode,
            "limitler": self.limitler.sozluk(),
            "hesap": hesap,
            "bakiye": bakiye,
            "acik_emirler_borsa": acik_borsa,
            "emirler": {
                "sayim": sayim,
                "belirsiz": sayim.get(str(EmirDurumu.UNKNOWN), 0),
                "acik": sum(n for d, n in sayim.items() if EmirDurumu(d) in ACIK),
                "son": [e.sozluk() for e in emirler],
            },
            "son_kararlar": self.son_kararlar[-SON_KAYIT:],
            "mutabakat": self.son_mutabakat,
            "pozisyon_mutabakati": self.son_pozisyon,
            "baglanti": baglanti,
            **(ek or {}),
        }

    def durum_yaz(self, *, ek: dict[str, Any] | None = None) -> dict[str, Any]:
        d = self.durum(ek=ek)
        self._yaz(DURUM_DOSYASI, d)
        return d


__all__ = [
    "DURUM_DOSYASI",
    "SAFE_ISARETI",
    "Engel",
    "ExecutionHatti",
    "GuvenlikLimitleri",
    "HatHatasi",
    "HesapGorunumu",
    "KayipIzleyici",
    "Uygulama",
]
