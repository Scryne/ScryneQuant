"""Kesitsel sıralama aileleri: evren içinde hangi dilim taşınır? (Faz 12, `kesitsel_fiyat`)

Program kaydı `docs/Arastirma-Programlari.jsonl`, taslak `docs/Faz-12-Program-Taslaklari.md`.
Üç aile, **aynı iskelet**; yalnızca skor farklı:

| Aile | Skor (büyük = tercih) | Soru |
| --- | --- | --- |
| `kesitsel_guc` | `roc(pencere)` | Son dönemde iyi gideni tutmak işe yarıyor mu? |
| `kesitsel_ters` | `−roc(pencere)` | Kısa vadede geride kalan toparlanıyor mu? |
| `kesitsel_dusuk_oynaklik` | `−atr(pencere)/fiyat` | Sakin dilim riske göre daha iyi mi? |

İskeletin kıyasla (`evren_esit_agirlik`, K-030) **aynı** olması bilinçli: aynı evren, aynı
yeniden dengeleme takvimi, aynı kurma katmanı (`strategy/kurma.py`), aynı eşit ağırlık.
Kıyasla tek fark seçimin **skoru**; dolayısıyla kıyasın üstüne çıkan fark skora
atfedilebilir.

## Sabit tutulanlar (ızgara ekseni değil)

- **Eşit ağırlık.** Oynaklık ayarlı boyutun kendi etkisi Faz 10'da ayrıca ölçüldü; burada
  da açılırsa "skor mu işe yaradı, boyut mu" sorusu ayrışmaz.
- **`hedef_brut` = 0,2.** Faz 4'ün her çekilişi `SABIT_MARUZIYET = 0,2` ile koşuldu ve
  K-019'un `max_drawdown ≤ 0,25` kapısı o maruziyette kalibre edildi. Evren kıyasının tam
  maruziyetteki düşüşü %57-68 (Faz 10); aynı kapıya tam maruziyetle gitmek programı kapıya
  varmadan öldürürdü. Maruziyeti taramak ise `research/izgaralar.py`nin uyarısı: yükselen
  varlıkta "daha çok risk al" cevabı her zaman bulunur.
- **Oynaklık ölçüsü** kıyasınkiyle aynı (ATR 14 / fiyat): eşit ağırlıkta boyuta girmiyor ama
  aday uygunluğu iki stratejide aynı olmalı.

## Isınmamış enstrüman aday değildir

Skor veya ATR `hazir` değilse (yeni listelenmiş sembol) o sembol o yeniden dengelemede
sıralamaya girmez. Sıfır skorla girmesi, geçmişi olmayan bir sembolü sıralamanın ortasına
koymak olurdu.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from scryne_quant.features.motor import OzellikTanimi
from scryne_quant.strategy.evren import EvrenBaglam
from scryne_quant.strategy.hedef import HedefPortfoy
from scryne_quant.strategy.kurma import Aday, KurmaAyarlari, kur
from scryne_quant.strategy.temel import PortfoyStratejisi

#: Kıyasla aynı oynaklık penceresi (`evren_esit_agirlik.ATR_PENCERESI`).
ATR_PENCERESI = 14

#: Bkz. modül başlığı: Faz 4'ün sabit maruziyeti.
VARSAYILAN_HEDEF_BRUT = 0.2


class _Kesitsel(PortfoyStratejisi):
    """Üç ailenin ortak iskeleti. Alt sınıf yalnızca `_skor` ve özelliğini tanımlar."""

    ad: ClassVar[str] = ""
    neden: ClassVar[str] = "KESITSEL"

    def __init__(
        self,
        pencere: int = 720,
        azami_enstruman: int = 10,
        yeniden_dengele_bar: int = 168,
        hedef_brut: float = VARSAYILAN_HEDEF_BRUT,
    ) -> None:
        super().__init__(
            pencere=pencere,
            azami_enstruman=azami_enstruman,
            yeniden_dengele_bar=yeniden_dengele_bar,
            hedef_brut=hedef_brut,
        )
        self._ayarlar = KurmaAyarlari(
            yontem="KESITSEL_ESIT",
            azami_enstruman=int(azami_enstruman),
            hedef_brut=float(hedef_brut),
            # Tavan eşit payın kendisi: eşit ağırlıkta hiçbir isim payını aşmıyor, tavanın
            # bağlaması yalnızca aday sayısı `azami_enstruman`ın altına düştüğünde olur ve
            # o durumda artan brüt nakitte kalır (kurma katmanının kuralı).
            azami_agirlik=float(hedef_brut) / int(azami_enstruman),
            esit_agirlik=True,
        )
        self._son_dengeleme: int | None = None

    def dogrula(self) -> None:
        p = self.parametreler
        if int(p["pencere"]) < 2:
            raise ValueError("pencere ≥ 2 olmalı")
        if int(p["azami_enstruman"]) < 1:
            raise ValueError("azami_enstruman ≥ 1 olmalı")
        if int(p["yeniden_dengele_bar"]) < 1:
            raise ValueError("yeniden_dengele_bar ≥ 1 olmalı")
        if not 0.0 < float(p["hedef_brut"]) <= 1.0:
            raise ValueError("hedef_brut (0, 1] aralığında olmalı")

    def hazirla(self) -> None:
        self._son_dengeleme = None

    def _skor_ozelligi(self) -> OzellikTanimi:
        raise NotImplementedError

    def _skor(self, baglam: Any) -> float:
        raise NotImplementedError

    def ozellikler(self) -> Sequence[OzellikTanimi]:
        return (OzellikTanimi("atr", "atr", {"pencere": ATR_PENCERESI}), self._skor_ozelligi())

    def isinma_bar(self) -> int:
        return max(ATR_PENCERESI, int(self.parametreler["pencere"])) + 2

    def on_bar(self, ctx: EvrenBaglam) -> HedefPortfoy | None:
        periyot = int(self.parametreler["yeniden_dengele_bar"])
        i = ctx.uzunluk - 1
        if self._son_dengeleme is not None and i - self._son_dengeleme < periyot:
            return None

        adaylar: list[Aday] = []
        for sembol in ctx.uyeler():
            baglam = ctx.enstruman(sembol)
            if not baglam.hazir("atr", "skor_ham"):
                continue
            fiyat = baglam.bar("close")
            if fiyat <= 0.0:
                continue
            oynaklik = baglam.ozellik("atr") / fiyat
            if oynaklik <= 0.0:
                continue
            adaylar.append(
                Aday(
                    sembol=sembol,
                    skor=self._skor(baglam),
                    oynaklik=oynaklik,
                    mevcut_agirlik=ctx.pozisyon(sembol).exposure,
                    reason=self.neden,
                    confidence=0.5,
                )
            )

        if not adaylar and not ctx.acik_pozisyonlar():
            return None
        self._son_dengeleme = i
        return kur(
            ctx.zaman,
            adaylar,
            self._ayarlar,
            acik_pozisyonlar=tuple(s for s in ctx.acik_pozisyonlar() if s in ctx.gorunur()),
        )


class KesitselGuc(_Kesitsel):
    """Göreli güç: trailing getirisi en yüksek `azami_enstruman` üye."""

    ad = "kesitsel_guc"
    neden = "KESITSEL_GUC"

    def _skor_ozelligi(self) -> OzellikTanimi:
        return OzellikTanimi("skor_ham", "roc", {"pencere": int(self.parametreler["pencere"])})

    def _skor(self, baglam: Any) -> float:
        return baglam.ozellik("skor_ham")


class KesitselTers(_Kesitsel):
    """Kısa vadeli ters dönüş: trailing getirisi en düşük `azami_enstruman` üye."""

    ad = "kesitsel_ters"
    neden = "KESITSEL_TERS"

    def _skor_ozelligi(self) -> OzellikTanimi:
        return OzellikTanimi("skor_ham", "roc", {"pencere": int(self.parametreler["pencere"])})

    def _skor(self, baglam: Any) -> float:
        return -baglam.ozellik("skor_ham")


class KesitselDusukOynaklik(_Kesitsel):
    """Düşük oynaklık: `atr(pencere)/fiyat`ı en düşük `azami_enstruman` üye."""

    ad = "kesitsel_dusuk_oynaklik"
    neden = "KESITSEL_DUSUK_OYNAKLIK"

    def _skor_ozelligi(self) -> OzellikTanimi:
        return OzellikTanimi("skor_ham", "atr", {"pencere": int(self.parametreler["pencere"])})

    def _skor(self, baglam: Any) -> float:
        return -baglam.ozellik("skor_ham") / baglam.bar("close")


__all__ = ["KesitselDusukOynaklik", "KesitselGuc", "KesitselTers"]
