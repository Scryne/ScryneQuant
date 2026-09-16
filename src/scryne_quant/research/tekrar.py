"""Kaydından bir deneyi yeniden üretir. (Faz 4 bitti kriteri, K-009)

Kriterin metni: *"Herhangi bir deney, kaydından yeniden üretilebiliyor — kanıt: rastgele
seçilen bir deney yeniden çalıştırılıp hash'i doğrulanır."* Bu modül o "yeniden
çalıştır"ın kendisi.

**Kayıt tek doğruluk kaynağıdır.** Tekrar, kaydın `girdi` bloğundan başka hiçbir yerden
parametre okumaz — varsayılanlara düşmez, bugünkü ızgarayı kullanmaz, `config/maliyet.json`
dosyasının **bugünkü** hâline bakmaz. Bunların herhangi biri yapılsaydı deney bugünkü
ayarlarla yeniden koşturulmuş olurdu ve "aynı çıktı" iddiası kendi kendini doğrulayan bir
totoloji hâline gelirdi.

**Veri kimliği kontrol edilir.** Kayıttaki `veri_sha256` ile eldeki dosyanınki farklıysa
tekrar **reddedilir**. Aynı komutun altı ay sonra daha uzun bir veri setiyle çalışıp
farklı sonuç vermesi, yeniden üretilememenin en yaygın ve en sessiz biçimi.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from scryne_quant.common.maliyet import MaliyetModeli, SlippageKalibrasyonu
from scryne_quant.research import analiz, degerlendirme, karsilastirma, tarama, walkforward
from scryne_quant.research.bolme import Pencere, walk_forward
from scryne_quant.research.deney import DeneyHatasi
from scryne_quant.strategy.kutuphane import coz


class TekrarHatasi(DeneyHatasi):
    """Deney kaydından yeniden üretilemedi."""


#: Kaydından yeniden koşturulabilen deney tipleri. `coklu_test` **listede değil**: girdisi
#: bar verisi değil, defterin kendisi (`docs/Hipotez-Defteri.jsonl`) ve o dosya append-only
#: büyüyor — aynı seed'le bile aynı çıktıyı vermesi defterin o günkü hâline bağlı. Tipi
#: sessizce `KeyError` ile patlatmak yerine burada adıyla dışarıda bırakmak, "yeniden
#: üretilemez" ile "kodda eksik" arasındaki farkı görünür kılıyor.
TEKRAR_EDILEBILIR: frozenset[str] = frozenset(
    {"tarama", "walk_forward", "stres", "monte_carlo", "karsilastirma", "degerlendirme"}
)


def _maliyet(govde: Mapping[str, Any]) -> MaliyetModeli:
    """Kayıttaki maliyet bloğunu modele çevirir — dosyadan **okumaz**."""
    kalibrasyon = govde.get("kalibrasyon")
    return MaliyetModeli(
        fee_taker_bps=float(govde["fee_taker_bps"]),
        slippage_bps=float(govde["slippage_bps"]),
        kalibrasyon=SlippageKalibrasyonu(**kalibrasyon) if kalibrasyon else None,
    )


def _pencere(govde: Mapping[str, Any]) -> Pencere:
    return Pencere(
        ad=govde["ad"],
        baslangic=int(govde["baslangic"]),
        bitis=int(govde["bitis"]),
        isinma_baslangic=int(govde["isinma_baslangic"]),
    )


def tekrar_uret(
    kayit: Mapping[str, Any],
    bar_dizileri: Mapping[str, np.ndarray],
    veri_sha256: str,
) -> dict[str, Any]:
    """Kayıttaki deneyi yeniden koşturur ve çıktısını döndürür.

    Dönen sözlük `deney.dogrula()` ile kayıttaki `cikti_hash`e karşı karşılaştırılır.
    """
    beklenen_veri = kayit.get("kimlik", {}).get("veri_sha256")
    if beklenen_veri and veri_sha256 and beklenen_veri != veri_sha256:
        raise TekrarHatasi(
            "veri seti değişmiş: kayıt "
            f"{beklenen_veri[:16]}…, eldeki {veri_sha256[:16]}… — tekrar anlamsız (K-009)"
        )

    tip = kayit["tip"]
    girdi = kayit["girdi"]
    if tip not in TEKRAR_EDILEBILIR:
        raise TekrarHatasi(
            f"tekrar edilemeyen deney tipi: {tip!r}. Tekrar edilebilenler: "
            f"{', '.join(sorted(TEKRAR_EDILEBILIR))}"
        )
    maliyet = _maliyet(girdi["maliyet"])
    sembol, timeframe = girdi["sembol"], girdi["timeframe"]
    sermaye = float(girdi["baslangic_sermaye"])

    if tip == "tarama":
        sonuc = tarama.tara(
            coz(kayit["strateji"]),
            {a: tuple(d) for a, d in girdi["izgara"].items()},
            maliyet,
            sembol,
            timeframe,
            bar_dizileri,
            _pencere(girdi["pencere"]),
            olcut=girdi["olcut"],
            baslangic_sermaye=sermaye,
            asgari_islem=int(girdi["asgari_islem"]),
        )
        return sonuc.sozluk()

    if tip == "walk_forward":
        katmanlar = walk_forward(
            int(girdi["bar_sayisi"]),
            int(girdi["isinma"]),
            int(girdi["egitim_bar"]),
            int(girdi["test_bar"]),
            kaydirmali=bool(girdi["kaydirmali"]),
        )
        sonuc = walkforward.calistir(
            coz(kayit["strateji"]),
            {a: tuple(d) for a, d in girdi["izgara"].items()},
            maliyet,
            sembol,
            timeframe,
            bar_dizileri,
            katmanlar,
            olcut=girdi["olcut"],
            baslangic_sermaye=sermaye,
        )
        return sonuc.sozluk()

    if tip == "stres":
        sonuc = analiz.stres(
            coz(kayit["strateji"])(**girdi["parametreler"]),
            maliyet,
            sembol,
            timeframe,
            bar_dizileri,
            _pencere(girdi["pencere"]),
            baslangic_sermaye=sermaye,
        )
        return sonuc.sozluk()

    if tip == "monte_carlo":
        # Monte Carlo işlem defterinden çalışır; defteri üretmek için önce backtest.
        koşu = tarama.kosu(
            coz(kayit["strateji"])(**girdi["parametreler"]),
            maliyet,
            sembol,
            timeframe,
            bar_dizileri,
            _pencere(girdi["pencere"]),
            baslangic_sermaye=sermaye,
        )
        return analiz.monte_carlo(
            koşu.islemler,
            sermaye,
            deneme=int(girdi["deneme"]),
            seed=int(kayit["kimlik"]["seed"]),
        ).sozluk()

    if tip == "karsilastirma":
        sonuc = karsilastirma.calistir(
            maliyet,
            sembol,
            timeframe,
            bar_dizileri,
            stratejiler=tuple(girdi["stratejiler"]),
            oos_orani=float(girdi["oos_orani"]),
            olcut=girdi["olcut"],
            baslangic_sermaye=sermaye,
            veri_sha256=veri_sha256,
        )
        return sonuc.sozluk()

    if tip == "degerlendirme":
        return degerlendirme.degerlendir(
            maliyet,
            sembol,
            timeframe,
            bar_dizileri,
            stratejiler=tuple(girdi["stratejiler"]),
            oos_orani=float(girdi["oos_orani"]),
            olcut=girdi["olcut"],
            baslangic_sermaye=sermaye,
            egitim_bar=int(girdi["egitim_bar"]),
            test_bar=int(girdi["test_bar"]),
        )

    raise TekrarHatasi(f"tekrar edilemeyen deney tipi: {tip!r}")  # pragma: no cover
