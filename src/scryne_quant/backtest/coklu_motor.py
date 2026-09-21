"""Çok enstrümanlı event loop. Tek enstrüman bunun **özel hâlidir**. (Faz 10, K-052/2)

Barın iç sırası Faz 3'ün sırasıyla birebir aynı ve aynı gerekçelerle sabit:

1. **Fill** — bir önceki barda onaylanmış hedefler bu barın **açılışından** dolar (K-004).
   Çok enstrümanlıda tek fark, birden fazla emrin aynı barda olması: **önce satışlar,
   sonra alımlar** (`fill.emirleri_hazirla`), çünkü aynı barda hem çıkılıp hem girilen bir
   yeniden dengelemede alım, satıştan gelen nakdi kullanabilmeli.
2. **Risk durumu** — özkaynak bu barın kapanışlarıyla işaretlenir; karardan **önce**.
3. **Karar** — strateji evren `ctx`ini görür, hedef portföy üretir, hedef risk motorundan
   geçer. Onaylanan hedefler bekleyene alınır; hiçbiri bu barda dolmaz.
4. **Değerleme** — özkaynak ve brüt maruziyet bu barın kapanışlarıyla işaretlenir.

## Tek enstrüman neden bit düzeyinde aynı çıkıyor

Tek sembollü bir koşuda: `CokluPortfoy.ozkaynak` tek bir `nakit + miktar×fiyat` toplamına
iner; `emirleri_hazirla` tek bir emir üretir ve boyutlandırmayı `emir_hazirla` ile **aynı**
fonksiyondan (`emir_hazirla_genel`) alır; portföy düzeyi tavanları varsayılan değerlerinde
bağlamaz; `uygula_coklu` tur muhasebesini `uygula` ile aynı sırada yapar. Yani aynı sayılar
aynı sırada toplanıyor — "yakın" değil, **aynı**. `tests/unit/test_coklu_motor.py` bunu
Faz 3'ün bağımsız referans fixture'ı üzerinde kontrol ediyor.

## Barı olmayan enstrüman

Bir sembolün `t`de barı yoksa (henüz listelenmemiş ya da delist edilmiş) o sembolde ne
karar verilir ne fill yapılır — `ok` olmayan bar kuralının (K-028) doğal uzantısı. Açık bir
pozisyon bu sebeple kapatılamıyorsa **son bilinen fiyattan** değerlenmeye devam eder ve
`bayat_degerleme` sayacı artar. Sıfıra yazmak olmayan bir zararı, portföyden atmak olmayan
bir kârı gerçekleştirmek olurdu; ikisi de bir tahmin, ve bu projede tahmin yasak. Sayacın
kendisi Faz 12'nin ölçeceği şey: evren kuralı bu durumu ne sıklıkta üretiyor.

## Sıfıra yazma politikası (K-059, Faz 12)

Faz 12 ölçtü: `kesitsel_fiyat`'ın OOS'unda 9 pozisyon barı biten sembolde koşu sonuna kadar
(693-18.837 bar) son fiyattan kaldı; biri (BNX) son fiyatı girişin 1,7 katıydı. "Son
fiyat" delistte iyimser, token göçünde (MATIC→POL) kötümser — yön bilinmiyor. `sifira_yaz_bar`
verilirse art arda o kadar bar barı gelmeyen pozisyon **sıfır** değerlenir; bar geri
gelirse piyasa fiyatına döner. Karar `t`ye kadarki barlardan verilir (look-ahead yok) ve
yalnızca kötü yöne işler (K-007). Varsayılan `None` = eski davranış, eski `sonuc_hash`ler
değişmez; politika açıkken `evren` kaydına yazılır.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np

from scryne_quant.backtest.defter import uygula_coklu
from scryne_quant.backtest.fill import AtlamaSebebi, emirleri_hazirla
from scryne_quant.backtest.metrikler import Islem, gunluk_hacim, hesapla
from scryne_quant.backtest.sonuc import VARSAYILAN_KALITE_ESIGI, Sonuc, VeriKimligi, atlama_sayimi
from scryne_quant.common.hash import nesne_hash
from scryne_quant.common.maliyet import (
    Maliyetler,
    MaliyetModeli,
    SembolMaliyeti,
    gecici_mi,
    maliyetler_govdesi,
)
from scryne_quant.common.zaman import timeframe_ms
from scryne_quant.data.semalar import KaliteDurumu
from scryne_quant.data.takvim import TAKVIM_24X7, Takvim
from scryne_quant.features.indikator import atr as atr_hesapla
from scryne_quant.portfolio.durum import CokluPortfoy
from scryne_quant.risk.motor import RISK_ATR_PENCERESI, PiyasaOlcumu, RiskMotoru
from scryne_quant.risk.niyet import OnayliNiyet
from scryne_quant.strategy.evren import LISTELENMEDI, EvrenGorunumu
from scryne_quant.strategy.hedef import HedefPortfoy
from scryne_quant.strategy.sinyal import Sinyal
from scryne_quant.strategy.temel import PortfoyStratejisi


class CokluBacktestHatasi(ValueError):
    """Çok enstrümanlı backtest kurulumu geçersiz."""


class CokluBacktest:
    """Evren üzerinde koşan, hedef portföy tüketen deterministik backtest motoru."""

    def __init__(
        self,
        strateji: PortfoyStratejisi,
        maliyet: MaliyetModeli,
        *,
        baslangic_sermaye: float = 10_000.0,
        seed: int = 0,
        kalite_esigi: float = VARSAYILAN_KALITE_ESIGI,
        risk: RiskMotoru | None = None,
        sifira_yaz_bar: int | None = None,
        maliyetler: Maliyetler | None = None,
        takvim: Takvim | None = None,
    ) -> None:
        if baslangic_sermaye <= 0.0:
            raise CokluBacktestHatasi(
                f"başlangıç sermayesi pozitif olmalı: {baslangic_sermaye}"
            )
        self.strateji = strateji
        self.maliyet = maliyet
        self.maliyetler: dict[str, SembolMaliyeti] | None = (
            None if maliyetler is None else dict(maliyetler)
        )
        """Sembol → `SembolMaliyeti` (K-084/U14). `None` = tek model, bugünkü yol bit-aynı.
        Verilmişse fill'ler sembolün modelini kullanır; kayda `maliyetler` bloğu **yalnız o
        zaman** girer. `maliyet` (tek model) her durumda kayıtta kalır — eski biçim korunur."""
        self.fill_maliyetleri: dict[str, MaliyetModeli] | None = (
            None if maliyetler is None else {s: em.model for s, em in maliyetler.items()}
        )
        self.takvim = takvim
        """Yıllıklandırma takvimi (R4 Paket 1). `None` = 24x7, `hesapla` bit-aynı ve kayda girmez.
        Seanslı takvim kayda `{"takvim": {id, icerik_hash}}` ile girer (`takvim_kaydi`, K-094;
        K-083/U16: yalnız 24x7 değilse)."""
        self.baslangic_sermaye = baslangic_sermaye
        self.seed = seed
        self.kalite_esigi = kalite_esigi
        self.risk = risk
        if sifira_yaz_bar is not None and sifira_yaz_bar < 1:
            raise CokluBacktestHatasi(f"sifira_yaz_bar ≥ 1 olmalı: {sifira_yaz_bar}")
        self.sifira_yaz_bar = sifira_yaz_bar

    # ------------------------------------------------------------------ koşu

    def calistir(
        self,
        gorunum: EvrenGorunumu,
        *,
        veri_sha256: Mapping[str, str] | None = None,
        olcum_baslangici: int = 0,
        tekil_sembol: str | None = None,
    ) -> Sonuc:
        """Evreni bar bar dolaşır ve tam sonuç kaydını döndürür.

        `tekil_sembol` verilirse sonuç **tek sembollü biçimde** kurulur: `veri` o sembolü
        anlatır, `evren` alanı `None` kalır ve işlem satırlarına sembol yazılmaz. Bu bir
        kozmetik ayar değil, K-009'un gereği: aynı koşunun kaydı Faz 1-7'de olduğu gibi
        kalmazsa `runs/` altındaki her eski sonuç yeniden üretilemez hâle gelir.
        """
        n = len(gorunum)
        if n < 2:
            raise CokluBacktestHatasi(f"backtest için en az 2 bar gerekir, verilen: {n}")
        if not 0 <= olcum_baslangici < n - 1:
            raise CokluBacktestHatasi(
                f"ölçüm başlangıcı 0..{n - 2} aralığında olmalı, verilen: {olcum_baslangici}"
            )
        semboller = gorunum.semboller
        if tekil_sembol is not None and tekil_sembol not in semboller:
            raise CokluBacktestHatasi(f"{tekil_sembol}: evren görünümünde yok")
        if self.fill_maliyetleri is not None:
            eksik = sorted(set(semboller) - set(self.fill_maliyetleri))
            if eksik:
                raise CokluBacktestHatasi(
                    f"enstrüman-başı maliyet modeli olmayan sembol(ler): {eksik} (K-084/U14)"
                )

        adim = timeframe_ms(gorunum.timeframe)
        girdi = self.girdi_kur(gorunum)
        adimci = CokluAdimci(self)
        ozkaynak = np.empty(n, dtype=np.float64)
        brut = np.empty(n, dtype=np.float64)
        for i in range(n):
            ozkaynak[i], brut[i] = adimci.adim(
                girdi, i, isinma=i < olcum_baslangici, son_bar=i == n - 1
            )

        return self._sonuc(
            gorunum=gorunum,
            adim=adim,
            zamanlar=girdi.zamanlar,
            kalite=girdi.kalite,
            ozkaynak=ozkaynak,
            brut=brut,
            islemler=adimci.islemler,
            atlanan=adimci.atlanan,
            uretilen=adimci.uretilen,
            bayat_degerleme=adimci.bayat_degerleme,
            sifira_yazilan=adimci.sifira_yazilan,
            kapasite_oranlari=adimci.kapasite_oranlari,
            portfoy=adimci.portfoy,
            olcum_baslangici=olcum_baslangici,
            veri_sha256=dict(veri_sha256 or {}),
            tekil_sembol=tekil_sembol,
            spread_bileseni=bool(girdi.kotasyon),
        )

    def takvim_kaydi(self) -> dict[str, str] | None:
        """Kayda giren takvim bloğu: seanslıysa `{"id", "icerik_hash"}`, 24x7/`None` ise `None`.

        Deterministik: `icerik_hash` katalog içeriğinin `nesne_hash`i (K-083/U15); aynı takvim
        aynı blok. 24x7 kayda girmez ki kripto kayıtlarının `config_hash`i değişmesin (K-094).
        """
        if self.takvim is None or self.takvim.kimlik == TAKVIM_24X7:
            return None
        return {"id": self.takvim.kimlik, "icerik_hash": self.takvim.icerik_hash}

    def girdi_kur(self, gorunum: EvrenGorunumu) -> AdimGirdisi:
        """Bir görünümün adım girdisi: bar dizilerine kısayollar + önceden hesaplananlar.

        Backtest bunu koşu başına bir kez kurar; canlı motor her yeni pencerede yeniden.

        Kotasyon (K-094): barlarında **hem** `bid_open` **hem** `ask_open` olan semboller
        `(bid, ask)` çiftiyle dolar; yalnız biri olan sembol hata — tek fiyata sessizce düşmek
        spread'i sıfır saymak olurdu. İkisi de yoksa tek fiyat (kripto), bugünkü yol.
        """
        semboller = gorunum.semboller
        adim = timeframe_ms(gorunum.timeframe)
        kotasyon: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for s in semboller:
            barlar = gorunum.gorunumler[s].barlar
            var = ("bid_open" in barlar, "ask_open" in barlar)
            if all(var):
                kotasyon[s] = (barlar["bid_open"], barlar["ask_open"])
            elif any(var):
                raise CokluBacktestHatasi(
                    f"{s}: bid_open/ask_open'dan yalnız biri var; kotasyon ikisini ister (K-094)"
                )
        return AdimGirdisi(
            gorunum=gorunum,
            zamanlar=np.asarray(gorunum.zamanlar, dtype="int64"),
            acilis={s: gorunum.gorunumler[s].barlar["open"] for s in semboller},
            kapanis={s: gorunum.gorunumler[s].barlar["close"] for s in semboller},
            kalite={s: gorunum.gorunumler[s].barlar["quality_status"] for s in semboller},
            risk_atr=self._risk_atr(gorunum) if self.risk is not None else {},
            # Kapasite ölçüsü (§16): fill notional'ının o enstrümanın ortalama günlük
            # hacmine oranı. Raporlanır, kapı değildir (K-054).
            adv={
                s: gunluk_hacim(gorunum.gorunumler[s].barlar["quote_volume"], adim)
                for s in semboller
            },
            kotasyon=kotasyon,
        )

    # ------------------------------------------------------------------ yardımcılar

    def _risk_atr(self, gorunum: EvrenGorunumu) -> dict[str, np.ndarray]:
        """Risk motorunun volatilite ölçüsü, enstrüman başına.

        Stratejinin bildirdiği özelliklerden bağımsız hesaplanıyor: strateji ATR bildirmese
        de guard çalışmak zorunda (Faz 3'ün kararı, evrene genişletilmiş hâli).
        """
        return {
            s: atr_hesapla(
                g.barlar["high"], g.barlar["low"], g.barlar["close"], RISK_ATR_PENCERESI
            )
            for s, g in gorunum.gorunumler.items()
        }

    @staticmethod
    def _fiyatlar(
        semboller: tuple[str, ...] | Mapping[str, object],
        kaynak: dict[str, float],
        i: int,
        silinen: frozenset[str] = frozenset(),
    ) -> dict[str, float]:
        """İstenen sembollerin fiyatları; barı olmayan için **son bilinen** fiyat.

        Hiç barı görülmemiş bir sembol için fiyat yok — ve olmaması gerekir: o sembolde
        pozisyon açılmış olamaz. İstenirse hata, çünkü sessizce sıfır koymak bir pozisyonu
        değersiz göstermek olurdu.
        """
        eksik = [s for s in semboller if s not in kaynak]
        if eksik:
            raise CokluBacktestHatasi(
                f"bar {i}: fiyatı hiç görülmemiş sembol(ler): {', '.join(sorted(eksik))}"
            )
        return {s: 0.0 if s in silinen else kaynak[s] for s in sorted(semboller)}

    def _risk_onayi(
        self,
        hedef: HedefPortfoy,
        portfoy: CokluPortfoy,
        fiyatlar: dict[str, float],
        portfoy_ozkaynak: float,
        zaman_ms: int,
        risk_atr: dict[str, np.ndarray],
        i: int,
    ) -> tuple[dict[str, tuple[Sinyal, float]], int]:
        """Hedefi risk motoruna sunar. Döner: `(onaylı hedefler, red sayısı)`.

        Risk devre dışıysa bu fonksiyon **kimliktir** — stratejinin hedefleri olduğu gibi
        geçer. Faz 1-4'ün risksiz ölçümleri bu yüzden bit düzeyinde korunuyor.
        """
        if self.risk is None:
            return {s.symbol: (s, s.target_exposure) for s in hedef.sinyaller}, 0

        olcumler: dict[str, PiyasaOlcumu] = {}
        for sinyal in hedef.sinyaller:
            sembol = sinyal.symbol
            fiyat = fiyatlar.get(sembol)
            if fiyat is None:
                raise CokluBacktestHatasi(
                    f"bar {i}: {sembol} için hedef üretildi ama fiyatı yok"
                )
            atr_degeri = float(risk_atr[sembol][i])
            olcumler[sembol] = PiyasaOlcumu(
                fiyat=fiyat,
                ozkaynak=portfoy_ozkaynak,
                mevcut_maruziyet=portfoy.maruziyet(sembol, fiyatlar)
                if sembol in fiyatlar
                else 0.0,
                bar_ms=zaman_ms,
                # NaN (ısınma penceresi) "ölçülemedi" demek, sıfır değil.
                atr=None if np.isnan(atr_degeri) else atr_degeri,
            )

        mevcut_maruziyetler = {
            s: portfoy.maruziyet(s, fiyatlar) for s in portfoy.sirali_semboller
        }
        karar = self.risk.portfoy_degerlendir(
            hedef, olcumler, mevcut_maruziyetler=mevcut_maruziyetler
        )
        onayli = karar.onayli_hedefler()
        return onayli, sum(1 for k in karar.kararlar if not isinstance(k, OnayliNiyet))

    # ------------------------------------------------------------------ sonuç

    def _sonuc(
        self,
        *,
        gorunum: EvrenGorunumu,
        adim: int,
        zamanlar: np.ndarray,
        kalite: dict[str, np.ndarray],
        ozkaynak: np.ndarray,
        brut: np.ndarray,
        islemler: list[Islem],
        atlanan: list[AtlamaSebebi],
        uretilen: int,
        bayat_degerleme: int,
        sifira_yazilan: int,
        kapasite_oranlari: list[float],
        portfoy: CokluPortfoy,
        olcum_baslangici: int,
        veri_sha256: dict[str, str],
        tekil_sembol: str | None,
        spread_bileseni: bool = False,
    ) -> Sonuc:
        ozkaynak = ozkaynak[olcum_baslangici:]
        brut = brut[olcum_baslangici:]
        olcum_zamanlari = zamanlar[olcum_baslangici:]
        olcum_n = len(olcum_zamanlari)

        if tekil_sembol is not None:
            sayim = Counter(str(k) for k in kalite[tekil_sembol][olcum_baslangici:])
            ok_olmayan = olcum_n - sayim.get(str(KaliteDurumu.OK), 0)
            veri = VeriKimligi(
                sembol=tekil_sembol,
                timeframe=gorunum.timeframe,
                sha256=veri_sha256.get(tekil_sembol, ""),
                bar_sayisi=olcum_n,
                ilk_ms=int(olcum_zamanlari[0]),
                son_ms=int(olcum_zamanlari[-1]),
                ok_olmayan_bar=ok_olmayan,
                ok_olmayan_oran=ok_olmayan / olcum_n,
                kalite_sayimi=dict(sayim),
            )
            evren = None
        else:
            veri, evren = self._evren_kimligi(
                gorunum, kalite, veri_sha256, olcum_baslangici, olcum_zamanlari
            )
            # Yalnızca politika açıkken: kapalıyken kayıt (ve `sonuc_hash`) Faz 10'daki gibi.
            if self.sifira_yaz_bar is not None:
                evren["sifira_yazma"] = {
                    "bar": self.sifira_yaz_bar,
                    "sifira_yazilan_pozisyon_bar": sifira_yazilan,
                }

        return Sonuc(
            veri=veri,
            strateji=self.strateji.sozluk(),
            maliyet=self.maliyet.sozluk(),
            maliyetler=None if self.maliyetler is None else maliyetler_govdesi(self.maliyetler),
            # Tek modelde `None`: eski `Sonuc` biçimi aynen; bayrak `maliyet["gecici"]`den okunur.
            gecici=None if self.maliyetler is None else gecici_mi(self.maliyet, self.maliyetler),
            baslangic_sermaye=self.baslangic_sermaye,
            seed=self.seed,
            metrikler=hesapla(
                ozkaynak,
                brut,
                islemler,
                adim,
                self.baslangic_sermaye,
                kapasite_oranlari=kapasite_oranlari,
                takvim=self.takvim,
                spread_bileseni=spread_bileseni,
            ),
            islemler=islemler,
            ozkaynak=ozkaynak,
            maruziyet=brut,
            zamanlar=olcum_zamanlari,
            atlanan=atlama_sayimi(atlanan)
            | ({"bayat_degerleme": bayat_degerleme} if tekil_sembol is None else {}),
            uretilen_sinyal=uretilen,
            acik_pozisyon_sonda=portfoy.acik,
            kalite_esigi=self.kalite_esigi,
            evren=evren,
            takvim=self.takvim_kaydi(),
            risk=None if self.risk is None else self.risk.ozet(),
        )

    @staticmethod
    def _evren_kimligi(
        gorunum: EvrenGorunumu,
        kalite: dict[str, np.ndarray],
        veri_sha256: dict[str, str],
        olcum_baslangici: int,
        olcum_zamanlari: np.ndarray,
    ) -> tuple[VeriKimligi, dict[str, object]]:
        """Çok enstrümanlı koşunun veri kimliği.

        **Kalite oranı üye barlar üzerinden sayılır.** Evrenin tamamı üzerinden sayılsaydı
        700 sembollü bir koşuda barların büyük çoğunluğu "listelenmedi" olurdu ve K-006'nın
        veri kalitesi uyarısı her koşuda tetiklenirdi — yani anlamını kaybederdi.
        """
        satirlar: list[dict[str, object]] = []
        toplam_sayim: Counter[str] = Counter()
        uye_toplam = 0
        for sembol in gorunum.semboller:
            u = np.asarray(gorunum.uyelik[sembol])[olcum_baslangici:]
            bayraklar = np.asarray(kalite[sembol], dtype=object)[olcum_baslangici:][u]
            sayim = Counter(str(b) for b in bayraklar)
            toplam_sayim.update(sayim)
            uye_toplam += int(u.sum())
            mevcut_dizi = (
                np.asarray(kalite[sembol], dtype=object)[olcum_baslangici:] != LISTELENMEDI
            )
            satirlar.append(
                {
                    "sembol": sembol,
                    "sha256": veri_sha256.get(sembol, ""),
                    "bar_sayisi": int(mevcut_dizi.sum()),
                    "uye_bar": int(u.sum()),
                    "ok_olmayan_bar": int(u.sum()) - sayim.get(str(KaliteDurumu.OK), 0),
                }
            )

        ok_olmayan = uye_toplam - toplam_sayim.get(str(KaliteDurumu.OK), 0)
        evren: dict[str, object] = {
            "kural_kimligi": gorunum.kural_kimligi,
            "enstruman_sayisi": len(gorunum.semboller),
            "uye_bar_toplami": uye_toplam,
            "enstrumanlar": satirlar,
        }
        veri = VeriKimligi(
            sembol=f"EVREN:{gorunum.kural_kimligi[:12]}" if gorunum.kural_kimligi else "EVREN",
            timeframe=gorunum.timeframe,
            sha256=nesne_hash({"enstrumanlar": [(s["sembol"], s["sha256"]) for s in satirlar]}),
            bar_sayisi=len(olcum_zamanlari),
            ilk_ms=int(olcum_zamanlari[0]),
            son_ms=int(olcum_zamanlari[-1]),
            ok_olmayan_bar=ok_olmayan,
            ok_olmayan_oran=ok_olmayan / uye_toplam if uye_toplam else 0.0,
            kalite_sayimi=dict(toplam_sayim),
        )
        return veri, evren


@dataclass(slots=True)
class AdimGirdisi:
    """Tek bir adımın okuduğu diziler. Görünüm değişmedikçe yeniden kurulmaz."""

    gorunum: EvrenGorunumu
    zamanlar: np.ndarray
    acilis: dict[str, np.ndarray]
    kapanis: dict[str, np.ndarray]
    kalite: dict[str, np.ndarray]
    risk_atr: dict[str, np.ndarray]
    adv: dict[str, np.ndarray]
    kotasyon: dict[str, tuple[np.ndarray, np.ndarray]] = field(default_factory=dict)
    """Sembol → `(bid_open, ask_open)` dizileri; yalnız bid/ask'i olan semboller (K-094). Boş =
    tek fiyat."""


class CokluAdimci:
    """Döngü gövdesinin **tek** uygulaması: bir barın fill → değerleme → risk → karar sırası.

    **Neden ayrı bir sınıf (Faz 14, K-001).** Backtest bütün barları bir döngüde bu adımdan
    geçirir; canlı paper motoru her kapanmış ızgara barında bir kez çağırır. İki ayrı döngü
    yazmak, aynı barın backtest'te ve canlıda farklı işlendiği bir sistemi üretirdi — tek
    sembollü motorun çok enstrümanlının sarmalayıcısı olmasıyla (K-057) aynı ilke.

    Durum (portföy, açık işlemler, bekleyen hedef, sayaçlar) burada yaşar ve adımlar arasında
    taşınır. **Barlar arası mesafe indeksle değil adım sayacıyla** ölçülür (`sifira_yaz_bar`):
    canlıda pencere kaydıkça indeks aynı barı göstermez, sayaç gösterir. Backtest'te ikisi
    birebir aynıdır (her indeks bir kez, sırayla), dolayısıyla eski sonuçlar değişmez.
    """

    def __init__(self, motor: CokluBacktest) -> None:
        self.motor = motor
        motor.strateji.hazirla()
        self.portfoy = CokluPortfoy(nakit=motor.baslangic_sermaye)
        self.islemler: list[Islem] = []
        self.acik: dict[str, Islem] = {}
        self.bekleyen: dict[str, tuple[Sinyal, float]] | None = None
        self.atlanan: list[AtlamaSebebi] = []
        self.uretilen = 0
        self.bayat_degerleme = 0
        self.sifira_yazilan = 0
        self.kapasite_oranlari: list[float] = []
        self.son_acilis: dict[str, float] = {}
        self.son_kapanis: dict[str, float] = {}
        self.son_bar: dict[str, int] = {}
        self.sayac = 0

    def adim(
        self, girdi: AdimGirdisi, i: int, *, isinma: bool, son_bar: bool
    ) -> tuple[float, float]:
        """`i`. barı işler; `(özkaynak, brüt maruziyet)` döner (bu barın kapanışıyla).

        `isinma`: bu barın hedefi ölçüm dışında (atlanır). `son_bar`: hedef dolacağı barı
        bulamaz (backtest'in son barı; canlıda hiçbir zaman).
        """
        motor = self.motor
        gorunum = girdi.gorunum
        semboller = gorunum.semboller
        portfoy = self.portfoy
        sayac = self.sayac
        self.sayac += 1

        mevcut = {s: gorunum.mevcut(s, i) for s in semboller}
        for s in semboller:
            if mevcut[s]:
                self.son_acilis[s] = float(girdi.acilis[s][i])
                self.son_kapanis[s] = float(girdi.kapanis[s][i])
                self.son_bar[s] = sayac
        silinen: frozenset[str] = frozenset()
        if motor.sifira_yaz_bar is not None:
            silinen = frozenset(
                s
                for s in portfoy.sirali_semboller
                if not mevcut[s] and sayac - self.son_bar[s] >= motor.sifira_yaz_bar
            )

        # 1) Fill — bekleyen hedefler bu barın açılışından dolar (K-004).
        if self.bekleyen is not None:
            uygun: dict[str, tuple[Sinyal, float]] = {}
            for s in sorted(self.bekleyen):
                if not mevcut[s]:
                    self.atlanan.append(AtlamaSebebi.ENSTRUMAN_BARI_YOK)
                elif str(girdi.kalite[s][i]) != KaliteDurumu.OK:
                    self.atlanan.append(AtlamaSebebi.FILL_BARI_OK_DEGIL)
                else:
                    uygun[s] = self.bekleyen[s]
            if uygun:
                fiyatlar_a = motor._fiyatlar(
                    (*portfoy.sirali_semboller, *uygun), self.son_acilis, i, silinen
                )
                # Kotasyon yalnız bu barda barı olan (uygun) semboller için okunur; `son_acilis`
                # gibi "son bilinen" kotasyon yok — olmayan bara kotasyon uydurulmaz.
                kotasyonlar = {
                    s: (float(girdi.kotasyon[s][0][i]), float(girdi.kotasyon[s][1][i]))
                    for s in uygun
                    if s in girdi.kotasyon
                }
                emirler, atlama = emirleri_hazirla(
                    uygun, portfoy, fiyatlar_a, int(girdi.zamanlar[i]), motor.maliyet,
                    maliyetler=motor.fill_maliyetleri,
                    kotasyonlar=kotasyonlar or None,
                )
                for s in sorted(atlama):
                    self.atlanan.append(atlama[s])
                for emir in emirler:
                    portfoy, _ = uygula_coklu(
                        emir, portfoy, self.acik, self.islemler, risk=motor.risk
                    )
                    gunluk = float(girdi.adv[emir.sembol][i])
                    if gunluk > 0.0:
                        self.kapasite_oranlari.append(emir.notional / gunluk)
            self.bekleyen = None

        fiyatlar_k = motor._fiyatlar(portfoy.sirali_semboller, self.son_kapanis, i, silinen)
        self.bayat_degerleme += sum(1 for s in portfoy.sirali_semboller if not mevcut[s])
        self.sifira_yazilan += sum(1 for s in portfoy.sirali_semboller if s in silinen)
        portfoy_ozkaynak = portfoy.ozkaynak(fiyatlar_k)

        # 2) Risk durumunun bu barla güncellenmesi — **karardan önce.**
        if motor.risk is not None:
            motor.risk.bar_isle(int(girdi.zamanlar[i]), portfoy_ozkaynak)

        # 3) Karar — evren `ctx`i `t`de kesiktir; `ok` olmayan bar görünmez (K-028).
        pozisyonlar = {s: portfoy.gorunum(s, fiyatlar_k) for s in portfoy.sirali_semboller}
        ctx = gorunum.baglam(
            i, pozisyonlar, portfoy.nakit_agirligi(fiyatlar_k), motor.strateji.parametreler
        )
        hedef = motor.strateji.on_bar(ctx)
        if hedef is not None and hedef.sinyaller:
            self.uretilen += len(hedef.sinyaller)
            if isinma:
                self.atlanan.extend([AtlamaSebebi.ISINMA_PENCERESI] * len(hedef.sinyaller))
            elif son_bar:
                # Son barın hedefi dolacağı barı bulamaz (K-004).
                self.atlanan.extend([AtlamaSebebi.SONRAKI_BAR_YOK] * len(hedef.sinyaller))
            else:
                onayli, red_sayisi = motor._risk_onayi(
                    hedef,
                    portfoy,
                    motor._fiyatlar(
                        (*portfoy.sirali_semboller, *hedef.semboller), self.son_kapanis, i,
                        silinen,
                    ),
                    portfoy_ozkaynak,
                    int(girdi.zamanlar[i]),
                    girdi.risk_atr,
                    i,
                )
                self.atlanan.extend([AtlamaSebebi.RISK_REDDETTI] * red_sayisi)
                self.bekleyen = onayli or None

        self.portfoy = portfoy
        # 4) Değerleme — bu barın kapanışlarıyla işaretle.
        return portfoy_ozkaynak, portfoy.brut_maruziyet(fiyatlar_k)


__all__ = ["AdimGirdisi", "CokluAdimci", "CokluBacktest", "CokluBacktestHatasi"]
