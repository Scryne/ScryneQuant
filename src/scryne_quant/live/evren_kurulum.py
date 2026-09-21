"""Koşu kimliğinden motor kurulumu ve çalışan koşunun anlık kopyası. (Faz 14)

`cli/main.py`de doğmuştu; salt okunur pano (`live/evren_pano.py`) da aynı kurulumu
kurmak zorunda olduğu için buraya taşındı. İki kopya olsaydı, panonun ürettiği pozisyon
listesi koşunun kendi yeniden üretiminden **sessizce** ayrışabilirdi — bu projede en
tehlikeli hata sınıfı tam olarak budur.

Sözleşme değişmedi: kurulum bugünkü konfigürasyonla bire bir tutmak zorunda; tutmazsa
kurulmaz. Yanlış konfigürasyonla yapılan yeniden üretim kanıt değildir (K-038).
"""

from __future__ import annotations

import inspect
import json
import sqlite3
from pathlib import Path
from typing import Any

from scryne_quant.common import maliyet as maliyet_mod
from scryne_quant.risk import limitler as limit_mod
from scryne_quant.risk.motor import RiskMotoru
from scryne_quant.strategy.kutuphane import EVREN_AILELER, EVREN_KIYAS


def anlik_kopya(kaynak: Path, hedef: Path) -> None:
    """Çalışan koşunun dosyasına **dokunmadan** tutarlı kopya (SQLite online backup).

    Kaynak `mode=ro` ile açılır: okuyucu koşuyu bloke etmez, koşu okuyucuyu bozamaz. Faz
    14'ün günlük yedeği ve sapma ölçümü aynı yolu kullanıyor; salt okunur pano da bunu
    kullanır, çünkü canlı WAL dosyasını doğrudan okumak koşuyla yarışa girmek olurdu.
    """
    hedef.parent.mkdir(parents=True, exist_ok=True)
    k = sqlite3.connect(f"file:{kaynak.as_posix()}?mode=ro", uri=True)
    h = sqlite3.connect(hedef)
    try:
        k.backup(h)
    finally:
        k.close()
        h.close()


class KurulumUyusmazligi(ValueError):
    """Koşu kimliği bugünkü konfigürasyonla uyuşmuyor ya da strateji tanınmıyor."""


def evren_kurulum_kimlikten(kimlik: dict[str, Any]) -> dict[str, Any]:
    """Evren koşusunun motor kurulumu, koşu kimliğinden.

    Strateji, maliyet ve limit kimliği bugünkü konfigürasyonla karşılaştırılır; biri bile
    tutmazsa `KurulumUyusmazligi` yükselir.
    """
    st = kimlik.get("strateji", {})
    kutuphane = {**EVREN_KIYAS, **EVREN_AILELER}
    if st.get("ad") not in kutuphane:
        raise KurulumUyusmazligi(f"koşu kimliğinde bilinmeyen strateji: {st.get('ad')}")
    sinif = kutuphane[st["ad"]]
    imza = inspect.signature(sinif).parameters
    strateji = sinif(**{k: v for k, v in st["parametreler"].items() if k in imza})
    # K-084/U14: tek model katalogdan (`global` → config/maliyet.json); kayıtta `maliyetler`
    # bloğu varsa her kimlik katalogdan **yeniden** çözülür ve gövdesi kayıtla karşılaştırılır.
    # Eksik/bozuk dosya `MaliyetHatasi` → kurulum yok (fail closed, sessiz global düşüşü yok).
    # Çözümleme hatası da kurulum uyuşmazlığıdır (çağıranlar tek tipi yakalıyor); sebep zincirde.
    katalog = maliyet_mod.MaliyetKatalogu()
    try:
        maliyet = katalog.coz(maliyet_mod.GLOBAL_KIMLIK, binance_spot_kripto=True)
        maliyetler = None
        if kimlik.get("maliyetler") is not None:
            kayitli = maliyet_mod.maliyetler_govdeden(kimlik["maliyetler"])
            maliyetler = {
                sembol: maliyet_mod.SembolMaliyeti(
                    em.kimlik,
                    katalog.coz(
                        em.kimlik, binance_spot_kripto=em.kimlik == maliyet_mod.GLOBAL_KIMLIK
                    ),
                )
                for sembol, em in kayitli.items()
            }
    except maliyet_mod.MaliyetHatasi as hata:
        raise KurulumUyusmazligi(f"maliyet modeli çözümlenemedi: {hata}") from hata
    limitler = limit_mod.yukle()
    uyusmayan = [
        ad
        for ad, beklenen, gercek in (
            ("strateji", st, strateji.sozluk()),
            ("maliyet", kimlik.get("maliyet"), maliyet.sozluk()),
            (
                "maliyetler",
                kimlik.get("maliyetler"),
                None if maliyetler is None else maliyet_mod.maliyetler_govdesi(maliyetler),
            ),
            ("limit_kimligi", kimlik.get("limit_kimligi"), limitler.kimlik()),
        )
        if json.loads(json.dumps(gercek)) != beklenen
    ]
    if uyusmayan:
        raise KurulumUyusmazligi(
            f"bugünkü konfigürasyon koşu kimliğiyle uyuşmuyor: {', '.join(uyusmayan)}"
        )
    return {
        "strateji": strateji,
        "maliyet": maliyet,
        "baslangic_sermaye": float(kimlik["baslangic_sermaye"]),
        "risk": RiskMotoru(limitler, "1h", mod="gozlem"),
        "timeframe": kimlik.get("timeframe", "1h"),
        "sifira_yaz_bar": kimlik.get("sifira_yaz_bar"),
        "turev": bool(kimlik.get("turev", False)),
        "makro": tuple(kimlik.get("makro", ())),
        # Yalnız çok modelde: tek modelli koşunun kurulum sözlüğü eskisiyle aynı anahtarları taşır.
        **({"maliyetler": maliyetler} if maliyetler is not None else {}),
    }


__all__ = ["KurulumUyusmazligi", "anlik_kopya", "evren_kurulum_kimlikten"]
