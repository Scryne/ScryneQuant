"""Canlı-backtest sapması: canlı koşu, girdileri baştan bilseydi ne olurdu? (Faz 14)

Toparlanma (`EvrenPaperMotoru.toparlan`) girdileri **bilindikleri adımda** geri yükler ve kayıtla
bit düzeyinde aynı sonucu bekler: bu, kaydın kendisiyle tutarlı olduğunu kanıtlar. Buradaki soru
başka: canlı akışın gecikmeleri (geç bar, kopma, eksik sembol, üyelik gecikmesi) sonucu ne
kadar değiştirdi?

Referans aynı motordur (K-001), tek fark her girdinin **0. adımda** bilinmesi: bütün barlar ve
üye listeleri baştan yüklenir, ısınma ve adımlar aynı ızgarada koşar. Look-ahead yok: görünüm
yine `t`de kesilir, üyelik `t`nin ayından alınır. Yani referans, aynı barlarla koşan bir
backtest'tir; canlıyla farkı yalnızca "ne zaman bilindi" farkından gelebilir. Sıfırdan farklı
her sapma bir olaya (geç bar, eksik adım, üyelik gecikmesi) bağlanabilmeli (tasarım §6/2).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from scryne_quant.common.zaman import utc_str
from scryne_quant.live.canli_evren import AyUyeligi
from scryne_quant.live.evren_depo import EvrenKosuDeposu
from scryne_quant.live.evren_motor import EvrenPaperMotoru


@dataclass(frozen=True)
class SapmaRaporu:
    adim: int
    canli_adim: int
    ilk_ayrisan_adim: int | None
    ilk_ayrisan_utc: str | None
    azami_ozkaynak_farki: float
    son_ozkaynak_farki: float
    son_ozkaynak_farki_bps: float
    canli_islem: int
    referans_islem: int
    eksikli_adim: int
    gec_bar: int
    kopma: int
    uyelik_gecikmesi: int
    gec_bilinen_bar: int
    """Bilindiği adım, açılış zamanının adımından sonra olan bar sayısı (ısınma sonrası)."""
    gec_bilinen_turev: int = 0
    """Adımından sonra bilinen premium barı ya da funding ödemesi (ısınma sonrası)."""
    makro_revizyon: int = 0
    """Sonradan farklı değerle yeniden bilinen makro gün sayısı."""

    def sozluk(self) -> dict[str, Any]:
        return asdict(self)


def sapma_olc(depo: EvrenKosuDeposu, **kurulum: Any) -> SapmaRaporu:
    kayitli = depo.adimlar()
    if not kayitli:
        raise ValueError("koşuda adım yok")
    motor = EvrenPaperMotoru(depo=None, **kurulum)
    risk = motor.backtest.risk
    if risk is not None:
        risk.defter = None  # referans koşu audit'e yazmaz

    adim_no = {a.open_time: a.adim for a in kayitli}
    isinma_sayisi = sum(1 for a in kayitli if a.isinma)
    gec_bilinen = 0
    for kb in depo.barlar():
        motor.bar_ekle(kb.sembol, kb.bar, kaydet=False, bilindi_adim=0)
        acilis_adimi = adim_no.get(kb.bar.open_time)
        if (acilis_adimi is not None and acilis_adimi >= isinma_sayisi
                and kb.bilindi_adim > acilis_adimi):
            gec_bilinen += 1
    import bisect

    zamanlar = [a.open_time for a in kayitli]
    gec_turev = 0

    def gorunur_adim(ms: int) -> int | None:
        """`ms` anında gerçekleşen girdinin ilk görülebileceği adım (açılışı ≥ ms)."""
        i = bisect.bisect_left(zamanlar, ms)
        return i if i < len(zamanlar) else None

    for sembol, t, aralik, oran, bilindi in depo.fundingler():
        motor.funding_ekle(sembol, t, aralik, oran, kaydet=False, bilindi_adim=0)
        ilk = gorunur_adim(t)
        if ilk is not None and ilk >= isinma_sayisi and bilindi > ilk:
            gec_turev += 1
    for sembol, t, close, bilindi in depo.premiumlar():
        motor.premium_ekle(sembol, t, close, kaydet=False, bilindi_adim=0)
        ilk = adim_no.get(t)
        if ilk is not None and ilk >= isinma_sayisi and bilindi > ilk:
            gec_turev += 1
    # Referans günün **son** bilinen değerini kullanır (revizyon dahil).
    makro_gunleri: dict[tuple[str, int], int] = {}
    for seri, gun, deger, _ in depo.makrolar():
        motor.makro_ekle(seri, gun, deger, kaydet=False, bilindi_adim=0)
        makro_gunleri[(seri, gun)] = makro_gunleri.get((seri, gun), 0) + 1
    for ay, semboller, h, _ in depo.uyelikler():
        motor.uyelik_ekle(AyUyeligi(ay, semboller, h), kaydet=False, bilindi_adim=0)

    referans = motor.isinma([a.open_time for a in kayitli[:isinma_sayisi]], kaydet=False)
    referans += [motor.adim(a.open_time, kaydet=False) for a in kayitli[isinma_sayisi:]]

    ilk: int | None = None
    azami = 0.0
    for canli, ref in zip(kayitli, referans, strict=True):
        fark = abs(canli.ozkaynak - ref.ozkaynak)
        azami = max(azami, fark)
        ayni = (repr(canli.ozkaynak), repr(canli.brut), canli.islem) == (
            repr(ref.ozkaynak), repr(ref.brut), ref.islem)
        if ilk is None and not ayni:
            ilk = canli.adim
    son_fark = kayitli[-1].ozkaynak - referans[-1].ozkaynak
    olaylar = [o["tur"] for o in depo.olaylar()]
    return SapmaRaporu(
        adim=len(kayitli),
        canli_adim=len(kayitli) - isinma_sayisi,
        ilk_ayrisan_adim=ilk,
        ilk_ayrisan_utc=None if ilk is None else utc_str(kayitli[ilk].open_time),
        azami_ozkaynak_farki=azami,
        son_ozkaynak_farki=son_fark,
        son_ozkaynak_farki_bps=son_fark / referans[-1].ozkaynak * 1e4,
        canli_islem=kayitli[-1].islem,
        referans_islem=referans[-1].islem,
        eksikli_adim=sum(1 for a in kayitli if a.eksik),
        gec_bar=olaylar.count("gec_bar"),
        kopma=olaylar.count("kopma"),
        uyelik_gecikmesi=olaylar.count("uyelik_gecikmesi"),
        gec_bilinen_bar=gec_bilinen,
        gec_bilinen_turev=gec_turev,
        makro_revizyon=sum(1 for n in makro_gunleri.values() if n > 1),
    )


__all__ = ["SapmaRaporu", "sapma_olc"]
