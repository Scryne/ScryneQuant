"""Çoklu test düzeltmesinin evren çekilişlerine genişletilmesi. (Faz 12, K-044'ün devamı)

`research/coklu_test.py` K-044'ün null'ını tek sembollü çekilişler için kuruyor: her
çekilişin OOS **sinyal takvimi** dairesel kaydırılıp gerçek motordan geçiriliyor. Faz 12'nin
evren çekilişleri (hipotez 39-) bu yola uymuyor: portföy hedefini zamanda kaydırmak, o anda
listelenmemiş ya da evren dışındaki sembollere hedef yazmak olur ve motor bunu haklı olarak
reddeder. `sq lab coklu-test` bu yüzden evren çekilişlerini "değerlendirme kaydı yok" diye
atlıyordu — defter 48'e çıkmışken eşik 31 çekilişle ölçülmüş kalıyordu.

## Null modeli: sinyal özelliklerinin dairesel kaydırılması

Her evren çekilişi için, kayıtlı seçilmiş parametrelerle OOS görünümü **bir kez** kurulur.
Her iterasyonda yalnızca stratejinin **sinyal özellikleri** (`SINYAL_OZELLIKLERI`: sıralama
skoru, funding/basis skoru, makro persentil) dilim içinde `k` bar dairesel kaydırılır ve
gerçek motordan geçirilir. Kaydırma bütün sembollerde **aynı** `k`: kesitteki korelasyon ve
her serinin kendi otokorelasyonu korunur, yok edilen tek şey sinyalin gelecekteki getiriyle
hizası.

**Kural:** kaydırılan şey, çekilişin **iddiasını taşıyan** özelliktir; iskelet kaydırılmaz.
Barlar, PIT üyelik, yeniden dengeleme takvimi, maliyet ve K-059 değerleme politikası her
zaman yerinde kalır. Yani null, **aynı iskeletin** beceri olmadan çalışan hâli.

Hangi özelliğin iskelet, hangisinin iddia olduğu **çekilişe göre değişir** ve bu yüzden
`SINYAL_OZELLIKLERI` strateji başına yazılır:

- Kesitsel/türev/makro/konumlanma çekilişlerinde iddia, kıyasın üstüne konan skordur;
  `kote_hacim` (sıralama) ve `atr` (boyut) iskeletin parçasıdır ve kaydırılmaz.
- `kurma_evren` çekilişlerinde (Faz 16) iddia tam olarak kurma katmanındadır:
  `evren_oynaklik_agirlik`in iddiası `atr`'nin boyutlandırmada işe yaradığıdır, dolayısıyla
  orada kaydırılan `atr`'dir. Aynı özelliğin bir çekilişte iskelet, ötekinde iddia olması
  çelişki değil; sabit bir liste tutmak çelişki olurdu.
- `evren_turnover_bandi`in **hiçbir tahmini yok** — bant bir şey öngörmez, ağırlık
  değişimini bastırır. Kaydırılacak doğal bir sinyal olmadığı için sıralama ölçüsü
  kaydırılıyor ve **bu bir yaklaşımdır**: null'da bant da çalıştığı için null dağılımı
  sıfır çevresinde değil, kaydırılmış kıyasın Sharpe'ı çevresinde toplanır. O çekiliş için
  ölçülen düzeltme muhafazakâr değildir; sınır raporda açık kalem olarak durur.

## Paylaşılan oran

Tek sembollü null ile aynı: iterasyon başına tek bir `oran ∈ [0,1)` çekilir ve her çekilişte
`k = 1 + ⌊oran·(L−2)⌋` olur (`L` o çekilişin dilim uzunluğu). Oranlar aynı tohumla aynı
sırada üretilir (`oranlar`), böylece evren ve tek sembollü satırlar aynı iterasyonda
birleştirilebilir (`birlesik_null`). `k = 0` seçilmez: gerçek dizilim null örneği değildir.

## Doğrulama (K-038 kalıbı)

Kaydırmasız (`k = 0`) koşu kayıttaki OOS `sonuc_hash`i **bit düzeyinde** vermeli; vermezse
ölçüm durur (`EvrenCokluTestHatasi`). Görünüm, strateji ya da politika kaydedilenden
farklıysa null o çekilişin null'ı değildir.

## Ölçmediği

- Kesitsel çekilişlerde `skor_ham` (ROC/ATR) geç listelenen sembolde `NaN` bölgeleri taşır;
  kaydırma o bölgeleri başka zamana taşır ve bazı sembollerin aday olduğu barları değiştirir.
  Etkisi aday **sayısını** hafifçe oynatmak; yön belirsiz, yazılı.
- Uygunluk tek sembollü null ile aynı ucuz kapılar (`asgari_islem`, `max_drawdown`):
  gerçek promotion'dan gevşek, düzeltmeyi büyük gösterir (K-007 yönü).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

import numpy as np

from scryne_quant.backtest.coklu_motor import CokluBacktest
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.research import coklu_test as coklu_mod
from scryne_quant.research.bolme import Pencere
from scryne_quant.research.evren_kosu import EvrenVerisi
from scryne_quant.strategy.baglam import PiyasaGorunumu
from scryne_quant.strategy.evren import EvrenGorunumu
from scryne_quant.strategy.temel import PortfoyStratejisi

#: Strateji adı → kaydırılan sinyal özellikleri. Burada olmayan bir evren stratejisi null'a
#: giremez: hangi özelliğin "bilgi" olduğu stratejinin tanımından okunmalı, tahmin edilmez.
SINYAL_OZELLIKLERI: Final[dict[str, tuple[str, ...]]] = {
    "kesitsel_guc": ("skor_ham",),
    "kesitsel_ters": ("skor_ham",),
    "kesitsel_dusuk_oynaklik": ("skor_ham",),
    "evren_funding_kesit": ("funding_skor",),
    "evren_funding_birikim": ("funding_skor",),
    "evren_basis": ("funding_skor",),
    "evren_funding_basis": ("funding_skor", "basis_skor"),
    "evren_makro_vix": ("makro_persentil",),
    "evren_makro_nfci": ("makro_persentil",),
    # Konumlanma ailesi (Faz 16) funding iskeletini miras alıyor, dolayısıyla skorun özellik
    # adı da `funding_skor` — ölçülen seri farklı, taşıyıcı alan aynı. `evren_oi_taker` iki
    # skor taşır (`evren_funding_basis` kalıbı).
    "evren_oi_birikim": ("funding_skor",),
    "evren_taker_baski": ("funding_skor",),
    "evren_buyuk_hesap": ("funding_skor",),
    "evren_oi_taker": ("funding_skor", "taker_skor"),
    # Kurma ailesi (Faz 16): iddia seçimde değil **boyutlandırmada**. Oynaklık ayarlı
    # çekilişte kaydırılan şey `atr` — "1/σ ağırlıklandırma gelecekteki getiriyle hizalı
    # mı" sorusunun null'ı budur.
    "evren_oynaklik_agirlik": ("atr",),
    # Turnover bandının **hiçbir tahmini yok**: bant, ağırlık değişimini bastırır, bir şey
    # öngörmez. Kaydırılacak doğal bir "sinyal" olmadığı için sıralama ölçüsü (`kote_hacim`)
    # kaydırılıyor: null, aynı bandın rastgele zamanlanmış bir seçim üzerinde ne yaptığı.
    # **Bu bir yaklaşımdır ve sınırı yazılı:** bandın kendi etkisi null'da da yaşıyor,
    # dolayısıyla ölçülen düzeltme bu çekiliş için muhafazakâr değil (raporda açık kalem).
    "evren_turnover_bandi": ("kote_hacim",),
    # Zaman serisi trend (R5, `fx_fiyat`): iddia `roc > 0` eşiği, taşıyıcı alan kesitsel
    # ailelerle aynı (`skor_ham`). Kaydırılan skor eşiği de sıralamayı da rastgele zamanlar.
    "zaman_serisi_trend": ("skor_ham",),
    # Ortalama dönüş (R6, `fx_ortalama_donus`): iddia sma/rsi eşiği; taşıyıcı alan `skor_ham`.
    "zaman_serisi_sapma": ("skor_ham",),
    "zaman_serisi_rsi": ("skor_ham",),
}


class EvrenCokluTestHatasi(ValueError):
    """Evren null ölçümünün girdisi geçersiz ya da kayıtla uyuşmuyor."""


def oranlar(deneme: int, seed: int) -> list[float]:
    """`coklu_test.null_dagilimi` ile **aynı** oran dizisi (aynı tohum, aynı çekim sırası)."""
    if deneme < 1:
        raise EvrenCokluTestHatasi(f"deneme sayısı pozitif olmalı: {deneme}")
    rng = np.random.default_rng(seed)
    return [float(rng.random()) for _ in range(deneme)]


def kaydirilmis_gorunum(
    gorunum: EvrenGorunumu, adlar: Sequence[str], k: int
) -> EvrenGorunumu:
    """Yalnızca `adlar` özelliklerini bütün sembollerde `k` bar dairesel kaydırır."""
    yeni = {}
    for sembol, g in gorunum.gorunumler.items():
        ozellikler = dict(g.ozellikler)
        for ad in adlar:
            if ad not in ozellikler:
                raise EvrenCokluTestHatasi(f"{sembol}: sinyal özelliği {ad!r} görünümde yok")
            dizi = np.roll(ozellikler[ad], k)
            dizi.flags.writeable = False
            ozellikler[ad] = dizi
        yeni[sembol] = PiyasaGorunumu(
            sembol=g.sembol, timeframe=g.timeframe, barlar=g.barlar, ozellikler=ozellikler
        )
    return EvrenGorunumu(
        timeframe=gorunum.timeframe,
        zamanlar=gorunum.zamanlar,
        gorunumler=yeni,
        uyelik=gorunum.uyelik,
        kural_kimligi=gorunum.kural_kimligi,
    )


@dataclass(frozen=True, slots=True)
class EvrenCekilisi:
    """Null'a giren tek bir evren çekilişi (kayıttan)."""

    kimlik: str
    strateji: str
    parametreler: dict[str, Any]
    gercek_sharpe: float
    gercek_sonuc_hash: str
    sifira_yaz_bar: int | None
    satirlar: list[tuple[float, bool]] = field(default_factory=list, repr=False)
    """İterasyon sırasıyla `(oos_sharpe, uygun)`."""

    def sozluk(self) -> dict[str, Any]:
        sharpe = np.array([s for s, _ in self.satirlar], dtype=np.float64)
        return {
            "kimlik": self.kimlik,
            "strateji": self.strateji,
            "parametreler": self.parametreler,
            "gercek_sharpe": self.gercek_sharpe,
            "sifira_yaz_bar": self.sifira_yaz_bar,
            "null_sharpe": {
                f"p{p:02d}": float(np.percentile(sharpe, p)) for p in coklu_mod.PERSENTILLER
            } if sharpe.size else {},
            "uygun_oran": float(np.mean([u for _, u in self.satirlar])) if self.satirlar else None,
        }


def cekilis_null(
    cekilis: EvrenCekilisi,
    sinif: type[PortfoyStratejisi],
    veri: EvrenVerisi,
    maliyet: MaliyetModeli,
    pencere: Pencere,
    oran_dizisi: Sequence[float],
    uygun_mu: Callable[[int, float], bool],
    *,
    sizinti_bar: int = 0,
    ilerleme: Callable[[int], None] | None = None,
) -> EvrenCekilisi:
    """Bir evren çekilişinin iterasyon satırlarını üretir. Önce kaydı yeniden üretir.

    `sizinti_bar` (K-064): kaydırma, sinyali bu kadar bar öne alacak bölgeye girmez;
    `k ∈ [1, L−2−H]`. Önerilen değer stratejinin ısınması + yeniden dengeleme periyodu."""
    from scryne_quant.research import evren_degerlendirme as ed  # döngüsel import yok

    adlar = SINYAL_OZELLIKLERI.get(cekilis.strateji)
    if adlar is None:
        raise EvrenCokluTestHatasi(f"{cekilis.strateji}: sinyal özellikleri tanımlı değil")
    gorunum = ed.gorunum(veri, sinif(**cekilis.parametreler), pencere)

    def kos(g: EvrenGorunumu):
        return CokluBacktest(
            sinif(**cekilis.parametreler), maliyet, sifira_yaz_bar=cekilis.sifira_yaz_bar
        ).calistir(g, veri_sha256=veri.veri_sha256, olcum_baslangici=pencere.olcum_baslangici)

    gercek = kos(gorunum)
    if gercek.sonuc_hash != cekilis.gercek_sonuc_hash:
        raise EvrenCokluTestHatasi(
            f"{cekilis.strateji} ({cekilis.kimlik[:12]}): kaydırmasız koşu kayıttaki OOS "
            "sonuc_hash'ini üretmedi — null bu çekilişin null'ı olmaz, ölçüm durdu"
        )
    uzunluk = len(gorunum)
    h = max(0, int(sizinti_bar))
    if uzunluk - 2 - h < 1:
        raise EvrenCokluTestHatasi(f"sızıntı payı ({h}) dilimi ({uzunluk}) tüketiyor")
    satirlar: list[tuple[float, bool]] = []
    for j, oran in enumerate(oran_dizisi):
        k = 1 + int(oran * (uzunluk - 2 - h))
        s = kos(kaydirilmis_gorunum(gorunum, adlar, k))
        islem = len([i for i in s.islemler if i.kapali])
        uygun = bool(uygun_mu(islem, s.metrikler.max_drawdown))
        satirlar.append((float(s.metrikler.sharpe), uygun))
        if ilerleme is not None:
            ilerleme(j)
    return EvrenCekilisi(
        kimlik=cekilis.kimlik, strateji=cekilis.strateji, parametreler=cekilis.parametreler,
        gercek_sharpe=cekilis.gercek_sharpe, gercek_sonuc_hash=cekilis.gercek_sonuc_hash,
        sifira_yaz_bar=cekilis.sifira_yaz_bar, satirlar=satirlar,
    )


def birlesik_null(
    satirlar: Mapping[str, Sequence[tuple[float, bool]]],
    gercek: Mapping[str, tuple[str, float]],
    *,
    seed: int,
) -> coklu_mod.NullSonucu:
    """Tek sembollü ve evren satırlarını **aynı iterasyonda** birleştirip null'ı kurar.

    `satirlar`: kimlik → iterasyon sırasıyla `(sharpe, uygun)`; hepsi aynı uzunlukta ve
    aynı `oranlar(deneme, seed)` dizisiyle üretilmiş olmalı. `gercek`: kimlik →
    `(strateji, gerçek OOS Sharpe)`. Maksimum ve atlama kuralları `null_dagilimi` ile aynı.
    """
    if not satirlar:
        raise EvrenCokluTestHatasi("en az bir çekiliş gerekir")
    uzunluklar = {len(v) for v in satirlar.values()}
    if len(uzunluklar) != 1:
        raise EvrenCokluTestHatasi(f"satır uzunlukları farklı: {sorted(uzunluklar)}")
    deneme = uzunluklar.pop()
    azami: list[float] = []
    ham = np.empty(deneme, dtype=np.float64)
    uygun_sayisi: list[int] = []
    for d in range(deneme):
        tur = [v[d][0] for v in satirlar.values()]
        uygunlar = [v[d][0] for v in satirlar.values() if v[d][1]]
        ham[d] = max(tur)
        uygun_sayisi.append(len(uygunlar))
        if uygunlar:
            azami.append(max(uygunlar))
    if not azami:
        raise EvrenCokluTestHatasi("hiçbir iterasyonda uygun çekiliş çıkmadı")
    dizi = np.array(azami, dtype=np.float64)
    en_iyi = max(gercek.items(), key=lambda kv: kv[1][1])
    p = coklu_mod.PERSENTILLER
    return coklu_mod.NullSonucu(
        cekilis_sayisi=len(satirlar),
        deneme=deneme,
        seed=seed,
        gercek_en_iyi=en_iyi[1][1],
        gercek_en_iyi_strateji=en_iyi[1][0],
        azami_dagilimi={f"p{x:02d}": float(np.percentile(dizi, x)) for x in p},
        ham_azami_dagilimi={f"p{x:02d}": float(np.percentile(ham, x)) for x in p},
        uygun_oran=float(np.mean(uygun_sayisi) / len(satirlar)),
        p_degeri=float((dizi >= en_iyi[1][1]).mean()),
        tekil_dagilim={
            k: {f"p{x:02d}": float(np.percentile([s for s, _ in v], x)) for x in p}
            for k, v in satirlar.items()
        },
        azami=dizi,
    )


__all__ = [
    "SINYAL_OZELLIKLERI",
    "EvrenCekilisi",
    "EvrenCokluTestHatasi",
    "birlesik_null",
    "cekilis_null",
    "kaydirilmis_gorunum",
    "oranlar",
]
