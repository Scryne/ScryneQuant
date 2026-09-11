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

## İptal: aynı ilkenin ters yöne uygulanması (K-047)

Gönderimde kayıt ağ çağrısından **önce** yazılıyor; iptalde **sonra**. Ters gibi görünen
bu ikisi tek bir ilkenin iki yüzü: **maruziyetin var olduğunu varsay.**

| | Kayıt ne zaman | Belirsizlikte varsayılan |
| --- | --- | --- |
| Gönderim | Ağ çağrısından **önce** (`SUBMITTED`) | Emir **olmuş olabilir** |
| İptal | Yanıt doğrulandıktan **sonra** (`CANCELED`) | Emir **hâlâ duruyor olabilir** |

İkisi de aynı yöne yanılıyor ve o yön güvenli olan. Tersi — doğrulanmamış bir iptali
`CANCELED` yazmak — duran bir maruziyeti kapanmış gösterir; sistem "pozisyonum yok" sanıp
yeni emir gönderir ve maruziyet ikiye katlanır. Yanlış tarafa yanılmanın bedeli, bu
projede geri alınamaz olan taraftadır.

**İptalin "emir yok" cevabı bir başarısızlık değil.** Borsa `-2011` döndürdüğünde iptal
edilecek bir şey yoktur: emir bu arada dolmuş, süresi geçmiş ya da zaten iptal edilmiştir.
Yapılacak şey tekrar iptal denemek değil, **sorgulamak** — `UNKNOWN`dan çıkışın tek
yolunun sorgulama olmasıyla aynı disiplin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scryne_quant.exchange.emir_adaptoru import BorsaEmri, EmirAdaptoru, borsa_yonu
from scryne_quant.exchange.hatalar import (
    BelirsizSonuc,
    BorsaReddetti,
    GonderilemediHatasi,
    SaatSapmasi,
)
from scryne_quant.exchange.kurallar import KuralIhlali, emri_dogrula, fiyat_uydur
from scryne_quant.oms.defter import EmirDefteri
from scryne_quant.oms.emir import ACIK, Emir, EmirDurumu, emir_kur, istemci_kimligi
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


@dataclass(frozen=True, slots=True)
class IptalSonucu:
    """Bir iptal denemesinin sonucu.

    Üç ayrı "başarısız" var ve üçü farklı şeyler söylüyor — tek bir `basarili` bayrağı
    onları birbirine karıştırırdı:

    | Alan | Anlamı | Sonraki adım |
    | --- | --- | --- |
    | `iptal_edildi` | Borsa iptali onayladı | Yok |
    | `belirsiz` | Yanıt kayboldu, emir duruyor **olabilir** | **Mutabakat**, tekrar iptal değil |
    | `borsa_tanimiyor` | İptal edilecek emir yok (dolmuş/kapanmış) | Sorgula, durumu yaz |
    | hiçbiri | Emir zaten nihai durumdaydı, ağa çıkılmadı | Yok |
    """

    emir: Emir
    iptal_edildi: bool = False
    belirsiz: bool = False
    borsa_tanimiyor: bool = False
    gonderildi: bool = False
    """İstek ağa **çıktı mı**. Çıkmadıysa iptal güvenle tekrar denenebilir."""

    def sozluk(self) -> dict[str, Any]:
        return {
            "emir": self.emir.sozluk(),
            "iptal_edildi": self.iptal_edildi,
            "belirsiz": self.belirsiz,
            "borsa_tanimiyor": self.borsa_tanimiyor,
            "gonderildi": self.gonderildi,
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

    def gonder(
        self,
        niyet: OnayliNiyet,
        miktar: float,
        *,
        limit_fiyati: float | None = None,
    ) -> GonderimSonucu:
        """Onaylı niyeti emre çevirip gönderir. Modül docstring'indeki altı adım.

        `limit_fiyati` verilirse emir `LIMIT` olur, verilmezse `MARKET`. Aynı metot
        çünkü altı adımın tamamı ikisinde de aynı ve **duplicate koruması ortak**: fiyat
        kimliğe girmiyor, yani aynı niyeti bir kez market bir kez limit olarak göndermek
        ikinci bir emir üretmiyor. Ayrı bir `limit_gonder` metodu, o ortaklığı bir
        dikkate bırakırdı.

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
        sembol = onayli.sinyal.symbol
        try:
            uydurulmus, ihlal = self._uydur(sembol, miktar), None
        except KuralIhlali as hata:
            uydurulmus, ihlal = miktar, hata

        tur = "MARKET" if limit_fiyati is None else "LIMIT"
        limit = 0.0
        if limit_fiyati is not None and ihlal is None:
            # Fiyat **deftere yazılmadan önce** tick'e uyduruluyor: borsaya giden fiyat
            # ile defterdeki fiyat aynı olmalı, yoksa "hangi fiyattan emir verdim"
            # sorusunun iki farklı cevabı olur.
            try:
                limit = fiyat_uydur(
                    limit_fiyati,
                    self._adaptor.sembol_kurallari(sembol).tick_size,
                    yon=borsa_yonu(str(onayli.sinyal.side)),
                )
            except KuralIhlali as hata:
                ihlal, limit = hata, 0.0
                tur = "MARKET"

        # Deftere **gönderilebilir** miktar yazılıyor, istenen değil. Aradaki fark lot
        # adımına yuvarlamadan geliyor ve küçük görünüyor — ama ham miktarı yazmak,
        # `FILLED` bir emrin `kalan`ını sıfırdan farklı bırakır: tamamen dolmuş bir emrin
        # defterde hâlâ bir bakiyesi olur. Kural ihlalinde istenen miktar yazılıyor,
        # çünkü orada kayda geçmesi gereken şey denenen şeydir.
        emir = emir_kur(
            onayli, uydurulmus, zaman_ms=zaman_ms, tur=tur, limit_fiyati=limit
        )
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

    def iptal(self, istemci_kimligi_: str) -> IptalSonucu:
        """Açık bir emri iptal eder. Modül docstring'indeki "İptal" bölümü.

        Emir zaten nihai durumdaysa **ağa çıkılmıyor**: iptal edilecek bir şey yok ve
        gereksiz bir yazma isteği, yanıtı kaybolduğunda çözülecek yeni bir belirsizlik
        üretmekten başka işe yaramaz.
        """
        emir = self._defter.al(istemci_kimligi_)
        if emir is None:
            raise ExecutionHatasi(
                f"iptal edilecek emir defterde yok: {istemci_kimligi_}. Defterin "
                f"bilmediği bir emri iptal etmek, kaydı olmayan bir maruziyete "
                f"dokunmaktır; önce mutabakat çalışmalı."
            )
        if emir.durum not in ACIK:
            return IptalSonucu(emir)

        try:
            yanit = self._adaptor.emir_iptal(
                sembol=emir.sembol, istemci_kimligi=istemci_kimligi_
            )
        except BelirsizSonuc as hata:
            # **Defter değişmiyor.** Emir duruyor olabilir; `CANCELED` yazmak duran bir
            # maruziyeti kapanmış göstermek olurdu. Çıkış yolu mutabakat.
            return IptalSonucu(
                self._not_dus(emir, f"iptal belirsiz: {hata}"),
                belirsiz=True,
                gonderildi=True,
            )
        except GonderilemediHatasi as hata:
            # İstek hiç çıkmadı: emir de defter de olduğu gibi. Güvenle tekrar denenir.
            return IptalSonucu(self._not_dus(emir, f"iptal gönderilemedi: {hata}"))
        except BorsaReddetti as hata:
            return IptalSonucu(self._not_dus(emir, f"iptal reddedildi: {hata}"))

        if yanit is None:
            # "İptal edilecek emir yok" — bir başarısızlık değil, emrin bu arada
            # kapandığının haberi. Doğru tepki **sorgulamak**; tahmin yürütülmüyor.
            return IptalSonucu(
                self._sorgulayip_yaz(emir), borsa_tanimiyor=True, gonderildi=True
            )

        guncel = self._iptal_yanitini_isle(emir, yanit)
        return IptalSonucu(
            guncel,
            iptal_edildi=guncel.durum is EmirDurumu.CANCELED,
            gonderildi=True,
        )

    # ------------------------------------------------------------------ iç

    def _uydur(self, sembol: str, miktar: float) -> float:
        """Miktarı sembolün kurallarına uydurur; sağlanamıyorsa `KuralIhlali`."""
        kurallar = self._adaptor.sembol_kurallari(sembol)
        fiyat = self._adaptor.son_fiyat(sembol)
        return emri_dogrula(kurallar, miktar, referans_fiyat=fiyat)

    def _borsaya_ilet(self, emir: Emir, miktar: float) -> GonderimSonucu:
        kimlik = emir.istemci_kimligi
        try:
            if emir.tur == "LIMIT":
                yanit = self._adaptor.limit_emri(
                    istemci_kimligi=kimlik,
                    sembol=emir.sembol,
                    yon=emir.yon,
                    miktar=miktar,
                    fiyat=emir.limit_fiyati,
                )
            else:
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
        # Komisyon **yalnızca burada**, `POST` yanıtının `fills` dizisinden okunabiliyor;
        # `GET /api/v3/order` onu taşımıyor. Bu satırı atlamak, komisyonu sonradan
        # `/api/v3/myTrades` ile toplamak zorunda bırakırdı — her emir için fazladan bir
        # imzalı çağrı, ve hiç yapılmazsa pozisyon mutabakatında her alımda ~%0,1'lik
        # açıklanamayan bir fark.
        return self._defter.gecir(
            emir.istemci_kimligi,
            yanit.durum,
            zaman_ms=zaman_ms,
            borsa_kimligi=yanit.borsa_kimligi,
            dolan_miktar=yanit.dolan_miktar,
            ortalama_fiyat=yanit.ortalama_fiyat,
            komisyon=yanit.komisyon,
            komisyon_kaynagi=yanit.komisyon_kaynagi or None,
        )

    def _not_dus(self, emir: Emir, mesaj: str) -> Emir:
        """Durumu değiştirmeden bir not bırakmak istiyoruz — ama defter buna izin vermez.

        `Emir` değişmez ve her not bir durum geçişi gerektirir; geçişsiz bir güncelleme
        için `gecir` çağrılamaz. O yüzden **hiçbir şey yazılmıyor** ve not yalnızca
        dönen nesnede taşınıyor: belirsiz bir iptalin defterde bıraktığı tek doğru iz,
        emrin hâlâ açık durmasıdır. Not için durum değiştirmek, bilgiyi kaydetmek uğruna
        muhasebeyi bozmak olurdu.
        """
        from dataclasses import replace as _replace

        return _replace(emir, hata=mesaj)

    def _iptal_yanitini_isle(self, emir: Emir, yanit: BorsaEmri) -> Emir:
        """İptal yanıtını deftere yazar. `_yaniti_isle`den **ayrı** ve olmak zorunda.

        `_yaniti_isle` gönderim yanıtı için yazıldı ve önce `ACKNOWLEDGED` geçiyor —
        emrin kabul edildiği an ile dolduğu anı ayrı olaylar olarak kaydetmek için. İptal
        yanıtında o adım hem gereksiz hem **yasak**: emir zaten `ACKNOWLEDGED` ve state
        machine `ACKNOWLEDGED → ACKNOWLEDGED` geçişini tanımıyor (tanımaması doğru, yoksa
        bir emir sonsuza kadar aynı durumda "ilerleyebilirdi").

        Borsanın durumu zaten bizimkiyse hiçbir şey yazılmıyor: iptal istendi ama emir
        `PENDING_CANCEL` olarak geri geldi (bizde `ACKNOWLEDGED`e eşleniyor) demektir.
        İptal **istendi ama tamamlanmadı**, ve emir hâlâ dolabilir.
        """
        if yanit.durum is emir.durum:
            return emir
        return self._defter.gecir(
            emir.istemci_kimligi,
            yanit.durum,
            zaman_ms=yanit.guncellendi_ms or self._zaman_ms(),
            borsa_kimligi=yanit.borsa_kimligi,
            dolan_miktar=yanit.dolan_miktar,
            ortalama_fiyat=yanit.ortalama_fiyat,
            komisyon=yanit.komisyon,
            komisyon_kaynagi=yanit.komisyon_kaynagi or None,
        )

    def _sorgulayip_yaz(self, emir: Emir) -> Emir:
        """Emri borsaya sorup gerçek durumunu deftere yazar.

        `mutabakat`ın tek emirlik hâli. Burada tekrarlanıyor çünkü iptal yolunda cevap
        **hemen** gerekiyor: çağıran "maruziyetim kapandı mı" sorusunu bir sonraki
        mutabakat turuna kadar bekleyemez.
        """
        borsada = self._adaptor.emir_sorgula(
            sembol=emir.sembol, istemci_kimligi=emir.istemci_kimligi
        )
        if borsada is None:
            return emir
        if borsada.durum is emir.durum:
            return emir
        return self._defter.gecir(
            emir.istemci_kimligi,
            borsada.durum,
            zaman_ms=borsada.guncellendi_ms or self._zaman_ms(),
            borsa_kimligi=borsada.borsa_kimligi,
            dolan_miktar=borsada.dolan_miktar,
            ortalama_fiyat=borsada.ortalama_fiyat,
            hata="iptal: borsa emri tanımadı, gerçek durum sorgulanıp yazıldı",
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


__all__ = [
    "EmirMotoru",
    "ExecutionHatasi",
    "GonderimSonucu",
    "IptalSonucu",
    "SaatEngeli",
]
