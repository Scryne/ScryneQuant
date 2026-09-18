"""Aynı seçim, farklı **kurma**. (Faz 16, `kurma_evren` programı, K-051/4)

Defterdeki 50 çekilişin 50'si de **seçimi** değiştirdi: tek sembolde hangi barda girileceği
(K-045), evrende hangi sembolün dışlanacağı (K-068). Bu programın çekilişleri seçime hiç
dokunmuyor — kıyasla **aynı** evreni, aynı sıralamayı ve aynı dengeleme takvimini
kullanıyorlar. Değişen tek şey `KurmaAyarlari`.

Farkın mekanizması da başka: **kurma bir tahmin yapmıyor.** Oynaklık ayarlı boyutlandırma
"hangi sembol yükselecek" demez, aynı seçimi farklı risk katkılarıyla taşır. K-068'in
bulgusu ("bu veride kesitsel tahmin gücü yok") bu yüzden bu soruyu kapatmıyor.

## Her çekilişin bir "kapalı" konumu var ve orada kıyasa döner

- `EvrenTurnoverBandi`: `turnover_bandi = 0.0` → hiçbir değişiklik bastırılmaz; kod yolu
  kıyasınkiyle **aynı**, dolayısıyla sonuç **bit düzeyinde** aynı (testle).
- `EvrenOynaklikAgirlik`: `azami_agirlik_carpani = 1.0` → tavan tam olarak eşit paya oturur,
  `1/σ` payları tümüyle kırpılır, ağırlıklar eşitlenir. Burada iddia **bit eşitliği değil,
  ağırlık eşitliği**: kod yolu gerçekten farklı (önce paylar, sonra kırpma, sonra artanın
  dağıtımı), aritmetik sırası farklı olduğu için son bitler tutmayabilir. Test ağırlıkların
  eşitliğini ve özkaynak eğrisinin 1e-9 bağıl toleransta örtüşmesini ölçüyor. Tutmayan bir
  bit eşitliği iddiası, ilk kırmızıda gevşetilecek bir iddia olurdu.

Funding ailesinde aynı disiplin `dislama_orani = 0` ile uygulanmıştı: kurma katmanındaki
sessiz bir fark bütün sonuçları karşılaştırılamaz yapar, çünkü kıyas artık aynı iskelet
olmaz.

## Izgaralarda "kapalı" konum yok

`azami_agirlik_carpani = 1.0` ve `turnover_bandi = 0.0` ızgaralara **girmiyor**: o nokta
kıyasın kendisi. Izgaraya konsaydı tarama "en iyi" olarak kıyası seçebilir ve çekiliş
kendi kıyasını geçip geçmediğini soramaz hâle gelirdi.

## ATR penceresi bir eksen değil

`ATR_PENCERESI = 14` sabit kalıyor. Kıyasın docstring'i bunun risk motorunun
`RISK_ATR_PENCERESI`siyle **aynı sayı** olmasının bilinçli olduğunu yazıyor: aynı
büyüklüğü iki farklı pencereyle ölçmek, kurma katmanı ile risk katmanının aynı pozisyon
hakkında farklı şeyler söylemesine yol açar. Bir ızgara ekseni yapmak o kararı sonuca
bakarak bozmak olurdu.
"""

from __future__ import annotations

from typing import Any, ClassVar

from scryne_quant.strategy.kurma import KurmaAyarlari
from scryne_quant.strategy.kutuphane.evren_esit_agirlik import EvrenEsitAgirlik


class _KurmaDegisimi(EvrenEsitAgirlik):
    """Ortak iskelet: kıyasın seçimi, değişen kurma ayarı.

    `_aday_uyeler` **geçersiz kılınmıyor** — bu ailenin dışlaması yok. Seçim kıyasınkiyle
    aynı kalsın diye `EvrenEsitAgirlik`in kancası olduğu gibi miras alınıyor.
    """

    ad: ClassVar[str] = ""

    def __init__(
        self,
        azami_enstruman: int = 10,
        yeniden_dengele_bar: int = 168,
        hedef_brut: float = 0.2,
        **ek: Any,
    ) -> None:
        super().__init__(
            yeniden_dengele_bar=yeniden_dengele_bar,
            azami_enstruman=azami_enstruman,
            azami_agirlik=float(hedef_brut) / int(azami_enstruman),
            hedef_brut=hedef_brut,
            esit_agirlik=True,
        )
        self.parametreler = {
            "azami_enstruman": azami_enstruman,
            "yeniden_dengele_bar": yeniden_dengele_bar,
            "hedef_brut": hedef_brut,
            **ek,
        }
        self.dogrula()
        self._dogrula_ayar()
        self._ayarlar = self._kurma_ayarlari()

    def _kurma_ayarlari(self) -> KurmaAyarlari:
        raise NotImplementedError

    def _dogrula_ayar(self) -> None:
        """Alt sınıfın kendi alanının doğrulaması.

        `dogrula`ya konulamaz: taban sınıfın `__init__`i `parametreler` daha bu sınıfın
        alanlarıyla dolmadan `dogrula`yı bir kez çağırıyor ve o çağrıda alan henüz yok.
        `dogrula` içinde `.get(..., varsayilan)` yazmak bunu gizlerdi — eksik bir alan
        sessizce varsayılana düşer ve doğrulama hiçbir şey doğrulamaz olurdu.
        """

    def dogrula(self) -> None:
        p = self.parametreler
        if int(p["yeniden_dengele_bar"]) < 1:
            raise ValueError("yeniden_dengele_bar ≥ 1 olmalı")
        if int(p["azami_enstruman"]) < 1:
            raise ValueError("azami_enstruman ≥ 1 olmalı")
        if not 0.0 < float(p["hedef_brut"]) <= 1.0:
            raise ValueError("hedef_brut (0, 1] aralığında olmalı")

    def sozluk(self) -> dict[str, Any]:
        # `EvrenEsitAgirlik.sozluk` "kiyas: True" ekliyor; bunlar kıyas değil, çekiliştir.
        d = super().sozluk()
        d["kiyas"] = False
        return d


class EvrenOynaklikAgirlik(_KurmaDegisimi):
    """Eşit ağırlık yerine `w ∝ 1/σ`; tavan, eşit payın `azami_agirlik_carpani` katı.

    Tavan **mutlak değil oransal** ifade ediliyor. `KurmaAyarlari.azami_agirlik` mutlak bir
    ağırlık; `hedef_brut = 0,2` ve 10 isimde eşit pay 0,02 olduğu için 0,15 ya da 0,30 gibi
    mutlak bir tavan hiçbir zaman bağlamaz — ızgaranın dört noktası birbirinin aynısı olur
    ve bu, olmayan bir platoyu var gösterir. Çarpan olarak ifade edilince eksen her
    yoğunlukta aynı şeyi sorar: "en büyük pozisyon eşit payın kaç katı olabilsin".
    """

    ad: ClassVar[str] = "evren_oynaklik_agirlik"

    def __init__(
        self,
        azami_agirlik_carpani: float = 2.0,
        azami_enstruman: int = 10,
        yeniden_dengele_bar: int = 168,
        hedef_brut: float = 0.2,
    ) -> None:
        super().__init__(
            azami_enstruman=azami_enstruman,
            yeniden_dengele_bar=yeniden_dengele_bar,
            hedef_brut=hedef_brut,
            azami_agirlik_carpani=azami_agirlik_carpani,
        )

    def _dogrula_ayar(self) -> None:
        if float(self.parametreler["azami_agirlik_carpani"]) < 1.0:
            # 1'in altı, tavanı eşit payın altına indirir: hiçbir pozisyon eşit payı
            # dolduramaz ve brüt maruziyet sessizce düşer. Ölçülen şey artık ağırlıklandırma
            # değil, maruziyet olurdu.
            raise ValueError("azami_agirlik_carpani ≥ 1 olmalı")

    def _kurma_ayarlari(self) -> KurmaAyarlari:
        p = self.parametreler
        esit_pay = float(p["hedef_brut"]) / int(p["azami_enstruman"])
        return KurmaAyarlari(
            yontem="EVREN_OYNAKLIK",
            azami_enstruman=int(p["azami_enstruman"]),
            azami_agirlik=min(1.0, esit_pay * float(p["azami_agirlik_carpani"])),
            hedef_brut=float(p["hedef_brut"]),
            esit_agirlik=False,
        )


class EvrenTurnoverBandi(_KurmaDegisimi):
    """Kıyasın ağırlıklandırması, üstüne turnover bandı.

    `kurma.py` bu sayının ölçülmeden bırakıldığını kendisi yazıyor: *"Varsayılan 0: Faz 10
    yöntemi kurar, sayıyı ölçmez. Bağlayıcı bir bant Faz 12'de, turnover'ın gerçek maliyeti
    ölçüldüğünde yazılır."* Faz 12 bunu yapmadı; bu çekiliş o açık kalemi kapatıyor.

    Bandın birimi **ağırlık**: eşit payın (`hedef_brut / azami_enstruman`) bir kesri. 10
    isimde eşit pay 0,02; bant 0,02 olduğunda dengeleme fiilen yalnızca giriş-çıkışlarda
    olur.
    """

    ad: ClassVar[str] = "evren_turnover_bandi"

    def __init__(
        self,
        turnover_bandi: float = 0.005,
        azami_enstruman: int = 10,
        yeniden_dengele_bar: int = 168,
        hedef_brut: float = 0.2,
    ) -> None:
        super().__init__(
            azami_enstruman=azami_enstruman,
            yeniden_dengele_bar=yeniden_dengele_bar,
            hedef_brut=hedef_brut,
            turnover_bandi=turnover_bandi,
        )

    def _dogrula_ayar(self) -> None:
        if float(self.parametreler["turnover_bandi"]) < 0.0:
            raise ValueError("turnover_bandi negatif olamaz")

    def _kurma_ayarlari(self) -> KurmaAyarlari:
        p = self.parametreler
        return KurmaAyarlari(
            yontem="EVREN_ESIT_BANT",
            azami_enstruman=int(p["azami_enstruman"]),
            azami_agirlik=float(p["hedef_brut"]) / int(p["azami_enstruman"]),
            hedef_brut=float(p["hedef_brut"]),
            esit_agirlik=True,
            turnover_bandi=float(p["turnover_bandi"]),
        )


#: Program çekilişlerinin sırası (durma kuralı ilk ikisine bakar).
KURMA_AILELERI: dict[str, type[_KurmaDegisimi]] = {
    EvrenOynaklikAgirlik.ad: EvrenOynaklikAgirlik,
    EvrenTurnoverBandi.ad: EvrenTurnoverBandi,
}

__all__ = ["EvrenOynaklikAgirlik", "EvrenTurnoverBandi", "KURMA_AILELERI"]
