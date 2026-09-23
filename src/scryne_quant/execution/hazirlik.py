"""Hazırlık raporu: "proje bitti mi, gerçek para konabilir mi?" sorusunun makine cevabı. (K-122)

Scryne'ın ölçütü: *"her şey hazır olduğundan emin olmadan hesaba gerçek para koymam; projenin
çalıştığını görmeden para atmam."* Bu modül o cümleyi iki ayrı, sayısal hükme çevirir:

1. **Sistem hazır:** bot gerçek bir borsada (testnet, sanal para) ve gerçek hesap üzerinde (shadow,
   salt okunur) `GOSTERIM_GUN` gün kesintilere dayanarak, hatasız ve mutabık çalıştı; arıza
   tatbikatları geçti; test takımı HEAD'de yeşil; R8 operasyon koşusu PASS.
2. **Strateji hazır:** en az bir strateji promotion zincirinde `live_adayi`na ulaştı (12 kapı +
   risk incelemesi + paper). Bu hükmü sistem hazırlığı değiştiremez; biri olmadan öteki "hazır"
   değildir.

3. **Mikro pilot hazır (K-129):** yalnız K-115 pilotu (100 USDT sermaye, 10 USDT kayıpta SAFE_MODE,
   tavanlar kodda) için: test takımı yeşil, testnet + shadow gösterimi `PILOT_GOSTERIM_GUN` gün aynı
   ölçütlerle temiz, kill tatbikatı geçti. R8 ve promotion **istemez**: pilot alfa iddiası taşımaz,
   promotion kanıtı üretmez ve kaybı kodda sabit tavanla sınırlı. Sermaye büyütme (Kademe ≥ 2) iki
   hükmün ikisini de ister; bu gevşetme yalnız pilot içindir (Scryne, 2026-09-23).

Hiçbir eşik sonuca bakılarak konmadı; hepsi gösterim döneminden **önce** yazıldı (K-122). Rapor
yalnızca okur: koşu dosyaları (`kosu.json`, `yurutucu.json`, `durum.json`, `rapor.json`,
`kill.json`), test kaydı, R8 sonucu, promotion kayıtları. Hiçbir şey yazmaz, hiçbir şey başlatmaz.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from scryne_quant.common.zaman import simdi_ms, timeframe_ms, utc_str
from scryne_quant.execution.canli_kapi import (
    KAPATILDI,
    KapiBaglami,
    Kontrol,
    kill_tatbikati_kontrolu,
    operasyon_kontrolu,
    testler_kontrolu,
)
from scryne_quant.live import kill as kill_mod

KOSU_KOKU: Final = Path("runs/execution")

#: Gösterim koşuları ve modları (gözetmen `tools/gosterim_gozetmen.ps1` bunları ayakta tutar).
GOSTERIM_KOSULARI: Final[dict[str, str]] = {
    "gosterim-testnet": "TESTNET",
    "gosterim-shadow": "SHADOW",
}
#: Kesintisiz gösterim süresi (gün). R8 ile aynı: iki haftalık dengeleme turu + ay sınırı
#: görecek kadar uzun, bekleme olarak katlanılabilecek kadar kısa (K-111/2).
GOSTERIM_GUN: Final = 14.0
#: Mikro pilot için gösterim süresi (K-129): bir haftalık dengeleme turu + hafta sonu; pilotun
#: kaybı kodda 10 USDT ile sınırlı olduğu için 14 günün yarısı.
PILOT_GOSTERIM_GUN: Final = 7.0
#: Testnet'te dolan emir (en az iki tam tur: aç-kapa, aç-kapa). Shadow'da GOLGE emir.
ASGARI_DOLAN: Final = 4
ASGARI_GOLGE: Final = 4
#: Kaçırılan karar barı oranı üst sınırı (kesinti yüzünden karar üretilmeyen bar / işlenen bar).
#: %2: 14 günde (336 bar) en çok ~7 bar — bir gecelik ağ kopması; daha fazlası güvenilmez host.
AZAMI_KACIRILAN_ORAN: Final = 0.02
#: Son işlenen barın tazeliği: beklenen son kapanmış bardan en çok bu kadar bar geride.
AZAMI_GECIKME_BAR: Final = 2
#: Yeniden başlatma tatbikatı: en az bu kadar yeniden başlatmadan sonra mutabakat temiz.
ASGARI_YENIDEN_BASLATMA: Final = 1


@dataclass
class HazirlikRaporu:
    sistem: list[Kontrol] = field(default_factory=list)
    strateji: list[Kontrol] = field(default_factory=list)
    pilot: list[Kontrol] = field(default_factory=list)
    zaman_ms: int = 0

    @property
    def sistem_hazir(self) -> bool:
        return all(k.gecti is True for k in self.sistem)

    @property
    def strateji_hazir(self) -> bool:
        return all(k.gecti is True for k in self.strateji)

    @property
    def gercek_paraya_hazir(self) -> bool:
        return self.sistem_hazir and self.strateji_hazir

    @property
    def pilot_hazir(self) -> bool:
        """K-129: mikro pilotun hazırlık hükmü (R8 ve promotion'dan bağımsız)."""
        return bool(self.pilot) and all(k.gecti is True for k in self.pilot)

    def sozluk(self) -> dict[str, Any]:
        return {
            "zaman_utc": utc_str(self.zaman_ms),
            "sistem_hazir": self.sistem_hazir,
            "strateji_hazir": self.strateji_hazir,
            "gercek_paraya_hazir": self.gercek_paraya_hazir,
            "pilot_hazir": self.pilot_hazir,
            "sistem": [k.sozluk() for k in self.sistem],
            "pilot": [k.sozluk() for k in self.pilot],
            "strateji": [k.sozluk() for k in self.strateji],
        }


def _json(p: Path) -> dict[str, Any] | None:
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
    except (OSError, ValueError):
        return None


def kosu_kontrolu(
    kok: Path, ad: str, mod: str, *, simdi: int, asgari_gun: float = GOSTERIM_GUN
) -> Kontrol:
    """Bir gösterim koşusunun tüm ölçütleri tek kontrolde; kalan her madde ayrıntıda."""
    dizin = kok / KOSU_KOKU / ad
    kimlik, yur, durum = (_json(dizin / f) for f in ("kosu.json", "yurutucu.json", "durum.json"))
    if kimlik is None or yur is None or durum is None:
        return Kontrol(f"kosu:{ad}", False, "koşu yok ya da hiç bar işlememiş",
                       "gözetmen: `tools/gosterim_gozetmen.ps1` (K-122)")
    if kimlik.get("mod") != mod:
        return Kontrol(f"kosu:{ad}", False, f"mod {kimlik.get('mod')} ≠ {mod}")
    sayac = yur.get("sayac") or {}
    tf = timeframe_ms(str(kimlik.get("timeframe", "1h")))
    eksik: list[str] = []

    bas = int(yur.get("baslangic_ms") or 0)
    gun = (simdi - bas) / 86_400_000 if bas else 0.0
    if gun < asgari_gun:
        eksik.append(f"süre {gun:.1f}/{asgari_gun:.0f} gün")
    try:
        pid = kill_mod.pid_oku(dizin / "kosu")
    except TypeError:
        # Bozuk pid dosyası (JSON ama nesne değil): `live/` R8 için dondurulmuş (K-111), okuyucu
        # orada düzeltilmedi; rapor çökmez, "çalışmıyor" der (K-122).
        pid = None
    if (dizin / KAPATILDI).is_file():
        eksik.append("koşu kapatılmış")
    elif pid is None or not kill_mod.surec_yasiyor_mu(pid):
        eksik.append("süreç çalışmıyor")
    son = yur.get("son_islenen_ms")
    beklenen = (simdi // tf) * tf - tf
    if son is None or (beklenen - int(son)) > AZAMI_GECIKME_BAR * tf:
        eksik.append(f"veri bayat (son bar {utc_str(int(son)) if son else '—'})")
    if durum.get("halt"):
        eksik.append(f"halt: {durum['halt']}")
    if (dizin / "kosu.safemode").is_file():
        eksik.append("SAFE_MODE açık")
    emir = durum.get("emirler") or {}
    if int(emir.get("belirsiz", 0)):
        eksik.append("çözülmemiş UNKNOWN emir")
    poz = durum.get("pozisyon_mutabakati") or {}
    if not poz or poz.get("halt") or poz.get("hata"):
        eksik.append("pozisyon mutabakatı temiz değil")
    sayim = emir.get("sayim") or {}
    if mod == "TESTNET" and int(sayim.get("FILLED", 0)) < ASGARI_DOLAN:
        eksik.append(f"dolan emir {sayim.get('FILLED', 0)}/{ASGARI_DOLAN}")
    if mod == "SHADOW":
        golge = int(sayim.get("GOLGE", 0))
        gonderilmis = sum(int(v) for k, v in sayim.items() if k not in ("GOLGE", "CREATED",
                                                                          "VALIDATED", "REJECTED"))
        if golge < ASGARI_GOLGE:
            eksik.append(f"GOLGE emir {golge}/{ASGARI_GOLGE}")
        if gonderilmis:
            eksik.append(f"shadow'da gönderilmiş emir {gonderilmis} (OLMAMALI)")
    bar = int(sayac.get("bar", 0))
    kacirilan = int(sayac.get("kacirilan_karar", 0))
    if bar and kacirilan / bar > AZAMI_KACIRILAN_ORAN:
        eksik.append(f"kaçırılan karar {kacirilan}/{bar} > %{AZAMI_KACIRILAN_ORAN * 100:.0f}")
    if int(sayac.get("saat_sicramasi", 0)):
        eksik.append(f"saat sıçraması {sayac['saat_sicramasi']}")
    if int(sayac.get("yeniden_baslatma", 0)) < ASGARI_YENIDEN_BASLATMA:
        eksik.append("yeniden başlatma tatbikatı yok")

    ozet = (f"{gun:.1f} gün · bar {bar} · kaçırılan {kacirilan} · bağlantı hatası "
            f"{sayac.get('baglanti_hatasi', 0)} · yeniden başlatma "
            f"{sayac.get('yeniden_baslatma', 0)} (plansız {sayac.get('plansiz_kesinti', 0)})"
            f" · emir {dict(sayim)}")
    if eksik:
        return Kontrol(f"kosu:{ad}", False, f"{ozet} — eksik: {'; '.join(eksik)}",
                       "gösterim dönemi sürüyor (K-122)")
    return Kontrol(f"kosu:{ad}", True, ozet, kanit=f"{ad}:{bas}:{bar}")


def strateji_kontrolu(kok: Path) -> Kontrol:
    """En az bir strateji `live_adayi` (ya da ötesi) aşamasında mı?"""
    from scryne_quant.risk.promotion import SIRA, Asama

    hedef = SIRA.index(Asama.LIVE_ADAYI)
    en_iyi: tuple[int, str, str] = (-1, "", "yok")
    for p in sorted((kok / "runs" / "promotion").glob("*.json")):
        d = _json(p) or {}
        try:
            asama = Asama(str(d.get("asama", "yok")))
        except ValueError:
            continue
        sira = SIRA.index(asama) if asama in SIRA else -1
        if sira > en_iyi[0]:
            en_iyi = (sira, p.stem, str(asama))
    if en_iyi[0] >= hedef:
        return Kontrol("promotion", True, f"{en_iyi[1]}: {en_iyi[2]}")
    return Kontrol(
        "promotion", False,
        f"promotion'u geçen strateji yok (en ileri: {en_iyi[1] or '—'} {en_iyi[2]})",
        "12 kapı + risk incelemesi + paper (K-010, K-119); gerçek para için şart",
    )


def rapor(kok: str | Path = ".", *, simdi: int | None = None) -> HazirlikRaporu:
    kok = Path(kok)
    zaman = simdi if simdi is not None else simdi_ms()
    b = KapiBaglami(kok=kok)
    r = HazirlikRaporu(zaman_ms=zaman)
    r.sistem.append(testler_kontrolu(b))
    for ad, mod in GOSTERIM_KOSULARI.items():
        r.sistem.append(kosu_kontrolu(kok, ad, mod, simdi=zaman))
    r.sistem.append(kill_tatbikati_kontrolu(b))
    r.sistem.append(operasyon_kontrolu(b))
    r.strateji.append(strateji_kontrolu(kok))
    r.pilot.append(testler_kontrolu(b))
    for ad, mod in GOSTERIM_KOSULARI.items():
        r.pilot.append(kosu_kontrolu(kok, ad, mod, simdi=zaman, asgari_gun=PILOT_GOSTERIM_GUN))
    r.pilot.append(kill_tatbikati_kontrolu(b))
    return r


__all__ = [
    "ASGARI_DOLAN",
    "ASGARI_GOLGE",
    "AZAMI_KACIRILAN_ORAN",
    "GOSTERIM_GUN",
    "GOSTERIM_KOSULARI",
    "PILOT_GOSTERIM_GUN",
    "HazirlikRaporu",
    "kosu_kontrolu",
    "rapor",
    "strateji_kontrolu",
]
