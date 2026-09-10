"""Risk durumu: motorun barlar arasında hatırladığı her şey. (§11, K-008, K-032)

Risk kararlarının çoğu **tek bir bara bakarak verilemez**: "bugün ne kadar kaybettim",
"zirveden ne kadar düştüm", "kaç işlem üst üste kaybettim", "cooldown bitti mi" — hepsi
geçmiş gerektirir. O geçmiş buradadır ve başka hiçbir yerde kopyası yoktur.

**Neden ayrı bir sınıf, neden motorun içinde alanlar değil:** Faz 6'nın bitti kriteri
"süreç öldürülüp yeniden başlatıldığında pozisyon ve emir state'i doğru toparlanıyor"
diyor. Risk durumu toparlanmazsa, yeniden başlayan süreç günlük zarar limitini sıfırlamış
olur — yani limitin tek işi olan şeyi, **süreç kadar uzun bir hafıza**yı kaybeder.
Sıfırlanan bir günlük zarar limiti, limit değildir; süreç her çöküşte kendini affeder.
Bu yüzden durum serileştirilebilir (`sozluk`/`yukle`) ve bu Faz 5'te hazır.

**Değişmez değil, bilinçli olarak.** Portföy (`portfolio/durum.py`) değişmezdir çünkü
geçmişi yanlışlıkla paylaşmak equity eğrisini bozar. Risk durumu tam tersi: barlar
ilerledikçe **aynı** nesnenin güncellenmesi isteniyor, çünkü "bu motorun durumu" diye tek
bir gerçek var. İki risk durumu nesnesinin aynı anda canlı olması, hangisinin günlük
zararı tuttuğu belirsiz bir sistem demek olurdu.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

GUN_MS = 86_400_000

#: Kalıcı risk durumunun yeri. `runs/` `.gitignore`'da — bu dosya çalışma durumudur,
#: kaynak kod değil.
VARSAYILAN_DURUM_YOLU: Final = Path("runs/risk-durum.json")


@dataclass(slots=True)
class RiskDurumu:
    """Motorun çalışma zamanı hafızası. Tek örnek, yerinde güncellenir."""

    # --------------------------------------------------------------- özkaynak

    zirve_ozkaynak: float = 0.0
    """Görülen en yüksek özkaynak. Drawdown bunun üzerinden ölçülür."""

    son_ozkaynak: float = 0.0

    gun_basi_ozkaynak: float = 0.0
    """İçinde bulunulan UTC gününün **ilk** barındaki özkaynak. Günlük zararın tabanı."""

    gun: int = -1
    """İçinde bulunulan UTC günü (epoch gün sayısı). −1 = hiç bar işlenmedi."""

    # ----------------------------------------------------------------- işlem

    ardisik_kayip: int = 0
    """Üst üste kaybeden kapanmış işlem sayısı. Kazanan bir işlem bunu sıfırlar."""

    cooldown_bitis_ms: int | None = None
    """Cooldown'ın sona erdiği bar zamanı (dahil değil). `None` = cooldown yok."""

    # ------------------------------------------------------------ kill switch

    safe_mode: bool = False
    """K-008/4: kill switch tetiklendi. Çıkış **yalnızca elle onayla** (`serbest_birak`)."""

    safe_mode_sebep: str = ""
    safe_mode_ms: int | None = None

    # ----------------------------------------------------------------- sayaç

    bar_sayisi: int = 0
    gun_sayisi: int = 0
    kapanan_islem: int = 0

    # ----------------------------------------------------------------- ölçüm

    @property
    def drawdown(self) -> float:
        """Zirveden düşüş kesri [0,1]. Zirve yoksa 0."""
        if self.zirve_ozkaynak <= 0.0:
            return 0.0
        return max(0.0, 1.0 - self.son_ozkaynak / self.zirve_ozkaynak)

    @property
    def gunluk_getiri(self) -> float:
        """Gün başından bu yana getiri kesri. Negatifi günlük zarardır."""
        if self.gun_basi_ozkaynak <= 0.0:
            return 0.0
        return self.son_ozkaynak / self.gun_basi_ozkaynak - 1.0

    def cooldownda_mi(self, zaman_ms: int) -> bool:
        return self.cooldown_bitis_ms is not None and zaman_ms < self.cooldown_bitis_ms

    # ---------------------------------------------------------------- güncelleme

    def bar_isle(self, zaman_ms: int, ozkaynak: float) -> None:
        """Yeni bir barın özkaynağını işler: gün dönümü, zirve, drawdown tabanı.

        **Gün dönümü özkaynak güncellenmeden önce yapılır.** Ters sırada, günün ilk
        barının zararı önceki güne yazılır ve her gün bir barlık kayma birikir — sessiz,
        makul görünen, gittikçe büyüyen bir hata.
        """
        if ozkaynak <= 0.0:
            raise ValueError(f"özkaynak pozitif olmalı: {ozkaynak}")

        gun = zaman_ms // GUN_MS
        if gun != self.gun:
            # Yeni gün: günlük zarar limiti kendiliğinden kalkar. Drawdown kalkmaz —
            # biri fren, diğeri birikmiş hasar (limitler.py'deki gerekçe).
            self.gun = int(gun)
            self.gun_basi_ozkaynak = ozkaynak
            self.gun_sayisi += 1

        self.son_ozkaynak = ozkaynak
        self.zirve_ozkaynak = max(self.zirve_ozkaynak, ozkaynak)
        self.bar_sayisi += 1

    def islem_kapandi(
        self, net_pnl: float, zaman_ms: int, *, limit: int, cooldown_ms: int
    ) -> bool:
        """Kapanan bir işlemi işler. Cooldown tetiklendiyse `True` döner.

        `limit` ve `cooldown_ms` motordan geliyor: durum nesnesi ne limitleri ne timeframe'i
        biliyor ve bilmemeli. Bar süresini iki yerde tutmak, ikisinin ayrışacağı gün
        cooldown'ı sessizce yanlış uzunlukta yapardı.

        **Başa başın (`net_pnl == 0`) kayıp sayılması bilinçli.** Bir tur maliyetini
        çıkardıktan sonra tam sıfırda kapanmış bir işlem kazanmamıştır; kazanç sayılsaydı
        ardışık kayıp sayacını sıfırlar ve cooldown'ı sessizce geciktirirdi.
        """
        self.kapanan_islem += 1
        if net_pnl > 0.0:
            self.ardisik_kayip = 0
            return False

        self.ardisik_kayip += 1
        if self.ardisik_kayip < limit or cooldown_ms <= 0:
            return False

        self.cooldown_bitis_ms = zaman_ms + cooldown_ms
        # Sayaç sıfırlanıyor: sıfırlanmazsa cooldown bittikten sonraki **ilk** kayıp
        # sayacı limitin üstüne taşır ve cooldown her kayıpta yeniden tetiklenir — yani
        # limit 10'dan sessizce 1'e düşer.
        self.ardisik_kayip = 0
        return True

    def kill(self, sebep: str, zaman_ms: int) -> None:
        """SAFE_MODE'a geçirir (K-008/4). Zaten SAFE_MODE'daysa ilk sebep korunur.

        İlk sebebin korunması önemli: ikinci bir tetikleyici, birincinin **sonucu**
        olabilir (drawdown kill'i tetikler, sonra veri akışı kesilir). Sebebi üzerine
        yazmak, kök nedeni silmek olurdu.
        """
        if self.safe_mode:
            return
        self.safe_mode = True
        self.safe_mode_sebep = sebep
        self.safe_mode_ms = zaman_ms

    def serbest_birak(self) -> None:
        """SAFE_MODE'dan çıkar. **Yalnızca elle onayla çağrılır** (K-008/4).

        Kod içinden otomatik çağrılmaması bir sözleşme: bu fonksiyonu bir koşula bağlayan
        her satır, kill switch'i kendini kapatan bir uyarıya dönüştürür. Zorlaması
        `tests/unit/test_kill_switch.py`'de — `risk/` içinde bu metodu çağıran tek yer
        elle onay yolu olmalı.
        """
        self.safe_mode = False
        self.safe_mode_sebep = ""
        self.safe_mode_ms = None

    # -------------------------------------------------------------- kalıcılık

    def sozluk(self) -> dict[str, Any]:
        """Durumun tam serileştirmesi. Faz 6'nın restart kriteri bunu okuyacak."""
        return {
            "zirve_ozkaynak": self.zirve_ozkaynak,
            "son_ozkaynak": self.son_ozkaynak,
            "gun_basi_ozkaynak": self.gun_basi_ozkaynak,
            "gun": self.gun,
            "ardisik_kayip": self.ardisik_kayip,
            "cooldown_bitis_ms": self.cooldown_bitis_ms,
            "safe_mode": self.safe_mode,
            "safe_mode_sebep": self.safe_mode_sebep,
            "safe_mode_ms": self.safe_mode_ms,
            "bar_sayisi": self.bar_sayisi,
            "gun_sayisi": self.gun_sayisi,
            "kapanan_islem": self.kapanan_islem,
            "drawdown": self.drawdown,
            "gunluk_getiri": self.gunluk_getiri,
        }

    @classmethod
    def yukle(cls, kayit: dict[str, Any]) -> RiskDurumu:
        """Serileştirilmiş durumdan geri yükler.

        Türetilmiş alanlar (`drawdown`, `gunluk_getiri`) **okunmaz**: onlar property ve
        kaynaklarından yeniden hesaplanır. Kayıttan okunsalardı, kayıtla kaynakların
        ayrışabildiği bir durum doğardı — ve o ayrışma kimseye görünmezdi.
        """
        alanlar = {
            a: kayit[a]
            for a in (
                "zirve_ozkaynak",
                "son_ozkaynak",
                "gun_basi_ozkaynak",
                "gun",
                "ardisik_kayip",
                "cooldown_bitis_ms",
                "safe_mode",
                "safe_mode_sebep",
                "safe_mode_ms",
                "bar_sayisi",
                "gun_sayisi",
                "kapanan_islem",
            )
            if a in kayit
        }
        return cls(**alanlar)


def durum_yaz(durum: RiskDurumu, yol: str | Path = VARSAYILAN_DURUM_YOLU) -> Path:
    """Durumu diske yazar. Faz 6'nın restart kriterinin yarısı (diğer yarısı portföy).

    Geçici dosyaya yazıp taşıma: yazım ortasında ölen bir süreç, yarım bir risk durumu
    bırakmamalı. Yarım okunan bir durum, `safe_mode` bayrağını kaybedebilir — yani kill
    switch bir çöküşle sıfırlanır.
    """
    p = Path(yol)
    p.parent.mkdir(parents=True, exist_ok=True)
    gecici = p.with_suffix(".json.tmp")
    gecici.write_text(
        json.dumps(durum.sozluk(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    gecici.replace(p)
    return p


def durum_oku(yol: str | Path = VARSAYILAN_DURUM_YOLU) -> RiskDurumu:
    """Durumu diskten okur. Dosya yoksa **sıfırdan** bir durum döner.

    Eksik dosyanın boş duruma düşmesi burada güvenli: boş durumda `safe_mode` kapalı ama
    zirve özkaynak da sıfır, yani ilk bar zirveyi kurar ve drawdown sıfırdan başlar. Riskli
    olan tersi olurdu — eksik dosyanın "her şey yolunda, devam et" diye okunması.
    """
    p = Path(yol)
    if not p.exists():
        return RiskDurumu()
    return RiskDurumu.yukle(json.loads(p.read_text(encoding="utf-8")))


__all__ = ["GUN_MS", "VARSAYILAN_DURUM_YOLU", "RiskDurumu", "durum_oku", "durum_yaz"]
