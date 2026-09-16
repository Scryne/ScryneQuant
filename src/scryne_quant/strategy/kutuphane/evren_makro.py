"""Evren kıyasının üstüne makro stres engeli. (Faz 12, `makro_rejim` programı)

Program kaydı `docs/Arastirma-Programlari.jsonl`; kaynak ölçüsü taslak §1.3 ve program
kaydının `kaynak_olcumu` alanı. Veri: `data/makro.py` (ALFRED vintage'ları, PIT).

**Soru:** Kripto fiyat serileri ABD risk iştahı bağlamını (oynaklık, finansal koşullar)
taşımıyor (ölçüldü: dört makro serinin günlük değişimi BTC getirisinin yalnızca R² 0,099'unu
açıklıyor). Stres rejiminde yeni risk almamak, evren kıyasını iyileştirir mi?

**Makro yalnızca engelleyicidir** (K-037, K-052, program kaydı). İzin vermez, alım
üretmez, kıyasın seçimini değiştirmez; yalnızca kıyasın **risk artıran** niyetlerini
stres rejiminde siler.

## Önden sabitlenen kurallar

- **Stres:** serinin `pencere_gun` günlük PIT persentili `≥ esik`. VIX'te yüksek oynaklık,
  NFCI'de sıkı finansal koşullar (NFCI pozitif yön = sıkı).
- **Stres rejiminde yeniden dengeleme:** kıyasın hedefi normal kurulur, sonra:
  - hedefi **0** olan niyet (çıkış) aynen geçer;
  - elde olan sembolde hedefi **mevcut ağırlığın altında ya da eşit** olan niyet geçer;
  - geri kalan her niyet (yeni isim, mevcut pozisyonu büyütme) **silinir**. Bahsedilmeyen
    sembol "olduğu gibi kal" demektir (`hedef.py`), yani silinen niyet bir satış değildir.
- **Makro bilgisi yoksa** (ilk vintage öncesi, pencere dolmamış): stres yok sayılır, kıyas
  aynen çalışır. Bilginin yokluğu engelleme gerekçesi değil — funding filtresiyle aynı kural.
- **Takvim kıyasla aynı.** Stres biterse yeni girişler bir sonraki yeniden dengelemede olur;
  araya dengeleme sokmak kıyastan ikinci bir farkı içeri alırdı.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from scryne_quant.features.motor import OzellikTanimi
from scryne_quant.strategy.evren import EvrenBaglam
from scryne_quant.strategy.hedef import HedefPortfoy, hedef_kur
from scryne_quant.strategy.kutuphane.evren_esit_agirlik import EvrenEsitAgirlik

MAKRO = "makro_persentil"

#: Yükleyicinin hesapladığı pencereler (`data/makro.PENCERELER_GUN`). Strateji paketi veri
#: katmanını import edemez (K-003), bu yüzden liste burada tekrarlanıyor ve bir test ikisinin
#: aynı olduğunu kontrol ediyor.
PENCERELER_GUN = (30, 90, 180, 365)


class _MakroEngel(EvrenEsitAgirlik):
    """İki çekilişin ortak iskeleti. Alt sınıf yalnızca seriyi seçer."""

    ad: ClassVar[str] = ""
    seri: ClassVar[str] = ""

    def __init__(
        self,
        pencere_gun: int = 90,
        esik: float = 0.8,
        azami_enstruman: int = 10,
        yeniden_dengele_bar: int = 168,
        hedef_brut: float = 0.2,
    ) -> None:
        super().__init__(
            yeniden_dengele_bar=yeniden_dengele_bar,
            azami_enstruman=azami_enstruman,
            azami_agirlik=float(hedef_brut) / int(azami_enstruman),
            hedef_brut=hedef_brut,
            esit_agirlik=True,
        )
        self.parametreler = {
            "pencere_gun": pencere_gun,
            "esik": esik,
            "azami_enstruman": azami_enstruman,
            "yeniden_dengele_bar": yeniden_dengele_bar,
            "hedef_brut": hedef_brut,
        }
        self.dogrula()
        self.stres_dengeleme = 0
        """Stres rejimine denk gelen yeniden dengeleme sayısı (ölçüm, karar değil)."""

    def dogrula(self) -> None:
        p = self.parametreler
        if int(p["yeniden_dengele_bar"]) < 1:
            raise ValueError("yeniden_dengele_bar ≥ 1 olmalı")
        if "pencere_gun" in p and int(p["pencere_gun"]) not in PENCERELER_GUN:
            raise ValueError(f"pencere_gun {PENCERELER_GUN} kümesinden olmalı")
        if "esik" in p and not 0.0 < float(p["esik"]) <= 1.0:
            raise ValueError("esik (0, 1] aralığında olmalı")

    def hazirla(self) -> None:
        super().hazirla()
        self.stres_dengeleme = 0

    def ozellikler(self) -> Sequence[OzellikTanimi]:
        alan = f"{self.seri}_p{int(self.parametreler['pencere_gun'])}"
        return (*super().ozellikler(), OzellikTanimi(MAKRO, alan, {}))

    def _stres(self, ctx: EvrenBaglam) -> bool:
        # Makro alan bütün sembollerde aynı dizi: ilk hazır üye yeterli.
        for sembol in ctx.uyeler():
            b = ctx.enstruman(sembol)
            if b.hazir(MAKRO):
                return b.ozellik(MAKRO) >= float(self.parametreler["esik"])
        return False

    def on_bar(self, ctx: EvrenBaglam) -> HedefPortfoy | None:
        hedef = super().on_bar(ctx)
        if hedef is None or not self._stres(ctx):
            return hedef
        self.stres_dengeleme += 1
        kalan = []
        for sinyal in hedef.sinyaller:
            # Pozisyonu olmayan sembolde `exposure` 0: yeni isim her zaman silinir.
            mevcut = ctx.pozisyon(sinyal.symbol).exposure
            if sinyal.target_exposure <= 0.0 or (
                mevcut > 0.0 and sinyal.target_exposure <= mevcut
            ):
                kalan.append(sinyal)
        return hedef_kur(hedef.timestamp, kalan, yontem=hedef.yontem)

    def sozluk(self) -> dict[str, Any]:
        govde = super().sozluk()
        govde.pop("kiyas", None)
        return govde


class EvrenMakroVix(_MakroEngel):
    """VIX PIT persentili yüksekken risk artırma."""

    ad = "evren_makro_vix"
    seri = "vix"


class EvrenMakroNfci(_MakroEngel):
    """NFCI (vintage, PIT) persentili yüksekken — finansal koşullar sıkıyken — risk artırma."""

    ad = "evren_makro_nfci"
    seri = "nfci"


__all__ = ["MAKRO", "PENCERELER_GUN", "EvrenMakroNfci", "EvrenMakroVix"]
