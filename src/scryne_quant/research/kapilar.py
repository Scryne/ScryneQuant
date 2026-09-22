"""Promotion kapılarının sayısal eşikleri. (K-010, K-018, K-019)

K-018 şunu şart koştu: *"K-010'un kapıları sayısal eşiklerle tanımlanır ve makine kontrol
eder. 'Sonuçlara bak ve karar ver' bir kapı değildir."* Bu modül o eşiklerin adresi.

**Faz 4 eşikleri belirler, Faz 5 uygular.** Burada bir sonucun kapılardan geçip
geçmediğini **söyleyen** kod var; sinyalin execution'a ulaşmasını engelleyen mekanizma
Faz 5'in risk motorunda kurulacak. İkisini ayırmak bilinçli: eşiklerin gerekçesi bu fazın
ölçümlerinden geliyor, zorlama ise başka bir katmanın işi.

**Eşikler nasıl seçildi:** Faz 4'ün gerçek ölçümlerine bakılarak — ama "bugünkü en iyi
stratejiyi geçirecek" biçimde değil. Tam tersi: Faz 4'te ölçülen **hiçbir strateji bu
kapılardan geçmiyor** ve bu doğru sonuçtur. Eşiği bugünkü sonuca göre gevşetmek, kapıyı
kaldırmakla aynı şey olurdu (K-010'un uyardığı sabırsızlık).

Kapılar bir stratejiyi *iyi* ilan etmez; yalnızca **"paper trading'e aday olabilir"**
der. Zincirin geri kalanı (paper, live adayı, elle onay) K-010'da.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

import numpy as np


@dataclass(frozen=True, slots=True)
class Esik:
    """Tek bir kapı: ne ölçülüyor, sınır ne, hangi yönde geçilir, neden bu sayı."""

    ad: str
    alan: str
    """Değerlendirilen sözlükteki anahtar."""

    sinir: float
    yon: str
    """`>=` (sınırdan büyük/eşit geçer) veya `<=` (küçük/eşit geçer)."""

    gerekce: str

    def gecti_mi(self, deger: float | None) -> bool | None:
        """`None` = ölçülemedi. Ölçülemeyen bir kapı **geçilmiş sayılmaz**."""
        if deger is None or (isinstance(deger, float) and np.isnan(deger)):
            return None
        return deger >= self.sinir if self.yon == ">=" else deger <= self.sinir

    def sozluk(self) -> dict[str, Any]:
        return {
            "ad": self.ad,
            "alan": self.alan,
            "sinir": self.sinir,
            "yon": self.yon,
            "gerekce": self.gerekce,
        }


#: `oos_sharpe` kapısının çoklu test için düzeltilmiş sınırı. (K-044)
#:
#: Ölçüm geçmişi:
#: - K-044 (Faz 4): 31 tek sembollü çekiliş, 4.000 iterasyon → 1,021 (%90 GA 0,975-1,055).
#: - K-064 (Faz 12): 41 çekiliş (31 tek sembollü + 10 evren), 500 iterasyon, **sızıntısız**
#:   kaydırma → 1,039 (%90 GA 0,975-1,076). `tools/faz12_coklu_test.py
#:   --sonradan-sizintisiz`, kayıt `runs/faz12/coklu-test-sizintisiz-500-0.json`. Sızıntılı
#:   yöntemle aynı satırlar 1,154 veriyordu; evren çekilişlerinin kendi null'ı 0,53.
#:
#: Sabit, iki ölçümden **tutucu** olanın yukarı yuvarlanmışı (K-007). Bu sayı defterin bir
#: fotoğrafıdır: ölçülebilir çekiliş sayısı değişirse yeniden ölçülür, elle büyütülmez.
COKLU_TEST_ESIGI: Final = 1.04

#: Düzeltmenin ölçüldüğü defter durumu. Defter bundan farklıysa `COKLU_TEST_ESIGI`
#: **bayattır**: daha çok çekiliş, daha yüksek bir eşik demek (K-039, K-044).
#: 2026-09-18'de 43'e çıktı (K-071): 31 tek sembollü + 12 evren, hepsi sızıntı paylı
#: yöntemle **yeniden koşuldu** — K-064'ün "sonradan dışlama" yaklaşımı değil.
#: 2026-09-20'de 45 (K-081, R1(c)): h51/h52 (kurma_evren) eklendi, 31 tek sembollü + 14 evren,
#: 500 deneme, seed 0; %5 sınırı 1,004 (%90 GA 0,982–1,064); sabit
#: değişmedi. 2026-09-22'de 47 (K-108, R7): h60/h61 (portfoy_kurma) eklendi, 31 tek sembollü +
#: 16 evren (h53-h59 FX ölçülemez, K-102/6); %5 sınırı 1,004 aynı; sabit değişmedi.
#: Bu sayı bir **eşik değil**, eşiğin ölçüldüğü defter fotoğrafıdır ve git'teki
#: `docs/research/coklu-test-olcum.json` ile eşit olmak zorundadır (`coklu_test_fotograf`).
COKLU_TEST_CEKILIS_SAYISI: Final = 47

#: K-019'un eşikleri. Her biri Faz 4'ün ölçümüne dayanıyor; gerekçeler
#: `docs/Faz-4-Laboratuvar-Raporu.md`'de ayrıntılı. `oos_sharpe` ayrıca K-044'ün
#: çoklu test düzeltmesini taşıyor.
ESIKLER: Final[tuple[Esik, ...]] = (
    Esik(
        ad="oos_sharpe",
        alan="oos_sharpe",
        sinir=COKLU_TEST_ESIGI,
        yon=">=",
        gerekce=(
            "Out-of-sample Sharpe, **çoklu test için düzeltilmiş** (K-044). İlk değer "
            "0,5'ti ve gerekçesi tek bir stratejiye bakmaktı: Faz 4'te al-tut kıyasının "
            "in-sample Sharpe'ı 0,70 ölçülmüştü, 0,5 o çizginin biraz altında duruyordu. "
            "O gerekçe yanlış değildi ama **eksikti**: kapıya kaç kez gidildiğini "
            "saymıyordu. Defterdeki 31 ölçülebilir çekiliş, edge'i olmayan bir dünyada "
            "yeniden koşturulduğunda en iyi çekiliş vakaların %26,3'ünde 0,5'i geçiyor "
            "— yani 0,5, %5'lik bir kapı değil %26'lık bir kapıydı. Ölçülen %5 sınırı "
            "1,021 (31 çekiliş, %90 GA 0,975-1,055; 4.000 iterasyon). Faz 12'de 41 "
            "çekilişle (10 evren dahil) sızıntısız kaydırmayla yeniden ölçüldü: 1,039 "
            f"(%90 GA 0,975-1,076; K-064); sabit tutucu olan, {COKLU_TEST_ESIGI}. Bağımsız "
            "çapraz kontrol (Deflated Sharpe) 0,92 veriyor, Bonferroni ise 1,30 — "
            "bağımsızlık varsaydığı için fazla düzeltiyor. "
            "**2026-09-18 yeniden ölçümü (K-071):** 43 çekiliş, hepsi sızıntı paylı "
            "yöntemle yeniden koşuldu (K-064'ün sonradan dışlaması bir yaklaşımdı). "
            "Ölçülen %5 sınırı 0,926 (%90 GA 0,838-0,967) ve bu sabitin gerçek "
            "yanlış-pozitif oranı %2,6 — yani kapı tasarım hedefinden (%5) **daha sıkı**. "
            "Sabit indirilmedi: 1,04'ü 0,93'e çekmek bir kapıyı gevşetmektir ve gerekçesi "
            "yalnızca 'tam %5 olsun' olurdu (K-007, K-050). Eşik **defterin bugünkü hâline "
            "bağlı**: çekiliş sayısı değişirse yeniden ölçülmeli (`sq lab coklu-test` tek "
            "sembollü, `tools/faz12_coklu_test.py` evren dahil). "
            "**2026-09-20 yeniden ölçümü (K-081, R1(c)):** 45 çekiliş (h51/h52 eklendi), "
            "500 deneme, seed 0, veri sonu 2026-09-14 23:00 UTC. Ölçülen %5 sınırı 1,004 "
            "(%90 GA 0,982-1,064) — aralık 1,04'ü kapsıyor; sabitin gerçek yanlış-pozitifi "
            "%4,2 (hedef %5); 52 çekilişin hiçbiri iki sayıyı da aşmıyor. Mevcut politika "
            "eşiği **korundu**; 1,004 bir ölçüm değeridir, eşik yapılmadı. Bekçi artık "
            "git'teki fotoğrafı (`docs/research/coklu-test-olcum.json`) ve defteri sayıyor."
        ),
    ),
    Esik(
        ad="oos_is_orani",
        alan="oos_is_orani",
        sinir=0.5,
        yon=">=",
        gerekce=(
            "OOS Sharpe'ın IS Sharpe'a oranı — overfitting'in en doğrudan ölçüsü. "
            "Faz 4'te altı stratejinin **altısında da** bu oran negatif çıktı "
            "(−0,09 ile −4,15 arası): in-sample başarı dışarıda tamamen kayboldu. "
            "0,5, 'IS performansının en az yarısı korunmuş olmalı' demek."
        ),
    ),
    Esik(
        ad="wf_katman_basari",
        alan="wf_pozitif_katman_orani",
        sinir=0.6,
        yon=">=",
        gerekce=(
            "Walk-forward katmanlarının kaçı pozitif getirdi. Bileşik OOS getirisi tek "
            "bir şanslı katmandan gelebilir; katman başarı oranı bunu ayırt eder. 0,6, "
            "16 katmanın en az 10'unda kazanmayı şart koşuyor."
        ),
    ),
    Esik(
        ad="parametre_kararliligi",
        alan="wf_kararsizlik",
        sinir=0.35,
        yon="<=",
        gerekce=(
            "Katmanlar arası benzersiz parametre değeri oranı (ortalama). Faz 4'te "
            "0,15-0,25 arası ölçüldü — yani prosedür 16 katmanda 2-4 farklı parametre "
            "seçiyor. 0,35 üstü 'her dönem başka bir şey seçiliyor' demektir ve o "
            "strateji canlıda hangi parametreyle çalıştırılacağı sorusuna cevap veremez."
        ),
    ),
    Esik(
        ad="asgari_islem",
        alan="oos_islem",
        sinir=30,
        yon=">=",
        gerekce=(
            "Out-of-sample işlem sayısı. 30 işlemde win rate'in standart hatası ~%9; "
            "daha azıyla 'bu strateji kazanıyor' cümlesi kurulamaz. Tarama eşiği 20'ydi "
            "(aday elemek için); promotion daha yüksek bir kanıt seviyesi ister."
        ),
    ),
    Esik(
        ad="max_drawdown",
        alan="oos_max_drawdown",
        sinir=0.25,
        yon="<=",
        gerekce=(
            "Out-of-sample azami düşüş. Faz 4'te al-tut kıyası %25,7 düştü; bir "
            "stratejinin varlığın kendisinden daha derin düşmesi, aktif yönetimin "
            "değer katmadığının işaretidir. Monte Carlo ayrıca gösterdi ki gerçekleşen "
            "düşüş şanslı bir sıralamanın sonucu olabilir — bu yüzden eşik gerçekleşen "
            "değere değil, kıyasa dayanıyor."
        ),
    ),
    Esik(
        ad="stres_dayanikliligi",
        alan="stres_bozulma",
        sinir=0.15,
        yon="<=",
        gerekce=(
            "Temel senaryodan en kötü stres senaryosuna getiri farkı (yüzde puan). "
            "Maliyet kalibrasyonu (K-021) bir tahmindir; slippage iki katına çıkınca "
            "çöken bir strateji, kalibrasyonun doğruluğuna bahis oynamaktır."
        ),
    ),
)

#: `Sonuc.promotion_engelleri`nin ürettiği, sayısal olmayan engeller. Bunlar eşik değil,
#: mutlak kapı: `dirty` bir ağaçtan çıkan sonuç ne kadar iyi olursa olsun geçemez.
MUTLAK_ENGELLER: Final[tuple[str, ...]] = (
    "dirty",  # K-009
    "data_quality_warning",  # K-006
    "gecici_maliyet_modeli",  # K-021
    # K-049/4, K-054: eğitim kesimi öncesi dönem için üretilmiş LLM türetimi taşıyan
    # hiçbir sonuç kapıdan geçemez. Sayısal bir eşik değil çünkü ölçülebilir bir büyüklük
    # değil: sızıntı veride değil modelin ağırlıklarında ve look-ahead testi onu
    # yakalayamaz. Engel bu yüzden beyana dayanıyor ve mutlak.
    "leak_riski",
)


@dataclass(frozen=True, slots=True)
class KapiSonucu:
    """Bir stratejinin kapı değerlendirmesi."""

    strateji: str
    kapilar: dict[str, dict[str, Any]]
    mutlak_engeller: list[str]

    @property
    def gecti(self) -> bool:
        """Tüm kapılar geçildi ve mutlak engel yok mu.

        Ölçülemeyen (`None`) bir kapı geçilmiş sayılmaz: "veri yoktu" ile "kapıdan geçti"
        aynı şey değil, ve ikisini karıştırmak kapıyı sessizce kaldırmak olurdu.
        """
        return not self.mutlak_engeller and all(
            k["gecti"] is True for k in self.kapilar.values()
        )

    @property
    def kalan_kapilar(self) -> list[str]:
        return [ad for ad, k in self.kapilar.items() if k["gecti"] is not True]

    def sozluk(self) -> dict[str, Any]:
        return {
            "strateji": self.strateji,
            "gecti": self.gecti,
            "kalan_kapilar": self.kalan_kapilar,
            "mutlak_engeller": self.mutlak_engeller,
            "kapilar": self.kapilar,
        }


def degerlendir(
    strateji: str,
    olcumler: Mapping[str, Any],
    *,
    mutlak_engeller: list[str] | None = None,
) -> KapiSonucu:
    """Ölçümleri eşiklere karşı değerlendirir. (K-019)

    `olcumler` `ESIKLER`in `alan` adlarını taşıyan bir sözlük; eksik alan "ölçülemedi"
    demektir ve o kapı geçilmemiş sayılır.
    """
    kapilar: dict[str, dict[str, Any]] = {}
    for esik in ESIKLER:
        deger = olcumler.get(esik.alan)
        kapilar[esik.ad] = {
            "deger": deger,
            "sinir": esik.sinir,
            "yon": esik.yon,
            "gecti": esik.gecti_mi(deger),
        }
    return KapiSonucu(
        strateji=strateji,
        kapilar=kapilar,
        mutlak_engeller=list(mutlak_engeller or []),
    )


def esik_tablosu() -> list[dict[str, Any]]:
    """Eşiklerin gerekçeleriyle birlikte listesi — rapora ve dokümana gider."""
    return [e.sozluk() for e in ESIKLER]
