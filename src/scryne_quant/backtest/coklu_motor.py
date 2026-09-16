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

import numpy as np

from scryne_quant.backtest.defter import uygula_coklu
from scryne_quant.backtest.fill import AtlamaSebebi, emirleri_hazirla
from scryne_quant.backtest.metrikler import Islem, gunluk_hacim, hesapla
from scryne_quant.backtest.sonuc import VARSAYILAN_KALITE_ESIGI, Sonuc, VeriKimligi, atlama_sayimi
from scryne_quant.common.hash import nesne_hash
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.common.zaman import timeframe_ms
from scryne_quant.data.semalar import KaliteDurumu
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
    ) -> None:
        if baslangic_sermaye <= 0.0:
            raise CokluBacktestHatasi(
                f"başlangıç sermayesi pozitif olmalı: {baslangic_sermaye}"
            )
        self.strateji = strateji
        self.maliyet = maliyet
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

        adim = timeframe_ms(gorunum.timeframe)
        zamanlar = np.asarray(gorunum.zamanlar, dtype="int64")
        acilis = {s: gorunum.gorunumler[s].barlar["open"] for s in semboller}
        kapanis = {s: gorunum.gorunumler[s].barlar["close"] for s in semboller}
        kalite = {s: gorunum.gorunumler[s].barlar["quality_status"] for s in semboller}

        risk_atr = self._risk_atr(gorunum) if self.risk is not None else {}
        # Kapasite ölçüsü (§16): fill notional'ının o enstrümanın ortalama günlük hacmine
        # oranı. Raporlanır, kapı değildir (K-054) — eşiği ölçülmemiş bir sayı kapı olamaz.
        adv = {
            s: gunluk_hacim(gorunum.gorunumler[s].barlar["quote_volume"], adim)
            for s in semboller
        }
        kapasite_oranlari: list[float] = []

        self.strateji.hazirla()
        portfoy = CokluPortfoy(nakit=self.baslangic_sermaye)

        ozkaynak = np.empty(n, dtype=np.float64)
        brut = np.empty(n, dtype=np.float64)
        islemler: list[Islem] = []
        acik: dict[str, Islem] = {}
        bekleyen: dict[str, tuple[Sinyal, float]] | None = None
        atlanan: list[AtlamaSebebi] = []
        uretilen = 0
        bayat_degerleme = 0

        son_acilis: dict[str, float] = {}
        son_kapanis: dict[str, float] = {}
        son_bar: dict[str, int] = {}
        sifira_yazilan = 0

        for i in range(n):
            mevcut = {s: gorunum.mevcut(s, i) for s in semboller}
            for s in semboller:
                if mevcut[s]:
                    son_acilis[s] = float(acilis[s][i])
                    son_kapanis[s] = float(kapanis[s][i])
                    son_bar[s] = i
            silinen: frozenset[str] = frozenset()
            if self.sifira_yaz_bar is not None:
                silinen = frozenset(
                    s
                    for s in portfoy.sirali_semboller
                    if not mevcut[s] and i - son_bar[s] >= self.sifira_yaz_bar
                )

            # 1) Fill — bekleyen hedefler bu barın açılışından dolar (K-004).
            if bekleyen is not None:
                uygun: dict[str, tuple[Sinyal, float]] = {}
                for s in sorted(bekleyen):
                    if not mevcut[s]:
                        atlanan.append(AtlamaSebebi.ENSTRUMAN_BARI_YOK)
                    elif str(kalite[s][i]) != KaliteDurumu.OK:
                        atlanan.append(AtlamaSebebi.FILL_BARI_OK_DEGIL)
                    else:
                        uygun[s] = bekleyen[s]
                if uygun:
                    fiyatlar_a = self._fiyatlar(
                        (*portfoy.sirali_semboller, *uygun), son_acilis, i, silinen
                    )
                    emirler, atlama = emirleri_hazirla(
                        uygun, portfoy, fiyatlar_a, int(zamanlar[i]), self.maliyet
                    )
                    for s in sorted(atlama):
                        atlanan.append(atlama[s])
                    for emir in emirler:
                        portfoy, _ = uygula_coklu(
                            emir, portfoy, acik, islemler, risk=self.risk
                        )
                        gunluk = float(adv[emir.sembol][i])
                        if gunluk > 0.0:
                            kapasite_oranlari.append(emir.notional / gunluk)
                bekleyen = None

            fiyatlar_k = self._fiyatlar(portfoy.sirali_semboller, son_kapanis, i, silinen)
            bayat_degerleme += sum(1 for s in portfoy.sirali_semboller if not mevcut[s])
            sifira_yazilan += sum(1 for s in portfoy.sirali_semboller if s in silinen)
            portfoy_ozkaynak = portfoy.ozkaynak(fiyatlar_k)

            # 2) Risk durumunun bu barla güncellenmesi — **karardan önce.**
            if self.risk is not None:
                self.risk.bar_isle(int(zamanlar[i]), portfoy_ozkaynak)

            # 3) Karar — evren `ctx`i `t`de kesiktir; `ok` olmayan bar görünmez (K-028).
            pozisyonlar = {
                s: portfoy.gorunum(s, fiyatlar_k) for s in portfoy.sirali_semboller
            }
            ctx = gorunum.baglam(
                i,
                pozisyonlar,
                portfoy.nakit_agirligi(fiyatlar_k),
                self.strateji.parametreler,
            )
            hedef = self.strateji.on_bar(ctx)
            if hedef is not None and hedef.sinyaller:
                uretilen += len(hedef.sinyaller)
                if i < olcum_baslangici:
                    atlanan.extend([AtlamaSebebi.ISINMA_PENCERESI] * len(hedef.sinyaller))
                elif i == n - 1:
                    # Son barın hedefi dolacağı barı bulamaz (K-004).
                    atlanan.extend([AtlamaSebebi.SONRAKI_BAR_YOK] * len(hedef.sinyaller))
                else:
                    onayli, red_sayisi = self._risk_onayi(
                        hedef,
                        portfoy,
                        self._fiyatlar(
                            (*portfoy.sirali_semboller, *hedef.semboller), son_kapanis, i,
                            silinen,
                        ),
                        portfoy_ozkaynak,
                        int(zamanlar[i]),
                        risk_atr,
                        i,
                    )
                    atlanan.extend([AtlamaSebebi.RISK_REDDETTI] * red_sayisi)
                    bekleyen = onayli or None

            # 4) Değerleme — bu barın kapanışlarıyla işaretle.
            ozkaynak[i] = portfoy_ozkaynak
            brut[i] = portfoy.brut_maruziyet(fiyatlar_k)

        return self._sonuc(
            gorunum=gorunum,
            adim=adim,
            zamanlar=zamanlar,
            kalite=kalite,
            ozkaynak=ozkaynak,
            brut=brut,
            islemler=islemler,
            atlanan=atlanan,
            uretilen=uretilen,
            bayat_degerleme=bayat_degerleme,
            sifira_yazilan=sifira_yazilan,
            kapasite_oranlari=kapasite_oranlari,
            portfoy=portfoy,
            olcum_baslangici=olcum_baslangici,
            veri_sha256=dict(veri_sha256 or {}),
            tekil_sembol=tekil_sembol,
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
            baslangic_sermaye=self.baslangic_sermaye,
            seed=self.seed,
            metrikler=hesapla(
                ozkaynak,
                brut,
                islemler,
                adim,
                self.baslangic_sermaye,
                kapasite_oranlari=kapasite_oranlari,
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


__all__ = ["CokluBacktest", "CokluBacktestHatasi"]
