"""Execution motoru: onaylı niyeti emre çeviren tek yol. (§33, Faz 7)

`execution/kapi.py` Faz 5'te kapıyı kurmuştu ve emir üretmiyordu — *"o faz hazır bir
kapının arkasına emir mantığı koyacak, kapıyı açmaya çalışmayacak."* Bu modül o mantık.

**Gönderim sırası bir karardır ve tersine çevrilemez:**

```
1. kimliği hesapla, deftere sor      → varsa DUR, tek bir ağ çağrısı bile yapma
2. miktarı sembol kurallarına uydur  → uymuyorsa kayıt + REJECTED, ağa çıkılmaz
3. emri kur ve deftere yaz           → CREATED → VALIDATED
4. SUBMITTED'ı diske yaz             → ağ çağrısından ÖNCE
5. borsaya gönder                    → sonucu sınıflandır
6. sonucu diske yaz
```

**1. adım duplicate korumasının birinci katmanı.** Aynı niyet ikinci kez geldiğinde istek
borsaya *hiç gitmiyor* — çünkü gitmek başlı başına risk: yanıt kaybolursa emrin oluşup
oluşmadığını bilemeyiz (`BelirsizSonuc`). Kontrolün en başta olması, kimliğin yalnızca
niyetin içeriğinden türemesi sayesinde mümkün: miktarı hesaplamak için fiyat sormak bile
gerekmiyor. Borsanın `-2010` reddi ikinci katman ve yedek (`oms/defter.py`'nin tablosu).

**2. adımda deftere yazılan miktar, gönderilebilir miktardır.** İstenen 0,00012981 BTC ve
lot adımı 0,00001 ise deftere 0,00012 yazılır. Ham miktarı yazmak, tamamen dolmuş bir
emrin `kalan`ını sıfırdan farklı bırakırdı — `FILLED` ama bakiyesi olan bir emir, ve
pozisyon hesabında sessizce biriken bir fark.

**4. adım yetim emir bırakmamak için.** Ters sırada — önce gönder, sonra yaz — arada ölen
bir süreç sistemin hiç bilmediği bir emir bırakırdı; onu bulmanın yolu borsayı sorgulamak
olurdu ama sistem *aramayı bile bilmezdi*. Bu sırayla en kötü durum, hiç gönderilmemiş bir
emrin kaydı; mutabakat (§25) onu borsaya sorup bulamayınca `FAILED`e kapatır. İki hatadan
**bilineni** seçiliyor (K-038'in aynı mantığı).

**5. adımın sınıflandırması bu dosyanın asıl işi** ve üç hatanın üç ayrı sonucu var:

| Adaptör hatası | Emir durumu | Sonraki adım |
| --- | --- | --- |
| `GonderilemediHatasi` | `FAILED` | Yeniden gönderilebilir |
| `BorsaReddetti` | `REJECTED` | Sebep giderilmeden gönderilmez |
| `BelirsizSonuc` | `UNKNOWN` | **Yalnızca** mutabakat; asla yeniden gönderim |
| `SaatSapmasi` | `FAILED` | Koşu durur — saat düzelmeden emir gönderilmez |

`SaatSapmasi`nın `FAILED` olması dikkat ister: `-1021` alan bir istek borsaya **ulaşmış**
ama emir **oluşmamıştır** (imza penceresi dışında olduğu için işlenmeden reddedilir). Yani
"gönderilemedi" bilgisi kesindir. Buna rağmen hata yukarı fırlatılıyor: bozuk saatle
devam eden bir koşu, emirlerini sessizce kaybeder.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scryne_quant.exchange.emir_adaptoru import BorsaEmri, EmirAdaptoru
from scryne_quant.exchange.hatalar import (
    BelirsizSonuc,
    BorsaReddetti,
    GonderilemediHatasi,
    SaatSapmasi,
)
from scryne_quant.exchange.kurallar import KuralIhlali, emri_dogrula
from scryne_quant.oms.defter import EmirDefteri
from scryne_quant.oms.emir import Emir, EmirDurumu, emir_kur, istemci_kimligi
from scryne_quant.risk.niyet import OnayliNiyet, dogrula


class ExecutionHatasi(RuntimeError):
    """Execution katmanı bir niyeti emre çeviremedi."""


class SaatEngeli(ExecutionHatasi):
    """Saat sapması yüzünden emir gönderilemiyor. Koşu durmalı."""


@dataclass(frozen=True, slots=True)
class GonderimSonucu:
    """Bir gönderim denemesinin sonucu.

    `gonderildi` yanlışsa emir **zaten vardı** ve ağa çıkılmadı — duplicate korumasının
    gözlemlenebilir hâli. `emir` her iki durumda da defterdeki güncel kayıt.
    """

    emir: Emir
    gonderildi: bool
    borsa_yaniti: BorsaEmri | None = None

    @property
    def belirsiz(self) -> bool:
        """Sonuç bilinmiyor mu? Doğruysa mutabakat çalışmadan devam edilmemeli."""
        return self.emir.durum is EmirDurumu.UNKNOWN

    def sozluk(self) -> dict[str, Any]:
        return {
            "emir": self.emir.sozluk(),
            "gonderildi": self.gonderildi,
            "belirsiz": self.belirsiz,
            "borsa_yaniti": self.borsa_yaniti.sozluk() if self.borsa_yaniti else None,
        }


class EmirMotoru:
    """Onaylı niyeti borsaya ileten motor. Defter ve adaptör dışarıdan verilir.

    Bağımlılıkların enjekte edilmesi test için değil **yetki** için: motoru kuran yer,
    hangi deftere yazacağını ve hangi borsaya bağlanacağını açıkça seçmek zorunda. Modül
    içinde bir varsayılan adaptör olsaydı, yanlış ortama emir göndermek bir unutmaya
    bakardı.
    """

    __slots__ = ("_adaptor", "_defter")

    def __init__(self, defter: EmirDefteri, adaptor: EmirAdaptoru) -> None:
        self._defter = defter
        self._adaptor = adaptor

    def gonder(self, niyet: OnayliNiyet, miktar: float) -> GonderimSonucu:
        """Onaylı niyeti emre çevirip gönderir. Modül docstring'indeki altı adım.

        Mühür **burada tekrar** doğrulanıyor (`emir_kur` da doğruluyor): onay anı ile
        gönderim anı arasında kod çalışıyor ve o kodun niyete dokunmadığını varsaymak,
        bir güvenlik sınırını varsayıma dayandırmak olurdu (`execution/kapi.py` ile aynı
        gerekçe).
        """
        onayli = dogrula(niyet)
        kimlik = istemci_kimligi(onayli)

        # Duplicate kontrolü **her şeyden önce** ve kimlik üzerinden: kimlik yalnızca
        # niyetin içeriğinden türüyor, yani miktarı hesaplamaya bile gerek yok. Böylece
        # tekrarlanan bir niyet tek bir ağ çağrısına — fiyat sorgusuna bile — mal olmuyor.
        mevcut = self._defter.al(kimlik)
        if mevcut is not None:
            return GonderimSonucu(mevcut, gonderildi=False)

        zaman_ms = self._adaptor.sunucu_zamani_ms()
        try:
            uydurulmus, ihlal = self._uydur(onayli.sinyal.symbol, miktar), None
        except KuralIhlali as hata:
            uydurulmus, ihlal = miktar, hata

        # Deftere **gönderilebilir** miktar yazılıyor, istenen değil. Aradaki fark lot
        # adımına yuvarlamadan geliyor ve küçük görünüyor — ama ham miktarı yazmak,
        # `FILLED` bir emrin `kalan`ını sıfırdan farklı bırakır: tamamen dolmuş bir emrin
        # defterde hâlâ bir bakiyesi olur. Kural ihlalinde istenen miktar yazılıyor,
        # çünkü orada kayda geçmesi gereken şey denenen şeydir.
        emir = emir_kur(onayli, uydurulmus, zaman_ms=zaman_ms)
        kayitli, yeni = self._defter.yer_ac(emir)
        if not yeni:
            return GonderimSonucu(kayitli, gonderildi=False)

        if ihlal is not None:
            return GonderimSonucu(
                self._defter.gecir(
                    emir.istemci_kimligi,
                    EmirDurumu.REJECTED,
                    zaman_ms=zaman_ms,
                    hata=str(ihlal),
                ),
                gonderildi=False,
            )

        emir = self._defter.gecir(
            emir.istemci_kimligi, EmirDurumu.VALIDATED, zaman_ms=zaman_ms
        )
        # 4. adım: ağ çağrısından ÖNCE diske.
        emir = self._defter.gecir(
            emir.istemci_kimligi, EmirDurumu.SUBMITTED, zaman_ms=zaman_ms
        )

        return self._borsaya_ilet(emir, uydurulmus)

    # ------------------------------------------------------------------ iç

    def _uydur(self, sembol: str, miktar: float) -> float:
        """Miktarı sembolün kurallarına uydurur; sağlanamıyorsa `KuralIhlali`."""
        kurallar = self._adaptor.sembol_kurallari(sembol)
        fiyat = self._adaptor.son_fiyat(sembol)
        return emri_dogrula(kurallar, miktar, referans_fiyat=fiyat)

    def _borsaya_ilet(self, emir: Emir, miktar: float) -> GonderimSonucu:
        kimlik = emir.istemci_kimligi
        try:
            yanit = self._adaptor.market_emri(
                istemci_kimligi=kimlik,
                sembol=emir.sembol,
                yon=emir.yon,
                miktar=miktar,
            )
        except BelirsizSonuc as hata:
            # Tek çıkışı mutabakat olan durum. Yeniden gönderim yok — state machine'de
            # `UNKNOWN → SUBMITTED` geçişi zaten tanımlı değil.
            return GonderimSonucu(
                self._sonuclandir(kimlik, EmirDurumu.UNKNOWN, hata),
                gonderildi=True,
            )
        except SaatSapmasi as hata:
            self._sonuclandir(kimlik, EmirDurumu.FAILED, hata)
            raise SaatEngeli(
                f"saat sapması yüzünden emir gönderilemedi ({kimlik}): {hata}. "
                f"Koşu durmalı; saat düzelmeden gönderilen her emir sessizce reddedilir."
            ) from hata
        except BorsaReddetti as hata:
            return GonderimSonucu(
                self._sonuclandir(kimlik, EmirDurumu.REJECTED, hata),
                gonderildi=True,
            )
        except GonderilemediHatasi as hata:
            return GonderimSonucu(
                self._sonuclandir(kimlik, EmirDurumu.FAILED, hata),
                gonderildi=False,
            )

        return GonderimSonucu(
            self._yaniti_isle(emir, yanit), gonderildi=True, borsa_yaniti=yanit
        )

    def _sonuclandir(self, kimlik: str, durum: EmirDurumu, hata: Exception) -> Emir:
        return self._defter.gecir(
            kimlik,
            durum,
            zaman_ms=self._zaman_ms(),
            hata=f"{type(hata).__name__}: {hata}",
        )

    def _yaniti_isle(self, emir: Emir, yanit: BorsaEmri) -> Emir:
        """Borsanın döndüğü durumu deftere yazar.

        Market emri çoğu zaman tek yanıtta `FILLED` döner, yani `SUBMITTED → FILLED`
        geçişi gerekir — ama state machine bunu **yasaklıyor** (`SUBMITTED`ın izinli
        kümesinde `FILLED` yok) ve bu doğru: borsanın emri kabul ettiği an ile doldurduğu
        an ayrı olaylardır, ikisini tek geçişte ezmek `gecmis` sütunundan `ACKNOWLEDGED`ı
        silerdi. O yüzden önce kabul, sonra dolum yazılıyor — emrin yolu kayıtta kalıyor.
        """
        zaman_ms = yanit.guncellendi_ms or self._zaman_ms()

        # Reddedilen bir emir hiç kabul edilmemiştir: `SUBMITTED → REJECTED` doğrudan
        # geçilir. Önce `ACKNOWLEDGED` yazmak, olmamış bir kabulü kayda geçirmek olurdu —
        # ve state machine zaten `ACKNOWLEDGED → REJECTED` geçişini tanımıyor.
        if yanit.durum is EmirDurumu.REJECTED:
            return self._defter.gecir(
                emir.istemci_kimligi,
                EmirDurumu.REJECTED,
                zaman_ms=zaman_ms,
                borsa_kimligi=yanit.borsa_kimligi,
                hata=f"borsa reddetti: {yanit.ham_durum}",
            )

        guncel = self._defter.gecir(
            emir.istemci_kimligi,
            EmirDurumu.ACKNOWLEDGED,
            zaman_ms=zaman_ms,
            borsa_kimligi=yanit.borsa_kimligi,
        )
        if yanit.durum is EmirDurumu.ACKNOWLEDGED:
            return guncel
        return self._defter.gecir(
            emir.istemci_kimligi,
            yanit.durum,
            zaman_ms=zaman_ms,
            borsa_kimligi=yanit.borsa_kimligi,
            dolan_miktar=yanit.dolan_miktar,
            ortalama_fiyat=yanit.ortalama_fiyat,
        )

    def _zaman_ms(self) -> int:
        """Sonuç yazarken saat sorulamıyorsa yazım yine de yapılmalı.

        Bir ağ hatasını kaydetmeye çalışırken ikinci bir ağ çağrısına (saat senkronu)
        bağımlı olmak, en çok gerektiği anda kaydı kaybetmek demek. Son çare olarak
        emrin kendi zaman damgası değil, sıfır yazılıyor — `gecir` zamanı kayda geçirir
        ve `gecmis` yine dolar.
        """
        try:
            return self._adaptor.sunucu_zamani_ms()
        except Exception:  # noqa: BLE001 — kayıt her koşulda yazılmalı
            return 0


__all__ = ["EmirMotoru", "ExecutionHatasi", "GonderimSonucu", "SaatEngeli"]
