"""Yürütücü: kapanmış bar → strateji → risk → execution hattı → mutabakat. (K-114, R9)

Tek sembol, tek strateji. Bar içi sıra backtest ve paper motoruyla aynı ve bu tesadüf değil
(K-001):

    1. Fill      — (paper) bekleyen emir bu barın **açılışından** dolar (K-004)
    2. Mutabakat — defter ↔ borsa; uyuşmazlıkta halt (K-038, K-046)
    3. Risk      — bu barın özkaynağı (defter+borsa ölçümlü) risk durumuna işlenir
    4. Karar     — strateji kapanmış barı görür, sinyal risk motorundan geçer
    5. Execution — onaylı niyet execution hattından emre dönüşür (ya da engellenir)
    6. Durum     — durum dosyası + kontrol noktası diske

**Bar kaynağı REST, kalite kuralı K-006.** Her döngüde son işlenen bardan sonraki kapanmış
barlar çekilir. Döngünün gördüğü **en son** kapanmış bar `AKIS` sayılır (bu veri karar anında
elimizdeydi); daha eskileri — kopukluk sonrası yakalama, ısınma — `BACKFILL`dır ve karar
üretmez (K-028). Paper'da bekleyen emirler kaçırılan barların açılışında da dolar: borsa
süreçle birlikte durmaz.

**Yeniden başlatma yeniden üretimdir** (K-038). Kalıcı durum: emir defteri
(`emirler.sqlite`), paper borsa (`paper_borsa.sqlite`), risk durumu (`risk.json`), son
işlenen bar (`yurutucu.json`), kimlik (`kosu.json`). Kimlik değiştiyse (strateji,
parametre, mod, sembol, sermaye) koşu **başlamaz** (K-009). Başlangıçta mutabakat koşar;
defter borsayla çelişirse halt.

**Duplicate emir.** Üç katman: (1) aynı niyet → aynı istemci kimliği → defter + borsa
reddi (Faz 7), (2) bar başına sembol başına tek emir (`hat.Engel.AYNI_BAR`), (3) işlenmiş
bar yeniden işlenmez (`son_islenen_ms`).
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Protocol

import numpy as np

from scryne_quant.common.hash import git_durumu
from scryne_quant.common.zaman import bar_acilisi, simdi_ms, timeframe_ms, utc_str
from scryne_quant.data.semalar import KaliteDurumu
from scryne_quant.exchange.akis import df_barlara
from scryne_quant.exchange.emir_adaptoru import BORSA_YONU
from scryne_quant.exchange.hatalar import BorsaHatasi, SaatSapmasi
from scryne_quant.exchange.paper_adaptoru import PaperBorsa
from scryne_quant.execution.hat import ExecutionHatti
from scryne_quant.execution.mod import CalismaModu
from scryne_quant.features.indikator import atr as atr_hesapla
from scryne_quant.live import durdurma
from scryne_quant.live import kill as kill_mod
from scryne_quant.live.akis import Bar, Kaynak
from scryne_quant.live.kilit import KilitAlinamadi, KosuKilidi
from scryne_quant.live.pencere import VARSAYILAN_KAPASITE, BarPenceresi
from scryne_quant.oms.emir import EmirDurumu
from scryne_quant.risk.durum import RiskDurumu
from scryne_quant.risk.motor import RISK_ATR_PENCERESI, PiyasaOlcumu, RiskMotoru
from scryne_quant.risk.niyet import OnayliNiyet
from scryne_quant.strategy.baglam import PozisyonDurumu
from scryne_quant.strategy.kosu import gorunum_kur
from scryne_quant.strategy.temel import Strateji

KIMLIK_ALANLARI: Final[tuple[str, ...]] = (
    "kosu_adi",
    "mod",
    "risk_modu",
    "strateji",
    "parametreler",
    "sembol",
    "timeframe",
    "sermaye_usdt",
)


class YurutucuHatasi(RuntimeError):
    """Yürütücü sözleşmesi ihlal edildi (kimlik değişti, mod uyuşmuyor)."""


class BarKaynagi(Protocol):
    def sunucu_zamani_ms(self) -> int: ...

    def kapanmis_barlar(
        self, sembol: str, timeframe: str, baslangic_ms: int, bitis_ms: int
    ) -> list[Bar]: ...


class RestBarKaynagi:
    """Binance public kline (`exchange/binance.BinanceAdaptoru`) — anahtarsız, salt okuma."""

    def __init__(self, adaptor: Any) -> None:
        self._a = adaptor

    def sunucu_zamani_ms(self) -> int:
        return int(self._a.sunucu_zamani_ms())

    def kapanmis_barlar(
        self, sembol: str, timeframe: str, baslangic_ms: int, bitis_ms: int
    ) -> list[Bar]:
        out: list[Bar] = []
        adim = timeframe_ms(timeframe)
        bas = baslangic_ms
        while bas < bitis_ms:
            df = self._a.klines(sembol, timeframe, bas, bitis_ms)
            parca = df_barlara(df, kaynak=Kaynak.BACKFILL)
            if not parca:
                break
            out.extend(parca)
            bas = parca[-1].open_time + adim
        return out


class ListeBarKaynagi:
    """Tekrar (replay) kaynağı: verilen barlar, saat dışarıdan ilerletilir. Test ve prova."""

    def __init__(self, barlar: Iterable[Bar], timeframe: str) -> None:
        self._barlar = sorted(barlar, key=lambda b: b.open_time)
        self._adim = timeframe_ms(timeframe)
        self.simdi = self._barlar[0].open_time if self._barlar else 0

    def sunucu_zamani_ms(self) -> int:
        return self.simdi

    def kapanmis_barlar(
        self, sembol: str, timeframe: str, baslangic_ms: int, bitis_ms: int
    ) -> list[Bar]:
        return [
            b for b in self._barlar
            if baslangic_ms <= b.open_time and b.open_time + self._adim <= min(bitis_ms, self.simdi)
        ]

    @property
    def barlar(self) -> list[Bar]:
        return list(self._barlar)


@dataclass
class YurutucuAyari:
    kosu_adi: str
    mod: CalismaModu
    risk_modu: str
    strateji: str
    parametreler: dict[str, Any]
    sembol: str
    timeframe: str
    sermaye_usdt: float
    kosu_dizini: Path

    def kimlik(self) -> dict[str, Any]:
        return {
            "kosu_adi": self.kosu_adi,
            "mod": str(self.mod),
            "risk_modu": self.risk_modu,
            "strateji": self.strateji,
            "parametreler": dict(self.parametreler),
            "sembol": self.sembol,
            "timeframe": self.timeframe,
            "sermaye_usdt": float(self.sermaye_usdt),
        }


@dataclass
class Sayac:
    bar: int = 0
    karar_bari: int = 0
    sinyal: int = 0
    risk_onay: int = 0
    risk_red: int = 0
    engellendi: int = 0
    gonderildi: int = 0
    golge: int = 0
    kural_reddi: int = 0
    borsa_reddi: int = 0
    belirsiz: int = 0
    baglanti_hatasi: int = 0
    saat_sicramasi: int = 0
    yeniden_baslatma: int = 0
    plansiz_kesinti: int = 0
    kacirilan_karar: int = 0
    """Koşu sırasında geç gelip `BACKFILL` işlenen, yani karar üretilmeyen bar (K-122).
    Bağlantı kesintisi ya da süreç duruşu bir bar kapanışını kaçırtırsa karar **sessizce**
    atlanıyordu (K-028 gereği doğru davranış: bayat barda karar verilmez); artık sayılıyor."""

    def sozluk(self) -> dict[str, int]:
        return dict(self.__dict__)


@dataclass
class Yurutucu:
    ayar: YurutucuAyari
    strateji: Strateji
    risk: RiskMotoru
    hat: ExecutionHatti
    kaynak: BarKaynagi
    paper: PaperBorsa | None = None
    saat: Callable[[], int] = simdi_ms
    kapasite: int = VARSAYILAN_KAPASITE

    sayac: Sayac = field(default_factory=Sayac)
    son_islenen_ms: int | None = None
    baslangic_ms: int = 0
    son_karar: dict[str, Any] = field(default_factory=dict)
    son_bar: dict[str, Any] = field(default_factory=dict)
    son_hata: str = ""
    islenen_tur: int = 0
    """Risk motoruna bildirilmiş kapanmış tur sayısı (K-118). Kalıcı: yeniden başlatmada aynı
    tur iki kez sayılmaz."""
    tekrar: bool = False
    """Tekrar oynatma koşusu mu (saat barlarla ilerler). Raporda `veri` alanı olarak görünür."""

    def __post_init__(self) -> None:
        a = self.ayar
        a.kosu_dizini.mkdir(parents=True, exist_ok=True)
        if self.risk.mod != a.risk_modu:
            raise YurutucuHatasi(f"risk modu {self.risk.mod} ≠ ayar {a.risk_modu}")
        if self.hat.mod is not a.mod or self.hat.sembol != a.sembol:
            raise YurutucuHatasi("hat modu/sembolü ayarla uyuşmuyor")
        if a.mod is CalismaModu.PAPER and self.paper is None:
            raise YurutucuHatasi("PAPER modu paper borsayı ister (fill açılışta)")
        if a.mod is CalismaModu.LIVE and a.risk_modu not in ("live", "pilot"):
            raise YurutucuHatasi(
                "LIVE modu yalnızca `live` (K-010) ya da `pilot` (K-115) risk moduyla koşar"
            )
        if a.risk_modu == "pilot" and self.hat.limitler.azami_kayip_usdt is None:
            raise YurutucuHatasi("`pilot` risk modu mutlak kayıp tavanı ister (K-115)")
        self._adim = timeframe_ms(a.timeframe)
        self.pencere = BarPenceresi(a.sembol, a.timeframe, kapasite=self.kapasite)
        self._kimlik_dogrula()
        self._durum_yukle()

    # ================================================================ kalıcılık

    @property
    def kosu_yolu(self) -> Path:
        """`live/kill` ve `live/durdurma` ile uyumlu önek (`kosu.pid`, `.safemode`, `.dur`)."""
        return self.ayar.kosu_dizini / "kosu"

    def _kimlik_dogrula(self) -> None:
        p = self.ayar.kosu_dizini / "kosu.json"
        yeni = self.ayar.kimlik()
        if p.is_file():
            eski = json.loads(p.read_text(encoding="utf-8"))
            farkli = [k for k in KIMLIK_ALANLARI if eski.get(k) != yeni.get(k)]
            if farkli:
                raise YurutucuHatasi(
                    f"koşu kimliği değişti ({', '.join(farkli)}); aynı koşu adıyla farklı "
                    f"kurulum başlatılamaz (K-009). Yeni koşu adı kullan."
                )
            return
        git = git_durumu()
        kayit = {**yeni, "commit": git.get("commit"), "dirty": git.get("dirty"),
                 "olusturuldu_ms": self.saat(), "limit_kimligi": self.risk.limit_kimligi}
        p.write_text(json.dumps(kayit, ensure_ascii=False, indent=1), encoding="utf-8")

    def _durum_yukle(self) -> None:
        p = self.ayar.kosu_dizini / "yurutucu.json"
        if p.is_file():
            d = json.loads(p.read_text(encoding="utf-8"))
            self.son_islenen_ms = d.get("son_islenen_ms")
            self.baslangic_ms = int(d.get("baslangic_ms", 0))
            self.sayac = Sayac(**{**Sayac().sozluk(), **d.get("sayac", {})})
            self.islenen_tur = int(d.get("islenen_tur", 0))
            self.sayac.yeniden_baslatma += 1
            if not d.get("temiz_kapanis", False):
                self.sayac.plansiz_kesinti += 1
        rp = self.ayar.kosu_dizini / "risk.json"
        if rp.is_file():
            self.risk.durum = RiskDurumu.yukle(json.loads(rp.read_text(encoding="utf-8")))
        if kill_mod.safe_isareti(self.kosu_yolu) is not None and not self.risk.durum.safe_mode:
            # Süreç dışı kill ya da hattın kendi SAFE_MODE'u: risk motoru da kilitli açılır.
            self.risk.kill("SAFE_ISARETI", self.saat())

    def _durum_kaydet(self, *, temiz_kapanis: bool = False) -> None:
        d = {
            "son_islenen_ms": self.son_islenen_ms,
            "son_islenen_utc": utc_str(self.son_islenen_ms) if self.son_islenen_ms else None,
            "baslangic_ms": self.baslangic_ms,
            "sayac": self.sayac.sozluk(),
            "islenen_tur": self.islenen_tur,
            "temiz_kapanis": temiz_kapanis,
            "yazildi_ms": self.saat(),
        }
        self._yaz("yurutucu.json", d)
        self._yaz("risk.json", self.risk.durum.sozluk())

    def _hata_kaydet(self, tur: str, mesaj: str) -> None:
        """`hatalar.jsonl`: zamanlı, append-only hata günlüğü (K-122). Sayaç kaç kez olduğunu,
        günlük **ne zaman** olduğunu söyler; kesintinin bir döneme mi yığıldığı buradan okunur."""
        simdi = self.saat()
        satir = {"zaman_ms": simdi, "zaman_utc": utc_str(simdi), "tur": tur, "mesaj": mesaj[:500]}
        with (self.ayar.kosu_dizini / "hatalar.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(satir, ensure_ascii=False) + "\n")

    def _yaz(self, ad: str, veri: dict[str, Any]) -> None:
        p = self.ayar.kosu_dizini / ad
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(veri, ensure_ascii=False, indent=1, default=str),
                       encoding="utf-8")
        tmp.replace(p)

    # ================================================================ başlatma

    def baslat(self) -> dict[str, Any]:
        """Isınma penceresi + başlangıç mutabakatı. Karar üretmez."""
        simdi = self.kaynak.sunucu_zamani_ms()
        if not self.baslangic_ms:
            self.baslangic_ms = simdi
        son_kapali = bar_acilisi(simdi, self.ayar.timeframe) - self._adim
        bas = son_kapali - (self.kapasite - 1) * self._adim
        tarih = self.kaynak.kapanmis_barlar(self.ayar.sembol, self.ayar.timeframe, bas, simdi)
        sinir = self.son_islenen_ms if self.son_islenen_ms is not None else son_kapali
        for b in tarih:
            if b.open_time <= sinir:
                self.pencere.ekle(_backfill(b))
        if self.son_islenen_ms is None:
            self.son_islenen_ms = self.pencere.son_ms
        if self.paper is not None and self.pencere.son is not None:
            son = self.pencere.son
            try:
                self.paper.son_fiyat(self.ayar.sembol)
            except BorsaHatasi:
                self.paper.fiyat_bildir(self.ayar.sembol, son.close, son.open_time + self._adim)
        sonuc = self.hat.baslat()
        self._durum_kaydet()
        self.hat.durum_yaz(ek=self._ek())
        return {"isinma_bar": len(self.pencere), "son_islenen_ms": self.son_islenen_ms, **sonuc}

    # ================================================================ döngü

    def adim(self) -> list[dict[str, Any]]:
        """Bir döngü: yeni kapanmış barları sırayla işler. İşlenen barların özetini döner."""
        try:
            simdi = self.kaynak.sunucu_zamani_ms()
            bas = (self.son_islenen_ms or 0) + self._adim
            yeni = [
                b for b in self.kaynak.kapanmis_barlar(
                    self.ayar.sembol, self.ayar.timeframe, bas, simdi
                )
                if self.son_islenen_ms is None or b.open_time > self.son_islenen_ms
            ]
        except BorsaHatasi as hata:
            self.sayac.baglanti_hatasi += 1
            self.son_hata = f"bar kaynağı: {hata}"
            self._hata_kaydet("bar_kaynagi", str(hata))
            self.hat.durum_yaz(ek=self._ek())
            return []
        en_son_kapali = bar_acilisi(simdi, self.ayar.timeframe) - self._adim
        ozetler = []
        for b in yeni:
            canli = b.open_time == en_son_kapali
            if not canli:
                self.sayac.kacirilan_karar += 1
                self._hata_kaydet("kacirilan_karar", f"bar {utc_str(b.open_time)} geç geldi")
            ozetler.append(self._bar_isle(canli_bar(b) if canli else _backfill(b), canli=canli))
            # Her bardan sonra: çökme penceresi tek bara iner (aynı bar yeniden işlenirse
            # `Engel.AYNI_BAR` ve paper'ın `transactTime` kuralı ikinci emri/erken fill'i keser).
            self._durum_kaydet()
        self.hat.durum_yaz(ek=self._ek())
        return ozetler

    def _bar_isle(self, bar: Bar, *, canli: bool) -> dict[str, Any]:
        a = self.ayar
        # 1) Fill (paper): bekleyen emir bu barın açılışında dolar; sonra kapanış fiyatı.
        if self.paper is not None:
            self.paper.bar_acilisi(a.sembol, bar.open, bar.open_time)
            self.paper.fiyat_bildir(a.sembol, bar.close, bar.open_time + self._adim)

        # 2) Mutabakat.
        try:
            self.hat.mutabakat_yap()
        except SaatSapmasi as hata:
            self.sayac.saat_sicramasi += 1
            self.son_hata = str(hata)

        # 2b) Kapanan turlar risk motoruna (ardışık kayıp → cooldown, K-118).
        self._turlari_isle()

        self.pencere.ekle(bar)
        self.sayac.bar += 1
        self.son_islenen_ms = bar.open_time
        self.son_bar = {**bar.sozluk(), "kaynak": str(bar.kaynak), "canli": canli}

        # 3) Risk durumu (karardan önce).
        try:
            h = self.hat.hesap(fiyat=bar.close)
        except BorsaHatasi as hata:
            self.sayac.baglanti_hatasi += 1
            self.son_hata = f"hesap: {hata}"
            self._hata_kaydet("hesap", str(hata))
            return {"bar_ms": bar.open_time, "karar": None, "hata": self.son_hata}
        self.risk.bar_isle(bar.open_time, h.ozkaynak)
        self.hat.ozkaynak_isle(h.ozkaynak, bar.open_time + self._adim)

        # 4-5) Karar + execution.
        karar = self._karar(bar, canli=canli, ozkaynak=h.ozkaynak, maruziyet=h.maruziyet,
                            miktar=h.miktar)
        return {"bar_ms": bar.open_time, "canli": canli, "ozkaynak": h.ozkaynak, **karar}

    def _karar(
        self, bar: Bar, *, canli: bool, ozkaynak: float, maruziyet: float, miktar: float
    ) -> dict[str, Any]:
        diziler = self.pencere.diziler()
        i = len(self.pencere) - 1
        ok = str(diziler["quality_status"][i]) == str(KaliteDurumu.OK)
        if not canli or not ok or len(self.pencere) < max(2, self.strateji.isinma_bar()):
            return {"karar": None}
        self.sayac.karar_bari += 1
        gorunum = gorunum_kur(self.ayar.sembol, self.ayar.timeframe, diziler, self.strateji)
        maliyet, giris = self._ortalama_maliyet()
        ctx = gorunum.baglam(
            i,
            PozisyonDurumu(
                miktar=max(miktar, 0.0),
                ortalama_maliyet=maliyet,
                exposure=maruziyet,
                giris_ms=giris,
            ),
        )
        sinyal = self.strateji.on_bar(ctx)
        if sinyal is None:
            return {"karar": "sinyal_yok"}
        self.sayac.sinyal += 1
        olcum = PiyasaOlcumu(
            fiyat=bar.close,
            ozkaynak=ozkaynak,
            mevcut_maruziyet=maruziyet,
            bar_ms=bar.open_time,
            atr=self._atr(diziler, i),
        )
        karar = self.risk.degerlendir(sinyal, olcum)
        self.son_karar = {
            "bar_ms": bar.open_time,
            "bar_utc": utc_str(bar.open_time),
            "sinyal": {"yon": str(sinyal.side), "hedef": sinyal.target_exposure,
                       "sebep": sinyal.reason},
        }
        if not isinstance(karar, OnayliNiyet):
            self.sayac.risk_red += 1
            self.son_karar["risk"] = {"karar": "red", "sebep": str(karar.sebep)}
            return {"karar": "risk_red", "sebep": str(karar.sebep)}
        self.sayac.risk_onay += 1
        self.son_karar["risk"] = {"karar": "onay", "onayli_maruziyet": karar.onayli_maruziyet,
                                  "kisitlayan": list(karar.kisitlayan)}
        # Bayatlık **gönderim anında** ölçülür (K-114 denetimi): karar barı, borsanın şimdiki
        # saatine göre son kapanmış bar değilse (işlem bir sonraki bar kapanışını aştıysa)
        # artıran emir gitmez. Saat okunamazsa bayat sayılır (fail closed).
        try:
            simdi = self.kaynak.sunucu_zamani_ms()
            son_kapali = bar_acilisi(simdi, self.ayar.timeframe) - self._adim
        except BorsaHatasi:
            son_kapali = -1
        u = self.hat.uygula(karar, son_kapali_bar_ms=son_kapali)
        self.son_karar["execution"] = u.sozluk()
        alan = {
            "gonderildi": "gonderildi", "golge": "golge", "kural_reddi": "kural_reddi",
            "borsa_reddi": "borsa_reddi", "belirsiz": "belirsiz", "engellendi": "engellendi",
        }.get(u.sonuc)
        if alan:
            setattr(self.sayac, alan, getattr(self.sayac, alan) + 1)
        return {"karar": "onay", "execution": u.sonuc, "engel": u.engel}

    def _turlari_isle(self) -> None:
        """Defterde yeni kapanan turları `RiskMotoru.islem_kapandi`ye bildirir. (K-118)

        Backtest bunu `backtest/defter.py`de yapıyordu; execution yolunda hiç yapılmıyordu ve
        `config/risk.json`'daki ardışık kayıp → cooldown limiti paper/testnet/canlıda **hiç**
        devreye girmiyordu. Kurallar okunamazsa bu bar atlanır, sonraki barda yeniden denenir
        (sayaç ilerlemez; kayıp tur atlanmaz).
        """
        try:
            kurallar = self.hat.adaptor.sembol_kurallari(self.ayar.sembol)
        except BorsaHatasi as hata:
            self.son_hata = f"kurallar: {hata}"
            return
        turlar = kapanan_turlar(
            self.hat.defter.tumu(), self.ayar.sembol, min_notional=kurallar.min_notional,
            taban=kurallar.taban_varlik, kote=kurallar.kote_varlik,
        )
        for zaman_ms, net_pnl in turlar[self.islenen_tur:]:
            self.risk.islem_kapandi(net_pnl, zaman_ms)
        self.islenen_tur = max(self.islenen_tur, len(turlar))

    def _atr(self, diziler: dict[str, np.ndarray], i: int) -> float | None:
        """Risk motorunun kendi ATR'si (`live/motor._olcum` ile aynı kural: kısa pencere → None)."""
        if len(diziler["close"]) < RISK_ATR_PENCERESI + 1:
            return None
        deger = float(
            atr_hesapla(diziler["high"], diziler["low"], diziler["close"], RISK_ATR_PENCERESI)[i]
        )
        return None if np.isnan(deger) else deger

    def _ortalama_maliyet(self) -> tuple[float, int | None]:
        """Açık pozisyonun komisyon dahil ortalama maliyeti ve ilk giriş zamanı (defterden)."""
        miktar = maliyet = 0.0
        giris: int | None = None
        emirler = sorted(
            (e for e in self.hat.defter.tumu() if e.sembol == self.ayar.sembol and e.dolan_miktar),
            key=lambda e: (e.karar_ms, e.olusturuldu_ms),
        )
        for e in emirler:
            if e.yon.upper() == "BUY":
                if miktar <= 1e-12:
                    giris, maliyet = e.karar_ms, 0.0
                maliyet += e.dolan_miktar * e.ortalama_fiyat + sum(m for _, m in e.komisyon)
                miktar += e.dolan_miktar
            else:
                if miktar > 0:
                    maliyet *= max(0.0, 1.0 - e.dolan_miktar / miktar)
                miktar = max(0.0, miktar - e.dolan_miktar)
                if miktar <= 1e-12:
                    giris, maliyet = None, 0.0
        return (maliyet / miktar if miktar > 1e-12 else 0.0), giris

    # ================================================================ çalıştırma

    def calistir(
        self,
        *,
        bekleme_s: float = 20.0,
        azami_sure_s: float | None = None,
        durdur: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        """Gerçek zamanlı döngü. `kosu.dur` bayrağı, `azami_sure_s` ya da `durdur()` ile biter."""
        kilitler = self.kilitle()
        kill_mod.pid_yaz(self.kosu_yolu)
        bitis = None if azami_sure_s is None else time.monotonic() + azami_sure_s
        try:
            self.baslat()
            while True:
                self.adim()
                if durdurma.istek(self.kosu_yolu) is not None:
                    break
                if durdur is not None and durdur():
                    break
                if bitis is not None and time.monotonic() >= bitis:
                    break
                time.sleep(bekleme_s)
            return self.kapat()
        finally:
            durdurma.temizle(self.kosu_yolu)
            kill_mod.pid_sil(self.kosu_yolu)
            for k in kilitler:
                k.kapat()

    def kilitle(self) -> list[KosuKilidi]:
        """Tek süreç kilidi; LIVE'da ayrıca **tek canlı koşu** kilidi (K-114 denetimi).

        Aynı koşuyu iki süreçle sürmek defteri çiftler; iki **ayrı** canlı koşu ise her biri
        kademe sermayesiyle sınırlı olduğu hâlde toplam maruziyeti kademenin katına çıkarır —
        kademe tavanının (K-050/3) ikinci bir süreçle delinmesi. İkinci süreç kilidi alamaz ve
        başlamaz.
        """
        kilitler = [KosuKilidi(self.kosu_yolu).al()]
        if self.ayar.mod is CalismaModu.LIVE:
            try:
                kilitler.append(KosuKilidi(self.ayar.kosu_dizini.parent / "canli").al())
            except KilitAlinamadi:
                kilitler[0].kapat()
                raise
        return kilitler

    def tekrar_oynat(self, kaynak: ListeBarKaynagi, *, isinma: int) -> dict[str, Any]:
        """Tekrar kaynağında: ilk `isinma` bar ısınma, kalanlar birer birer 'canlı' gelir."""
        barlar = kaynak.barlar
        if len(barlar) <= isinma:
            raise YurutucuHatasi("tekrar için ısınmadan fazla bar gerekir")
        self.tekrar = True
        kilitler = self.kilitle()
        try:
            kaynak.simdi = barlar[isinma - 1].open_time + self._adim
            self.baslat()
            for b in barlar[isinma:]:
                kaynak.simdi = b.open_time + self._adim
                self.adim()
            return self.kapat()
        finally:
            for k in kilitler:
                k.kapat()

    def kapat(self) -> dict[str, Any]:
        """Kapanış mutabakatı + rapor (`rapor.json`). Açık emir iptal edilmez, raporlanır."""
        sonuc = self.hat.kapat()
        self._durum_kaydet(temiz_kapanis=True)
        durum = self.hat.durum_yaz(ek=self._ek())
        rapor = self.rapor(durum, sonuc)
        self._yaz("rapor.json", rapor)
        # Raporun hash'i koşunun zincirli audit defterine yazılır (K-114 denetimi): live gate
        # kanıtı rapor dosyasına değil, audit'e bağlı hash'e bakar — elle düzenlenmiş bir
        # rapor.json kanıt sayılmaz.
        import hashlib

        sha = hashlib.sha256((self.ayar.kosu_dizini / "rapor.json").read_bytes()).hexdigest()
        self.hat._olay("rapor", {"rapor_sha256": sha, "gecti": rapor["gecti"]})
        return rapor

    # ================================================================ rapor

    def _ek(self) -> dict[str, Any]:
        simdi = self.saat()
        son = self.son_islenen_ms
        return {
            "kosu": self.ayar.kimlik(),
            "sayac": self.sayac.sozluk(),
            "son_bar": self.son_bar,
            "veri_tazeligi": {
                "son_bar_ms": son,
                "son_bar_utc": utc_str(son) if son else None,
                "kapanistan_beri_ms": (simdi - (son + self._adim)) if son else None,
                "beklenen_son_bar_ms": bar_acilisi(simdi, self.ayar.timeframe) - self._adim,
            },
            "son_karar": self.son_karar,
            "risk": {
                "mod": self.risk.mod,
                "durum": self.risk.durum.sozluk(),
                "red_sayimi": {k: v for k, v in self.risk.red_sayimi.items() if v},
                "limit_kimligi": self.risk.limit_kimligi,
            },
            "son_hata": self.son_hata,
        }

    def rapor(self, durum: dict[str, Any], kapanis: dict[str, Any]) -> dict[str, Any]:
        """Koşu raporu ve `gecti` hükmü. Kural mod başına; hiçbiri eşik icat etmez."""
        s = self.sayac
        sayim = (durum.get("emirler") or {}).get("sayim", {})
        dolan = sayim.get(str(EmirDurumu.FILLED), 0)
        golge = sayim.get(str(EmirDurumu.GOLGE), 0)
        gonderilmis = sum(
            n for d, n in sayim.items()
            if d not in (str(EmirDurumu.GOLGE), str(EmirDurumu.CREATED), str(EmirDurumu.VALIDATED))
            and d != str(EmirDurumu.REJECTED)
        )
        poz = durum.get("pozisyon_mutabakati") or {}
        pozisyon_farki = 1 if poz.get("halt") or not poz else 0
        kalan: list[str] = []
        if s.bar == 0:
            kalan.append("hiç bar işlenmedi")
        if durum.get("halt"):
            kalan.append(f"halt: {durum['halt']}")
        if pozisyon_farki:
            kalan.append("pozisyon mutabakatı temiz değil ya da ölçülemedi")
        if int((durum.get("emirler") or {}).get("belirsiz", 0)):
            kalan.append("çözülmemiş UNKNOWN emir")
        mod = self.ayar.mod
        if mod is CalismaModu.SHADOW:
            if golge == 0:
                kalan.append("GOLGE kaydı yok (shadow uçtan uca sınanmadı)")
            if gonderilmis:
                kalan.append(f"shadow'da gönderilmiş emir var: {gonderilmis} (OLMAMALI)")
        elif mod in (CalismaModu.PAPER, CalismaModu.TESTNET, CalismaModu.LIVE) and dolan == 0:
            kalan.append("dolan emir yok (emir→fill→mutabakat sınanmadı)")
        sure_gun = (
            max(0.0, (self.saat() - self.baslangic_ms) / 86_400_000) if self.baslangic_ms else 0.0
        )
        return {
            "kosu": self.ayar.kimlik(),
            "mod": str(mod),
            "strateji": self.ayar.strateji,
            "risk_modu": self.ayar.risk_modu,
            "veri": "tekrar" if self.tekrar else "canli",
            "duvar_saati_bitis_utc": utc_str(simdi_ms()),
            "baslangic_ms": self.baslangic_ms,
            "bitis_ms": self.saat(),
            "bitis_utc": utc_str(self.saat()),
            "sure_gun": round(sure_gun, 4),
            "sayac": s.sozluk(),
            "emir_sayimi": sayim,
            "dolan_emir": dolan,
            "golge_sayisi": golge,
            "kapanista_acik_emir": int((durum.get("emirler") or {}).get("acik", 0)),
            "kural_reddi": s.kural_reddi,
            "pozisyon_farki": pozisyon_farki,
            "saat_sicramasi": s.saat_sicramasi,
            "aciklanamaz_kesinti": s.plansiz_kesinti,
            "hesap": durum.get("hesap"),
            "kapanis_mutabakati": kapanis,
            "gecti": not kalan,
            "kalan": kalan,
            "not": (
                "Execution altyapı ölçümü. `risk_modu` gozlem ise kanıt üretmez (K-035); "
                "strateji başarısı ölçülmez."
            ),
        }


def kapanan_turlar(
    emirler: Iterable[Any], sembol: str, *, min_notional: float, taban: str, kote: str
) -> list[tuple[int, float]]:
    """Dolan emirlerden kapanmış turlar: `(kapanış zamanı ms, net PnL kote)`. (K-118)

    Tur, pozisyonun (taban varlık) minNotional'ın altına inen satışla kapanır: spot'ta taban
    varlıkla ödenen komisyon yüzünden satıştan sonra adım altı bir kırıntı kalır ve pozisyon
    tam sıfıra inmez. Net PnL = turun nakit akışı (kote komisyonlar dahil) + kapanışta kalan
    kırıntının değeri − turun başındaki kırıntının değeri. Taban varlıkla ödenen komisyon
    miktarı azaltır; nakitten ayrıca düşülmez (çift sayılmasın). Sıra: `(karar_ms,
    olusturuldu_ms)` — `_ortalama_maliyet` ile aynı.
    """
    dolanlar = sorted(
        (e for e in emirler if e.sembol == sembol and e.dolan_miktar > 0.0),
        key=lambda e: (e.karar_ms, e.olusturuldu_ms),
    )
    out: list[tuple[int, float]] = []
    miktar = 0.0
    nakit = 0.0
    acik = False
    for e in dolanlar:
        fiyat = float(e.ortalama_fiyat)
        alis = BORSA_YONU.get(e.yon.upper()) == "BUY"
        if alis and not acik:
            acik, nakit = True, -miktar * fiyat  # önceki kırıntı turun maliyetine girer
        q = float(e.dolan_miktar)
        miktar += q if alis else -q
        nakit += -q * fiyat if alis else q * fiyat
        for varlik, m in e.komisyon:
            if varlik == kote:
                nakit -= m
            elif varlik == taban:
                miktar -= m
        if acik and not alis and miktar * fiyat < min_notional:
            zaman = int(e.guncellendi_ms or e.olusturuldu_ms or e.karar_ms)
            out.append((zaman, nakit + max(miktar, 0.0) * fiyat))
            acik, nakit = False, 0.0
    return out


def _backfill(b: Bar) -> Bar:
    if b.kaynak is Kaynak.BACKFILL:
        return b
    return Bar(**{**{k: getattr(b, k) for k in b.__dataclass_fields__}, "kaynak": Kaynak.BACKFILL})


def canli_bar(b: Bar) -> Bar:
    """Tekrar kaynağının barını `AKIS` olarak işaretler (yalnızca yürütücü karar verir)."""
    return Bar(**{**{k: getattr(b, k) for k in b.__dataclass_fields__}, "kaynak": Kaynak.AKIS})


__all__ = [
    "BarKaynagi",
    "ListeBarKaynagi",
    "RestBarKaynagi",
    "Sayac",
    "Yurutucu",
    "YurutucuAyari",
    "YurutucuHatasi",
    "canli_bar",
    "kapanan_turlar",
]
