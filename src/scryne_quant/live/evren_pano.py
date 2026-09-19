"""Gözlem panosu: dört koşunun tamamını gösteren **salt okunur** görüntüleyici. (Faz 14)

Neden ayrı bir süreç ve ayrı bir port: `live/api.py` panosunu koşunun **kendi süreci**
servis ediyor ve yalnızca o koşuyu tanıyor — tek sembollü `host-1`. İşlemlerin çoğu ise
evren koşularında ve onların hiçbir arayüzü yoktu. Panoyu koşunun içine eklemek, arayüzü
değiştirmek için koşuyu yeniden başlatmak demekti; dayanıklılık penceresi (K-069) açıkken
bu, ölçümü silmek olurdu.

**Değişmezler — bu modül bir okuyucudur:**

1. Koşu dosyalarına **yazmaz**. Her okuma `anlik_kopya` ile alınmış geçici bir kopyadan
   yapılır (günlük yedeğin ve sapma ölçümünün zaten kullandığı yol); canlı WAL dosyası
   doğrudan açılmaz.
2. Hiçbir uç nokta durum değiştirmez. Emir, durdurma, parametre yazma yoktur — sunucu
   yalnızca `GET` tanır.
3. Yeniden üretim, koşunun kendi audit defterine yazmaz (`risk.defter = None`), tıpkı
   sapma ölçümündeki gibi: gölge koşu gerçek koşunun kaydını kirletemez.
4. Ağır iş isteği bloke etmez. Yeniden üretim arka planda koşar, sonucu önbelleğe girer;
   hazır değilse arayüz "hesaplanıyor" görür. O(N²) maliyeti pencere uzadıkça büyüyor
   (tasarım §6c), yani her istekte yeniden üretmek panoyu kullanılamaz yapardı.

**Neyi gösteriyor, neyi göstermiyor:** gösterdiği her sayı koşunun kendi kaydından ya da
o kayıttan yeniden üretilen durumdan gelir. Pano hiçbir şey tahmin etmez; bir sayı
ölçülemiyorsa `null` döner ve arayüz "—" gösterir (K-024'ün ruhu: bilinmeyen sıfır değildir).
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import time
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from scryne_quant.common.zaman import simdi_ms, utc_str
from scryne_quant.live.evren_kurulum import (
    KurulumUyusmazligi,
    anlik_kopya,
    evren_kurulum_kimlikten,
)

#: Koşu listesi ve özkaynak serisi bu kadar saniye önbellekte tutulur. Bar periyodu 1 saat;
#: 20 saniye "ekran eskimesin" için fazlasıyla sık, ama her isteğin anlık kopya almasını da
#: engelliyor (kopya ≈6 MB'lık bir dosyanın okunması).
ONBELLEK_S: float = 20.0

#: Özkaynak serisi arayüze en fazla bu kadar nokta gönderir. 8 günlük koşu ≈192 nokta;
#: tavan 30 günlük koşuda (720) grafiği değil, aktarımı sınırlar. Seyreltme **eşit aralıklı**
#: ve son nokta her zaman korunur: grafiğin sağ ucu gerçek son değerdir.
AZAMI_NOKTA: int = 1500

UretimDurumu = Literal["yok", "hesaplaniyor", "hazir", "hata"]


@dataclass
class Uretim:
    """Bir koşunun yeniden üretilmiş durumu: pozisyonlar ve işlem turları."""

    durum: UretimDurumu = "yok"
    adim: int | None = None
    """Hangi adım sayısında üretildi. Koşu ilerlediğinde bu sayı durumdan geri kalır."""
    olculdu_ms: int | None = None
    sure_s: float | None = None
    ozkaynak: float | None = None
    pozisyonlar: list[dict[str, Any]] = field(default_factory=list)
    islemler: list[dict[str, Any]] = field(default_factory=list)
    hata: str | None = None

    def sozluk(self) -> dict[str, Any]:
        return {
            "durum": self.durum,
            "adim": self.adim,
            "olculdu_ms": self.olculdu_ms,
            "olculdu_utc": None if self.olculdu_ms is None else utc_str(self.olculdu_ms),
            "sure_s": self.sure_s,
            "ozkaynak": self.ozkaynak,
            "pozisyonlar": self.pozisyonlar,
            "islemler": self.islemler,
            "hata": self.hata,
        }


class PanoKaynagi:
    """Koşu dosyalarını salt okunur okuyan veri kaynağı.

    Kopyalar `gecici_kok` altında açılıp okuma biter bitmez silinir; tek bir koşunun
    kopyası ≈6-9 MB ve diskte kalıcı iz bırakmaz.
    """

    def __init__(
        self,
        paper_kok: Path = Path("runs/paper"),
        izleme_kok: Path = Path("runs/izleme"),
        *,
        jev_kok: Path = Path("runs/jev"),
        onbellek_s: float = ONBELLEK_S,
        saat: Any = simdi_ms,
    ) -> None:
        self.paper_kok = Path(paper_kok)
        self.izleme_kok = Path(izleme_kok)
        self.jev_kok = Path(jev_kok)
        self.onbellek_s = onbellek_s
        self.saat = saat
        self._onbellek: dict[str, tuple[float, Any]] = {}
        self._uretimler: dict[str, Uretim] = {}
        self._kilit = threading.Lock()
        self._calisan: set[str] = set()

    # ------------------------------------------------------------------ keşif

    def kosu_yollari(self) -> list[Path]:
        """Koşu dosyaları, adına göre sıralı. `-wal`/`-shm` yardımcıları glob'a girmez."""
        if not self.paper_kok.is_dir():
            return []
        return sorted(p for p in self.paper_kok.glob("*.sqlite") if p.is_file())

    def durum_json(self, ad: str) -> dict[str, Any] | None:
        """Koşucunun her adımda yazdığı durum dosyası. Anlık kopya gerektirmez."""
        yol = self.paper_kok / f"{ad}.sqlite.durum.json"
        if not yol.is_file():
            return None
        try:
            return json.loads(yol.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def izleme(self) -> dict[str, Any]:
        """`sq izle kontrol`ün son yazdığı durum; süreç canlılığı buradan gelir.

        **`yazildi_ms` dosyanın kendisinde yok**, mtime'ından türetiliyor — `live/api.py`
        ile aynı kaynak, aynı anlam. Türetmeyi atlayan ilk sürüm alanı `None` bırakıyordu
        ve arayüz bunu "izleme bayat" diye okuyup kırmızı şerit basıyordu: kontrol
        dakikası dakikasına çalışırken. **Sahte alarm, alarmsızlıktan kötüdür** — bakanı
        kırmızıyı yok saymaya alıştırır.
        """
        yol = self.izleme_kok / "durum.json"
        if not yol.is_file():
            return {"var": False, "simdi_ms": self.saat()}
        try:
            govde = json.loads(yol.read_text(encoding="utf-8"))
            yazildi_ms = int(yol.stat().st_mtime * 1000)
        except (OSError, ValueError):
            return {"var": False, "simdi_ms": self.saat()}
        govde["var"] = True
        govde["simdi_ms"] = self.saat()
        govde["yazildi_ms"] = yazildi_ms
        for kosu in govde.get("kosular", []):
            if not isinstance(kosu, dict):
                continue
            sapma = self.paper_kok / f"{kosu.get('kosu')}.sapma.jsonl"
            if sapma.is_file():
                try:
                    satirlar = sapma.read_text(encoding="utf-8").strip().splitlines()
                except OSError:
                    continue
                if satirlar:
                    with suppress(ValueError):
                        kosu["sapma"] = json.loads(satirlar[-1])
        return govde

    # ------------------------------------------------------- anlık kopya okuma

    def _kopyadan(self, ad: str, oku: Any) -> Any:
        """Koşunun anlık kopyasını alır, `oku(baglanti)` sonucunu döndürür, kopyayı siler."""
        kaynak = self.paper_kok / f"{ad}.sqlite"
        if not kaynak.is_file():
            raise FileNotFoundError(f"koşu yok: {kaynak}")
        with tempfile.TemporaryDirectory(prefix="sq-pano-") as g:
            kopya = Path(g) / "kopya.sqlite"
            anlik_kopya(kaynak, kopya)
            baglanti = sqlite3.connect(f"file:{kopya.as_posix()}?mode=ro", uri=True)
            try:
                return oku(baglanti)
            finally:
                baglanti.close()

    def _onbellekli(self, anahtar: str, uret: Any) -> Any:
        simdi = time.monotonic()
        girdi = self._onbellek.get(anahtar)
        if girdi is not None and simdi - girdi[0] < self.onbellek_s:
            return girdi[1]
        deger = uret()
        self._onbellek[anahtar] = (simdi, deger)
        return deger

    @staticmethod
    def _tablolar(baglanti: sqlite3.Connection) -> set[str]:
        return {a for (a,) in baglanti.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    # ------------------------------------------------------------------ liste

    def kosular(self) -> dict[str, Any]:
        """Bütün koşuların tek satırlık özeti. Pano açılışının tek kaynağı."""
        izleme = self.izleme()
        yasayan = {
            k.get("kosu"): k.get("surec_yasiyor")
            for k in (izleme.get("kosular") or [])
            if isinstance(k, dict)
        }
        satirlar = []
        for yol in self.kosu_yollari():
            ad = yol.name[: -len(".sqlite")]
            satirlar.append(self._satir(ad, yasayan.get(ad)))
        return {
            "zaman_ms": self.saat(),
            "kosular": satirlar,
            "izleme": {
                "var": izleme.get("var", False),
                "yazildi_ms": izleme.get("yazildi_ms"),
                "alarm_sayisi": len(izleme.get("alarmlar") or []),
                "alarmlar": izleme.get("alarmlar") or [],
                "sistem": izleme.get("sistem"),
            },
        }

    def durum_ozeti(self, ad: str) -> dict[str, Any] | None:
        """Koşunun son durumu. Önce koşucunun yazdığı `durum.json`, yoksa koşu dosyası.

        Tek sembollü koşu (`host-1`) `durum.json` **yazmıyor** — durumu kendi tablosunda
        tutuyor. Yedek yol olmasaydı pano o koşunun satırını boş gösterir, yani ekran
        "veri yok" ile "koşu durmuş"u aynı şekilde çizerdi.
        """
        json_durum = self.durum_json(ad)
        if json_durum is not None:
            return json_durum
        return self._onbellekli(f"durum:{ad}", lambda: self._durum_db(ad))

    def _durum_db(self, ad: str) -> dict[str, Any] | None:
        def oku(b: sqlite3.Connection) -> dict[str, Any] | None:
            tablolar = self._tablolar(b)
            if "adim" in tablolar and "uyelik" in tablolar:
                satir = b.execute(
                    "SELECT adim, open_time, ozkaynak, brut, islem FROM adim "
                    "ORDER BY adim DESC LIMIT 1"
                ).fetchone()
                if satir is None:
                    return None
                return {
                    "adim": satir[0],
                    "son_bar_utc": utc_str(satir[1]),
                    "ozkaynak": float(satir[2]),
                    "brut_maruziyet": float(satir[3]),
                    "islem": satir[4],
                    "pozisyonlar": None,
                }
            satir = b.execute(
                "SELECT son_bar_ms, portfoy, risk, guncellendi_ms FROM durum WHERE id = 1"
            ).fetchone()
            if satir is None:
                return None
            portfoy = json.loads(satir[1]) if satir[1] else {}
            risk = json.loads(satir[2]) if satir[2] else {}
            miktar = float(portfoy.get("miktar") or 0.0)
            fill_sayisi = b.execute("SELECT COUNT(*) FROM fill").fetchone()[0]
            son_fill = b.execute(
                "SELECT ozkaynak_sonra FROM fill ORDER BY id DESC LIMIT 1"
            ).fetchone()
            return {
                "adim": None,
                "son_bar_utc": None if satir[0] is None else utc_str(satir[0]),
                # Tek sembollü koşuda son özkaynak yalnızca fill anlarında kaydediliyor;
                # aradaki bar değerlemesi diske yazılmıyor. Yaklaşık değil, **eski** bir
                # sayı: öyle etiketleniyor.
                "ozkaynak": None if son_fill is None else float(son_fill[0]),
                "ozkaynak_kaynagi": "son_fill",
                "brut_maruziyet": None,
                "islem": fill_sayisi,
                "pozisyonlar": None,
                "safe_mode": (risk.get("durum") or {}).get("safe_mode"),
                "miktar": miktar,
                "yazildi_utc": utc_str(satir[3]),
            }

        try:
            return self._kopyadan(ad, oku)
        except (FileNotFoundError, sqlite3.Error, ValueError):
            return None

    def _satir(self, ad: str, surec_yasiyor: bool | None) -> dict[str, Any]:
        kimlik = self._onbellekli(f"kimlik:{ad}", lambda: self._kimlik_oku(ad))
        durum = self.durum_ozeti(ad)
        sermaye = kimlik.get("baslangic_sermaye")
        ozkaynak = None if durum is None else durum.get("ozkaynak")
        getiri = None if ozkaynak is None or not sermaye else ozkaynak / float(sermaye) - 1.0
        uretim = self._uretimler.get(ad)
        return {
            "ad": ad,
            "tur": kimlik.get("tur", "bilinmiyor"),
            "strateji": kimlik.get("strateji_adi"),
            "parametreler": kimlik.get("parametreler") or {},
            "mod": kimlik.get("mod", "gozlem"),
            "sembol": kimlik.get("sembol"),
            "baslangic_sermaye": sermaye,
            "surec_yasiyor": surec_yasiyor,
            "adim": None if durum is None else durum.get("adim"),
            "son_bar_utc": None if durum is None else durum.get("son_bar_utc"),
            "ozkaynak": ozkaynak,
            "getiri": getiri,
            "brut": None if durum is None else durum.get("brut_maruziyet"),
            "islem": None if durum is None else durum.get("islem"),
            "pozisyon_sayisi": None if durum is None else len(durum.get("pozisyonlar") or []),
            "pozisyonlar": None if durum is None else durum.get("pozisyonlar"),
            "safe_mode": None if durum is None else durum.get("safe_mode"),
            "ozkaynak_kaynagi": None if durum is None else durum.get("ozkaynak_kaynagi"),
            "yazildi_utc": None if durum is None else durum.get("yazildi_utc"),
            "uretim_durumu": "yok" if uretim is None else uretim.durum,
        }

    def _kimlik_oku(self, ad: str) -> dict[str, Any]:
        """Koşu kimliği; evren ve tek sembollü şemanın ortak paydası."""

        def oku(b: sqlite3.Connection) -> dict[str, Any]:
            tablolar = self._tablolar(b)
            if "adim" in tablolar and "uyelik" in tablolar:
                satir = b.execute("SELECT kimlik FROM kosu WHERE id = 1").fetchone()
                kimlik = json.loads(satir[0]) if satir else {}
                st = kimlik.get("strateji") or {}
                return {
                    "tur": "evren",
                    "kimlik": kimlik,
                    "strateji_adi": st.get("ad"),
                    "parametreler": st.get("parametreler") or {},
                    "mod": kimlik.get("mod", "gozlem"),
                    "sembol": None,
                    "baslangic_sermaye": kimlik.get("baslangic_sermaye"),
                }
            satir = b.execute(
                "SELECT kosu_adi, mod, sembol, timeframe, strateji, baslangic_sermaye "
                "FROM kosu WHERE id = 1"
            ).fetchone()
            if satir is None:
                return {"tur": "bilinmiyor"}
            st = json.loads(satir[4])
            return {
                "tur": "tek",
                "strateji_adi": st.get("ad"),
                "parametreler": st.get("parametreler") or {},
                "mod": satir[1],
                "sembol": satir[2],
                "timeframe": satir[3],
                "baslangic_sermaye": satir[5],
            }

        try:
            return self._kopyadan(ad, oku)
        except (FileNotFoundError, sqlite3.Error, ValueError) as e:
            return {"tur": "bilinmiyor", "hata": str(e)}

    # ----------------------------------------------------------------- detay

    def detay(self, ad: str) -> dict[str, Any]:
        """Tek koşunun sayfası: kimlik, özkaynak serisi, olaylar, işlem defteri."""
        kimlik = self._onbellekli(f"kimlik:{ad}", lambda: self._kimlik_oku(ad))
        tur = kimlik.get("tur")
        if tur == "evren":
            govde = self._onbellekli(f"evren:{ad}", lambda: self._evren_detay(ad))
        elif tur == "tek":
            govde = self._onbellekli(f"tek:{ad}", lambda: self._tek_detay(ad))
        else:
            govde = {"seri": [], "olaylar": [], "islemler": []}
        satir = self._satir(ad, None)
        uretim = self._uretimler.get(ad) or Uretim()
        return {
            "ad": ad,
            "tur": tur,
            "kimlik": kimlik,
            "ozet": satir,
            "uretim": uretim.sozluk(),
            **govde,
        }

    def _evren_detay(self, ad: str) -> dict[str, Any]:
        def oku(b: sqlite3.Connection) -> dict[str, Any]:
            adimlar = b.execute(
                "SELECT adim, open_time, isinma, ozkaynak, brut, islem, eksik "
                "FROM adim WHERE isinma = 0 ORDER BY adim"
            ).fetchall()
            seri = [
                {
                    "adim": a,
                    "ms": t,
                    "ozkaynak": float(o),
                    "brut": float(br),
                    "islem": isl,
                    "eksik": len(json.loads(e) or []) if e else 0,
                }
                for a, t, _i, o, br, isl, e in adimlar
            ]
            olaylar = [
                {
                    "tur": t,
                    "zaman_ms": z,
                    "zaman_utc": utc_str(z),
                    "bar_ms": bm,
                    "ayrinti": json.loads(ay) if ay else {},
                }
                for t, z, bm, ay in b.execute(
                    "SELECT tur, zaman_ms, bar_ms, ayrinti FROM olay ORDER BY id"
                )
            ]
            uyelik = [
                {"ay": ay, "sembol_sayisi": len(json.loads(s) or [])}
                for ay, s in b.execute("SELECT ay, semboller FROM uyelik ORDER BY ay")
            ]
            isinma_sayisi = b.execute("SELECT COUNT(*) FROM adim WHERE isinma = 1").fetchone()[0]
            return {
                "seri": _seyrelt(seri, AZAMI_NOKTA),
                "seri_nokta": len(seri),
                "olaylar": olaylar,
                "uyelik": uyelik,
                "isinma_adim": isinma_sayisi,
            }

        try:
            return self._kopyadan(ad, oku)
        except (FileNotFoundError, sqlite3.Error, ValueError) as e:
            return {"seri": [], "olaylar": [], "uyelik": [], "hata": str(e)}

    def _tek_detay(self, ad: str) -> dict[str, Any]:
        """Tek sembollü koşu: fill defteri doğrudan tabloda, yeniden üretim gerekmez."""

        def oku(b: sqlite3.Connection) -> dict[str, Any]:
            filller = [
                {
                    "id": i,
                    "zaman_ms": z,
                    "zaman_utc": utc_str(z),
                    "yon": yon,
                    "miktar": mik,
                    "fiyat": f,
                    "referans_fiyat": rf,
                    "komisyon": k,
                    "ozkaynak_sonra": oz,
                    "gerceklesen_pnl": pnl,
                }
                for i, z, yon, mik, f, rf, k, oz, pnl in b.execute(
                    "SELECT id, zaman_ms, yon, miktar, fiyat, referans_fiyat, komisyon, "
                    "ozkaynak_sonra, gerceklesen_pnl FROM fill ORDER BY id"
                )
            ]
            seri = [{"ms": f["zaman_ms"], "ozkaynak": f["ozkaynak_sonra"]} for f in filller]
            olaylar = [
                {
                    "tur": t,
                    "zaman_ms": z,
                    "zaman_utc": utc_str(z),
                    "bar_ms": bm,
                    "ayrinti": json.loads(ay) if ay else {},
                }
                for t, z, bm, ay in b.execute(
                    "SELECT tur, zaman_ms, bar_ms, ayrinti FROM olay ORDER BY id"
                )
            ]
            return {"seri": seri, "seri_nokta": len(seri), "filller": filller, "olaylar": olaylar}

        try:
            return self._kopyadan(ad, oku)
        except (FileNotFoundError, sqlite3.Error, ValueError) as e:
            return {"seri": [], "filller": [], "olaylar": [], "hata": str(e)}

    # ------------------------------------------------------- yeniden üretim

    def uretim(self, ad: str, *, tetikle: bool = True) -> Uretim:
        """Pozisyon ve işlem defteri. Hazır değilse arka planda üretimi başlatır.

        İstek asla beklemez: pencere uzadıkça yeniden üretim dakikalara çıkıyor
        (tasarım §6c'nin O(N²) ölçümü) ve bir HTTP isteğini o kadar bekletmek panoyu
        çalışmıyor gibi gösterirdi.
        """
        mevcut = self._uretimler.get(ad) or Uretim()
        durum = self.durum_ozeti(ad)
        guncel_adim = None if durum is None else durum.get("adim")
        if tetikle and (mevcut.durum in ("yok", "hata") or mevcut.adim != guncel_adim):
            self._tetikle(ad)
            # Tetikledikten **sonra** oku: ilk istek "yok" yerine "hesaplanıyor" görsün.
            # Aksi hâlde arayüz ilk açılışta hiç başlamamış gibi görünürdü.
            return self._uretimler.get(ad) or mevcut
        return mevcut

    def _tetikle(self, ad: str) -> None:
        with self._kilit:
            if ad in self._calisan:
                return
            self._calisan.add(ad)
            mevcut = self._uretimler.get(ad)
            if mevcut is None or mevcut.durum != "hazir":
                self._uretimler[ad] = Uretim(durum="hesaplaniyor")
        threading.Thread(target=self._uret, args=(ad,), daemon=True).start()

    def _uret(self, ad: str) -> None:
        basladi = time.perf_counter()
        try:
            sonuc = self._yeniden_uret(ad)
            sonuc.sure_s = round(time.perf_counter() - basladi, 2)
            sonuc.olculdu_ms = self.saat()
            with self._kilit:
                self._uretimler[ad] = sonuc
        except Exception as e:  # pano bir okuyucudur: hata ekranda görünür, süreci düşürmez
            with self._kilit:
                self._uretimler[ad] = Uretim(
                    durum="hata", hata=f"{type(e).__name__}: {e}", olculdu_ms=self.saat()
                )
        finally:
            with self._kilit:
                self._calisan.discard(ad)

    def _yeniden_uret(self, ad: str) -> Uretim:
        """Koşuyu anlık kopyadan baştan üretir ve portföyü okur. Canlı dosyaya dokunmaz."""
        from scryne_quant.live.evren_depo import EvrenKosuDeposu
        from scryne_quant.live.evren_motor import EvrenPaperMotoru

        kaynak = self.paper_kok / f"{ad}.sqlite"
        with tempfile.TemporaryDirectory(prefix="sq-pano-uretim-") as g:
            kopya = Path(g) / "kopya.sqlite"
            anlik_kopya(kaynak, kopya)
            depo = EvrenKosuDeposu(kopya)
            try:
                kimlik = depo.kimlik_oku() or {}
                try:
                    kurulum = evren_kurulum_kimlikten(kimlik)
                except KurulumUyusmazligi as e:
                    return Uretim(durum="hata", hata=str(e))
                risk = kurulum.get("risk")
                if risk is not None:
                    # Gölge koşu gerçek koşunun audit defterine yazamaz (sapma ölçümüyle
                    # aynı kural).
                    risk.defter = None
                motor = EvrenPaperMotoru.toparlan(depo, **kurulum)
                return self._portfoyden(motor)
            finally:
                depo.kapat()

    @staticmethod
    def _portfoyden(motor: Any) -> Uretim:
        adimci = motor.adimci
        fiyat = dict(adimci.son_kapanis)
        portfoy = adimci.portfoy
        ozkaynak = motor.son_sonuc.ozkaynak if motor.son_sonuc is not None else None

        pozisyonlar = []
        for sembol in portfoy.sirali_semboller:
            p = portfoy.pozisyon(sembol)
            son = fiyat.get(sembol)
            deger = None if son is None else p.miktar * son
            maliyet = p.miktar * p.ortalama_maliyet
            pozisyonlar.append(
                {
                    "sembol": sembol,
                    "miktar": p.miktar,
                    "ortalama_maliyet": p.ortalama_maliyet,
                    "son_fiyat": son,
                    "deger": deger,
                    "maliyet": maliyet,
                    "agirlik": None if deger is None or not ozkaynak else deger / ozkaynak,
                    "gerceklesmemis_pnl": None if deger is None else deger - maliyet,
                    "getiri": None if deger is None or maliyet <= 0.0 else deger / maliyet - 1.0,
                    "giris_ms": p.giris_ms,
                    "giris_utc": None if p.giris_ms is None else utc_str(p.giris_ms),
                }
            )

        # `adimci.islemler` defterin **tamamı**: bir tur açılışta buraya ekleniyor
        # (`backtest/defter.py`), `adimci.acik` ise aynı nesnelere bakan bir görünüm.
        # İkisini birleştirmek her açık turu iki kez listelerdi.
        islemler = [
            {
                **i.sozluk(sembol_yaz=True),
                "acik": i.kapanis_ms is None,
                "acilis_utc": utc_str(i.acilis_ms),
                "kapanis_utc": None if i.kapanis_ms is None else utc_str(i.kapanis_ms),
            }
            for i in adimci.islemler
        ]
        islemler.sort(key=lambda i: (i["acilis_ms"], i.get("sembol") or ""))

        return Uretim(
            durum="hazir",
            adim=motor.adim_sayisi,
            ozkaynak=ozkaynak,
            pozisyonlar=pozisyonlar,
            islemler=islemler,
        )

    # ------------------------------------------------------------ Jev gölge (K-074)
    #
    # Pano `scryne_quant.jev`i **import etmez** (bağımlılık yönü tek, `test_jev_izolasyon.py`).
    # Okuduğu şey Jev sürecinin her barda yazdığı `<kosu>.sqlite.durum.json` ve defterin
    # salt okunur SQL'i. Bu ekranda görünen hiçbir sayı isabet ya da kâr iddiası değildir;
    # `kanit: false` alanı ve arayüzdeki şerit bunu söyler.

    def jev_yollari(self) -> list[Path]:
        if not self.jev_kok.is_dir():
            return []
        return sorted(p for p in self.jev_kok.glob("*.sqlite") if p.is_file())

    def _jev_durum_json(self, ad: str) -> dict[str, Any] | None:
        yol = self.jev_kok / f"{ad}.sqlite.durum.json"
        if not yol.is_file():
            return None
        try:
            govde = json.loads(yol.read_text(encoding="utf-8"))
            govde["dosya_yazildi_ms"] = int(yol.stat().st_mtime * 1000)
            return govde
        except (OSError, ValueError):
            return None

    def _jev_surec(self, ad: str) -> tuple[int | None, bool | None]:
        from scryne_quant.live import kill as kill_mod

        pid = kill_mod.pid_oku(self.jev_kok / f"{ad}.sqlite")
        if pid is None:
            return None, None
        return pid, bool(kill_mod.surec_yasiyor_mu(pid))

    def _jev_db(self, ad: str, oku: Any) -> Any:
        """Jev defterini salt okunur açar (WAL; yazan süreç engellenmez)."""
        yol = self.jev_kok / f"{ad}.sqlite"
        baglanti = sqlite3.connect(f"file:{yol.as_posix()}?mode=ro", uri=True)
        baglanti.row_factory = sqlite3.Row
        try:
            return oku(baglanti)
        finally:
            baglanti.close()

    def jev_kosular(self) -> dict[str, Any]:
        """Bütün Jev gölge koşularının tek satırlık özeti."""
        satirlar = []
        for yol in self.jev_yollari():
            ad = yol.name[: -len(".sqlite")]
            d = self._jev_durum_json(ad) or {}
            pid, yasiyor = self._jev_surec(ad)
            if not d:
                # durum.json yoksa (ör. yalnızca replay defteri) kimlik ve sayım SQL'den
                d = self._onbellekli(f"jev-ozet:{ad}", lambda ad=ad: self._jev_ozet_db(ad))
            satirlar.append(
                {
                    "ad": ad,
                    "mod": d.get("mod"),
                    "model": d.get("model"),
                    "sembol": d.get("sembol"),
                    "pid": pid,
                    "surec_yasiyor": yasiyor,
                    "toplam": d.get("toplam"),
                    "gecerli": d.get("gecerli"),
                    "hata": d.get("hata"),
                    "sayim": d.get("sayim") or {},
                    "cekimserlik_orani": d.get("cekimserlik_orani"),
                    "yon_dagilimi": d.get("yon_dagilimi") or {},
                    "gecikme_ms": d.get("gecikme_ms") or {"p50": None, "p95": None},
                    "son_karar": d.get("son_karar"),
                    "son_bar_ms": d.get("son_bar_ms"),
                    "zincir_gecerli": d.get("zincir_gecerli"),
                    "yazildi_ms": d.get("dosya_yazildi_ms"),
                    "kanit": False,
                }
            )
        return {
            "zaman_ms": self.saat(),
            "kosular": satirlar,
            "not": "Gölge ölçümü: sinyal, risk, emir yok. İsabet/kâr iddiası değildir (K-074).",
        }

    def _jev_ozet_db(self, ad: str) -> dict[str, Any]:
        def oku(b: sqlite3.Connection) -> dict[str, Any]:
            tablolar = self._tablolar(b)
            if "kosu" not in tablolar or "karar" not in tablolar:
                return {}
            kosu = b.execute("SELECT govde FROM kosu WHERE tek = 1").fetchone()
            kimlik = json.loads(kosu["govde"]) if kosu else {}
            sayim = {
                str(r["durum_kodu"]): int(r["n"])
                for r in b.execute(
                    "SELECT durum_kodu, COUNT(*) AS n FROM karar GROUP BY durum_kodu"
                )
            }
            son = b.execute("SELECT karar_ms FROM karar ORDER BY id DESC LIMIT 1").fetchone()
            toplam = sum(sayim.values())
            yon: dict[str, int] = {}
            for r in b.execute("SELECT karar_json FROM karar WHERE durum_kodu = 'gecerli'"):
                y = json.loads(r["karar_json"]).get("yon")
                if y is not None:
                    yon[str(y)] = yon.get(str(y), 0) + 1
            gecerli = sayim.get("gecerli", 0)
            return {
                "yon_dagilimi": dict(sorted(yon.items())),
                "cekimserlik_orani": None if not gecerli else yon.get("flat", 0) / gecerli,
                "mod": kimlik.get("mod"),
                "model": (kimlik.get("ayarlar") or {}).get("model"),
                "sembol": kimlik.get("sembol"),
                "toplam": toplam,
                "gecerli": sayim.get("gecerli", 0),
                "hata": toplam - sayim.get("gecerli", 0),
                "sayim": sayim,
                "son_bar_ms": None if son is None else int(son["karar_ms"]),
            }

        try:
            return self._jev_db(ad, oku)
        except sqlite3.Error:
            return {}

    def jev_detay(self, ad: str, *, son: int = 200) -> dict[str, Any]:
        """Tek gölge koşusu: kimlik, son kararlar, olaylar. Salt okunur SQL."""
        durum = self._jev_durum_json(ad)
        pid, yasiyor = self._jev_surec(ad)

        def oku(b: sqlite3.Connection) -> dict[str, Any]:
            tablolar = self._tablolar(b)
            kosu = (
                b.execute("SELECT govde FROM kosu WHERE tek = 1").fetchone()
                if "kosu" in tablolar
                else None
            )
            kararlar = []
            if "karar" in tablolar:
                for r in b.execute(
                    "SELECT karar_ms, uretim_ms, durum_kodu, karar_json FROM karar "
                    "ORDER BY id DESC LIMIT ?",
                    (son,),
                ):
                    k = json.loads(r["karar_json"])
                    kararlar.append(
                        {
                            "karar_ms": int(r["karar_ms"]),
                            "karar_utc": utc_str(int(r["karar_ms"])),
                            "uretim_ms": int(r["uretim_ms"]),
                            "durum": str(r["durum_kodu"]),
                            "yon": k.get("yon"),
                            "yon_olasiliklari": k.get("yon_olasiliklari"),
                            "yon_guven": k.get("yon_guven"),
                            "rejim": k.get("rejim"),
                            "kurulum_skor": k.get("kurulum_skor"),
                            "cekimser": k.get("cekimser"),
                            "gecikme_ms": k.get("gecikme_ms"),
                            "ileriye_donuk": k.get("ileriye_donuk"),
                            "leak_riski": k.get("leak_riski"),
                            "durum_hash": k.get("durum_hash"),
                            "hata": k.get("hata"),
                        }
                    )
            olaylar = []
            if "olay" in tablolar:
                for r in b.execute(
                    "SELECT tur, zaman_ms, ayrinti FROM olay ORDER BY id DESC LIMIT 50"
                ):
                    olaylar.append(
                        {
                            "tur": str(r["tur"]),
                            "zaman_ms": int(r["zaman_ms"]),
                            "zaman_utc": utc_str(int(r["zaman_ms"])),
                            "ayrinti": json.loads(r["ayrinti"]),
                        }
                    )
            return {
                "kimlik": json.loads(kosu["govde"]) if kosu else {},
                "kararlar": list(reversed(kararlar)),
                "olaylar": list(reversed(olaylar)),
            }

        govde = self._jev_db(ad, oku)
        return {
            "ad": ad,
            "zaman_ms": self.saat(),
            "pid": pid,
            "surec_yasiyor": yasiyor,
            "durum": durum,
            "kanit": False,
            **govde,
        }

    # ------------------------------------------------------------ servis sağlığı

    def servisler(self) -> dict[str, Any]:
        """Tek ekranın üst şeridi: hangi süreç yaşıyor, izleme taze mi, pano ayakta mı."""
        kosular = self.kosular()
        jev = self.jev_kosular()
        izleme = kosular["izleme"]
        simdi = self.saat()
        satirlar: list[dict[str, Any]] = []
        for k in kosular["kosular"]:
            strateji = k.get("strateji") or "—"
            satirlar.append(
                {
                    "ad": k["ad"],
                    "tur": "paper",
                    "aciklama": f"{strateji} · {k.get('mod') or 'gozlem'} · gerçek emir yok",
                    "yasiyor": k.get("surec_yasiyor"),
                    "son_ms": None,
                    "son_utc": k.get("son_bar_utc"),
                    "ayrinti": {"safe_mode": k.get("safe_mode"), "adim": k.get("adim")},
                }
            )
        for j in jev["kosular"]:
            son_ms = j.get("son_bar_ms")
            satirlar.append(
                {
                    "ad": j["ad"],
                    "tur": "jev",
                    "aciklama": f"Jev gölge · {j.get('model') or '—'} · ölçüm, emir yok",
                    "yasiyor": j.get("surec_yasiyor"),
                    "son_ms": son_ms,
                    "son_utc": None if son_ms is None else utc_str(int(son_ms)),
                    "ayrinti": {"gecerli": j.get("gecerli"), "hata": j.get("hata")},
                }
            )
        yazildi = izleme.get("yazildi_ms")
        satirlar.append(
            {
                "ad": "izleme",
                "tur": "izleme",
                "aciklama": "sq izle kontrol · 15 dk · alarm + runbook",
                "yasiyor": None
                if not izleme.get("var") or yazildi is None
                else (simdi - int(yazildi)) <= 35 * 60_000,
                "son_ms": yazildi,
                "son_utc": None if yazildi is None else utc_str(int(yazildi)),
                "ayrinti": {"alarm_sayisi": izleme.get("alarm_sayisi", 0)},
            }
        )
        satirlar.append(
            {
                "ad": "pano",
                "tur": "pano",
                "aciklama": "salt okunur gözlem panosu (bu süreç)",
                "yasiyor": True,
                "son_ms": simdi,
                "son_utc": utc_str(simdi),
                "ayrinti": {},
            }
        )
        return {
            "zaman_ms": simdi,
            "servisler": satirlar,
            "ozet": {
                "toplam": len(satirlar),
                "yasayan": sum(1 for x in satirlar if x["yasiyor"] is True),
                "duran": sum(1 for x in satirlar if x["yasiyor"] is False),
                "bilinmeyen": sum(1 for x in satirlar if x["yasiyor"] is None),
            },
            "gercek_emir": False,
        }


def _seyrelt(seri: list[dict[str, Any]], azami: int) -> list[dict[str, Any]]:
    """Eşit aralıklı seyreltme; **son nokta her zaman korunur.**

    Son noktayı düşürmek grafiğin sağ ucunu geçmişte bırakırdı: ekranda görünen "şu anki
    özkaynak" gerçek olmayan bir sayı olurdu.
    """
    if len(seri) <= azami or azami < 2:
        return seri
    adim = (len(seri) - 1) / (azami - 1)
    secilen = [seri[int(round(i * adim))] for i in range(azami - 1)]
    secilen.append(seri[-1])
    return secilen


def pano_kur(
    kaynak: PanoKaynagi | None = None,
    *,
    web_kok: Path | None = None,
    indeks: str = "pano.html",
    paper_kok: Path = Path("runs/paper"),
    izleme_kok: Path = Path("runs/izleme"),
    jev_kok: Path = Path("runs/jev"),
) -> Any:
    """Salt okunur pano uygulaması. Yalnızca `GET` uçları tanımlıdır."""
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse

    kay = kaynak if kaynak is not None else PanoKaynagi(paper_kok, izleme_kok, jev_kok=jev_kok)
    app = FastAPI(
        title="ScryneQuant — Gözlem panosu",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.kaynak = kay

    @app.get("/api/kosular")
    async def kosular() -> dict[str, Any]:
        """Bütün koşuların tek satırlık özeti."""
        return kay.kosular()

    @app.get("/api/kosu/{ad}")
    async def kosu(ad: str) -> dict[str, Any]:
        """Tek koşunun sayfası: kimlik, özkaynak serisi, olaylar, üyelik."""
        if not (kay.paper_kok / f"{ad}.sqlite").is_file():
            raise HTTPException(status_code=404, detail=f"koşu yok: {ad}")
        return kay.detay(ad)

    @app.get("/api/kosu/{ad}/uretim")
    async def uretim(ad: str) -> dict[str, Any]:
        """Pozisyonlar ve işlem defteri (yeniden üretimden). Hazır değilse tetikler."""
        if not (kay.paper_kok / f"{ad}.sqlite").is_file():
            raise HTTPException(status_code=404, detail=f"koşu yok: {ad}")
        return kay.uretim(ad).sozluk()

    @app.get("/api/izleme")
    async def izleme() -> dict[str, Any]:
        """`sq izle kontrol`ün son durumu: dört boyut, alarmlar, sistem."""
        return kay.izleme()

    @app.get("/api/servisler")
    async def servisler() -> dict[str, Any]:
        """Tek ekran sağlık şeridi: paper koşuları, Jev gölgesi, izleme, pano."""
        return kay.servisler()

    @app.get("/api/jev")
    async def jev_kosular() -> dict[str, Any]:
        """Jev gölge koşuları (K-074): ölçüm; sinyal, risk, emir yok."""
        return kay.jev_kosular()

    @app.get("/api/jev/{ad}")
    async def jev_kosu(ad: str) -> dict[str, Any]:
        """Tek gölge koşusu: son kararlar ve olaylar."""
        if not (kay.jev_kok / f"{ad}.sqlite").is_file():
            raise HTTPException(status_code=404, detail=f"gölge koşusu yok: {ad}")
        return kay.jev_detay(ad)

    if web_kok is not None:
        kok = web_kok.resolve()

        @app.get("/{yol:path}")
        async def spa(yol: str) -> FileResponse:
            if yol.startswith("api/"):
                raise HTTPException(status_code=404, detail="bilinmeyen uç")
            hedef = (kok / yol).resolve()
            if yol and hedef.is_file() and hedef.is_relative_to(kok):
                return FileResponse(hedef)
            # Aynı build iki giriş taşıyor; pano süreci `pano.html`i kök sayar.
            sayfa = kok / indeks
            if not sayfa.is_file():
                raise HTTPException(status_code=404, detail=f"SPA build yok: {indeks}")
            return FileResponse(sayfa)

    return app


__all__ = ["AZAMI_NOKTA", "ONBELLEK_S", "PanoKaynagi", "Uretim", "pano_kur"]
