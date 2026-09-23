"""B-3 bağımsız doğrulama verisi: French veri kütüphanesi, ABD 12 sektör + piyasa, günlük. (K-127)

**Neden bu veri (K-125 §5, K-127 §3).** Kripto OOS'una 18 çekiliş baktı; RYPP PASS için aynı donmuş
kuralın OOS'una bu projede hiç bakılmamış bir veride de raporlanması zorunlu. Seçim ölçütleri sonuca
bakılmadan yazıldı: (1) farklı varlık sınıfı ve piyasa (kripto evreniyle ortak enstrüman yok), (2)
ücretsiz ve otomasyona açık (K-124: Scryne abonelik istemiyor), (3) uzun ve CRSP tabanlı (hayatta
kalma yanlılığı yok), (4) projede tek kullanımı K-124'ün IS ölçümü, **1952-07 → 2004-05**; o
ölçümün OOS'u olarak ayrılan 2004-06 → sonrası hiçbir çekilişte, hiçbir ölçümde kullanılmadı.

**Kimlik ve kilit.** Doğrulama penceresi, kaynak dosyalar (ham zip ve içindeki CSV'nin SHA-256'sı),
şema ve kanonik veri hash'i `config/bagimsiz_veri.json`da **dondurulmuştur**. `yukle()` her okumada
hepsini yeniden hesaplar; biri tutmazsa `FrenchHatasi` (fail closed). French kütüphanesi her ay CRSP
güncellemesiyle **yeniden üretilir** ve geçmiş değerler revize olur (bkz. `revizyon_olc`); yeni
indirilen dosya farklı bir vintage'dır, sessizce yerine konmaz: yeni vintage, yeni pencere ya da
yeni şema yeni bir K ve yeni bir doğrulama döngüsü ister.

**Kanonik temsil.** Pencere içindeki satırlar, kaynaktaki **ondalık metinleriyle** (kayan noktaya
çevrilmeden) `tarih,NoDur,…,Other,Mkt-RF,RF` biçiminde, LF satır sonuyla UTF-8 yazılır; hash budur.
Böylece kimlik ayrıştırıcının float davranışına, pandas/pyarrow sürümüne bağlı değildir; tek bir
değer değişirse hash değişir.

**Zaman sözleşmesi (K-005).** Satır `tarih`i o işlem gününün getirisidir; `zaman_ms` günün UTC
00:00'ı (bar açılışı). Getiri gün **kapanışında** bilinir: t gününün getirisine bakan karar en
erken t+1'de dolar (K-004). Veri yalnız getiri taşır, fiyat barı yoktur.

**Bu modülün yapmadığı:** strateji koşmak, getiri istatistiği hesaplamak. Doğrulama yalnız bir
RYPP adayı donduktan sonra ve bir kez yapılır (K-125 §5.3).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd

KAYNAK_KOK: Final = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
SEKTOR_ZIP: Final = "12_Industry_Portfolios_Daily_CSV.zip"
FAKTOR_ZIP: Final = "F-F_Research_Data_Factors_daily_CSV.zip"

SEKTORLER: Final[tuple[str, ...]] = (
    "NoDur", "Durbl", "Manuf", "Enrgy", "Chems", "BusEq",
    "Telcm", "Utils", "Shops", "Hlth", "Money", "Other",
)
FAKTORLER: Final[tuple[str, ...]] = ("Mkt-RF", "SMB", "HML", "RF")
#: Kanonik tablo: 12 sektörün değer ağırlıklı getirisi + piyasa fazlası + risksiz faiz (yüzde).
KANONIK_SUTUNLAR: Final[tuple[str, ...]] = ("tarih", *SEKTORLER, "Mkt-RF", "RF")
VW_BOLUMU: Final = "Average Value Weighted Returns -- Daily"
#: Kaynağın eksik değer kodları (dosya başlığında yazılı).
EKSIK_KODLARI: Final[frozenset[str]] = frozenset({"-99.99", "-999"})
_ONDALIK: Final = re.compile(r"^-?\d+(\.\d+)?$")

MANIFEST_YOLU: Final = Path("config/bagimsiz_veri.json")
VARSAYILAN_KOK: Final = Path("data/bagimsiz/french")
VARSAYILAN_SET: Final = "french_12ind_vw_gunluk_202607"


class FrenchHatasi(ValueError):
    """Bağımsız veri kimliği, şeması ya da bütünlüğü tutmuyor — veri kullanılmaz."""


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def zip_icerigi(ham: bytes) -> tuple[str, bytes]:
    """Zip'in tek üyesi `(ad, bayt)`. French zip'leri tek CSV taşır; fazlası beklenmez."""
    with zipfile.ZipFile(io.BytesIO(ham)) as z:
        adlar = z.namelist()
        if len(adlar) != 1:
            raise FrenchHatasi(f"zip tek dosya taşımalı, {len(adlar)} var: {adlar}")
        return adlar[0], z.read(adlar[0])


def bolumler(metin: str) -> dict[str, tuple[list[str], list[list[str]]]]:
    """CSV'nin tablo bölümleri: `{başlık: (sütunlar, satırlar)}`; hücreler metin, kırpılmış.

    Bölüm, `,` ile başlayan sütun satırıyla açılır; adı ondan önceki boş olmayan satırdır (faktör
    dosyasında açıklama satırı). Satırlar 8 haneli tarihle başlar; ilk tarih-dışı satırda biter.
    """
    satirlar = metin.splitlines()
    out: dict[str, tuple[list[str], list[list[str]]]] = {}
    i = 0
    while i < len(satirlar):
        if satirlar[i].startswith(","):
            baslik = next((s.strip() for s in reversed(satirlar[:i]) if s.strip()), "")
            sutunlar = [c.strip() for c in satirlar[i].split(",")]
            govde: list[list[str]] = []
            i += 1
            while i < len(satirlar):
                hucre = [c.strip() for c in satirlar[i].split(",")]
                if not (len(hucre[0]) == 8 and hucre[0].isdigit()):
                    break
                govde.append(hucre)
                i += 1
            if baslik in out:
                raise FrenchHatasi(f"aynı başlıklı iki bölüm: {baslik!r}")
            out[baslik] = (sutunlar, govde)
        else:
            i += 1
    return out


def _tarih_dogrula(satirlar: list[list[str]], ne: str, pencere_basi: int) -> None:
    """Sıra, tekrar ve takvim geçerliliği bütün satırlarda; hafta sonu yalnız pencerede (1952
    öncesinde cumartesi seansı vardı, K-124)."""
    onceki = 0
    for s in satirlar:
        t = int(s[0])
        if t <= onceki:
            raise FrenchHatasi(f"{ne}: tarih sırası bozuk ya da tekrar: {onceki} → {t}")
        try:
            gun = dt.date(t // 10000, t // 100 % 100, t % 100)
        except ValueError:
            raise FrenchHatasi(f"{ne}: geçersiz tarih {t}") from None
        if t >= pencere_basi and gun.weekday() >= 5:
            raise FrenchHatasi(f"{ne}: hafta sonu tarihi {t}")
        onceki = t


def _hucreler(satir: list[str], n: int, ne: str) -> list[str]:
    if len(satir) != n:
        raise FrenchHatasi(f"{ne} {satir[0]}: {n} hücre beklenirken {len(satir)}")
    for h in satir[1:]:
        if h in EKSIK_KODLARI:
            raise FrenchHatasi(f"{ne} {satir[0]}: eksik değer kodu {h} (pencerede eksik veri yok "
                               "sayılmaz, doldurulmaz)")
        if not _ONDALIK.match(h):
            raise FrenchHatasi(f"{ne} {satir[0]}: sayı olmayan hücre {h!r}")
    return satir


def kanonik_satirlar(
    sektor_zip: bytes, faktor_zip: bytes, *, baslangic: int, bitis: int
) -> list[list[str]]:
    """Penceredeki kanonik satırlar (`KANONIK_SUTUNLAR` sırasıyla, kaynak metinleriyle).

    Denetler: şema (sütun adları ve sırası birebir), tarih geçerliliği/sırası/tekrar/hafta sonu,
    eksik değer kodu, sayı biçimi, iki dosyanın pencerede **aynı** işlem günlerini taşıması,
    pencerenin kaynakta tam olarak `bitis`te bitmesi (kısa dosya sessizce kabul edilmez).
    """
    _, s_csv = zip_icerigi(sektor_zip)
    _, f_csv = zip_icerigi(faktor_zip)
    s_bol, f_bol = bolumler(s_csv.decode("latin-1")), bolumler(f_csv.decode("latin-1"))
    if VW_BOLUMU not in s_bol:
        raise FrenchHatasi(f"sektör dosyasında {VW_BOLUMU!r} bölümü yok: {list(s_bol)}")
    s_sut, s_sat = s_bol[VW_BOLUMU]
    if s_sut != ["", *SEKTORLER]:
        raise FrenchHatasi(f"sektör şeması değişmiş: {s_sut}")
    f_adaylar = [b for b in f_bol.values() if b[0] == ["", *FAKTORLER]]
    if len(f_adaylar) != 1:
        raise FrenchHatasi(f"faktör dosyasında tek bir {FAKTORLER} tablosu yok")
    f_sat = f_adaylar[0][1]
    _tarih_dogrula(s_sat, "sektör", baslangic)
    _tarih_dogrula(f_sat, "faktör", baslangic)

    s_pen = [s for s in s_sat if baslangic <= int(s[0]) <= bitis]
    f_pen = {s[0]: s for s in f_sat if baslangic <= int(s[0]) <= bitis}
    if not s_pen or s_pen[-1][0] != str(bitis) or int(s_sat[-1][0]) < bitis:
        raise FrenchHatasi(f"pencere kaynakta {bitis}'te bitmiyor (son: "
                           f"{s_pen[-1][0] if s_pen else None})")
    if [s[0] for s in s_pen] != list(f_pen):
        raise FrenchHatasi("sektör ve faktör dosyaları pencerede aynı işlem günlerini taşımıyor")
    out = []
    for s in s_pen:
        s = _hucreler(s, 1 + len(SEKTORLER), "sektör")
        f = _hucreler(f_pen[s[0]], 1 + len(FAKTORLER), "faktör")
        out.append([*s, f[1], f[4]])
    return out


def kanonik_metin(satirlar: list[list[str]]) -> bytes:
    govde = [",".join(KANONIK_SUTUNLAR), *(",".join(s) for s in satirlar)]
    return ("\n".join(govde) + "\n").encode("utf-8")


def veri_sha256(satirlar: list[list[str]]) -> str:
    """Bağımsız verinin kimliği: kanonik metnin SHA-256'sı."""
    return sha256(kanonik_metin(satirlar))


def cerceve(satirlar: list[list[str]]) -> pd.DataFrame:
    """Kanonik satırlardan getiri tablosu (kesir, yüzde değil). İndeks `zaman_ms` (UTC 00:00)."""
    tarih = np.array([int(s[0]) for s in satirlar])
    zaman = pd.to_datetime(tarih.astype(str), format="%Y%m%d", utc=True)
    deger = np.array([[float(h) for h in s[1:]] for s in satirlar]) / 100.0
    df = pd.DataFrame(deger, columns=list(KANONIK_SUTUNLAR[1:]))
    df.insert(0, "tarih", tarih)
    df.index = pd.Index(zaman.as_unit("ms").asi8, name="zaman_ms")
    return df


def veri_setleri(yol: str | Path | None = None) -> list[dict[str, Any]]:
    """Kayıtlı bağımsız doğrulama veri setleri (`config/bagimsiz_veri.json`, K-127)."""
    metin = Path(yol or MANIFEST_YOLU).read_text(encoding="utf-8")
    return list(json.loads(metin)["veri_setleri"])


def manifest_oku(dataset_id: str = VARSAYILAN_SET, yol: str | Path | None = None) -> dict[str, Any]:
    eslesen = [m for m in veri_setleri(yol) if m["dataset_id"] == dataset_id]
    if len(eslesen) != 1:
        raise FrenchHatasi(f"{dataset_id!r} kayıtta {len(eslesen)} kez var (tam bir kez olmalı)")
    return eslesen[0]


def promotion_icin_kayit(
    veri_sha256_: Any, dataset_id: Any, yol: str | Path | None = None
) -> dict[str, Any]:
    """Bağımsız doğrulama kanıtının veri kimliği, `promotion_uygun` işaretli **kayıtlı** bir
    setle birebir eşleşiyor mu? Eşleşmiyorsa `FrenchHatasi` (K-127 §4): kanıtın kendi beyanı
    (ör. `veri_sha256`) bağımsızlık ve PIT için yeterli değil; uygunluk karar kaydında verilir."""
    for m in veri_setleri(yol):
        if m["dataset_id"] == dataset_id and m["veri_sha256"] == veri_sha256_:
            if m.get("promotion_uygun") is not True:
                raise FrenchHatasi(f"{dataset_id}: promotion için uygun değil — {m.get('engel')}")
            return m
    raise FrenchHatasi(f"bağımsız veri ({dataset_id!r}, {str(veri_sha256_)[:12]}) kayıtlı bir "
                       "doğrulama veri seti değil (config/bagimsiz_veri.json)")


@dataclass(frozen=True)
class BagimsizVeri:
    manifest: dict[str, Any]
    satirlar: list[list[str]]

    @property
    def veri_sha256(self) -> str:
        return self.manifest["veri_sha256"]

    def kimlik(self) -> dict[str, Any]:
        """RYPP bağımsız doğrulama kanıtına (`bagimsiz_dogrulama`) girecek kimlik alanları."""
        m = self.manifest
        return {"dataset_id": m["dataset_id"], "kaynak": m["kaynak"]["ad"],
                "period_start": m["donem"]["baslangic"], "period_end": m["donem"]["bitis"],
                "veri_sha256": m["veri_sha256"]}

    def cerceve(self) -> pd.DataFrame:
        return cerceve(self.satirlar)


def yukle(kok: str | Path = VARSAYILAN_KOK, manifest: dict[str, Any] | None = None) -> BagimsizVeri:
    """Dondurulmuş bağımsız veriyi yükler; kimliğin her parçası yeniden hesaplanıp manifestle
    karşılaştırılır. Tutmayan bir şey varsa `FrenchHatasi` — farklı vintage/pencere/şema, veri
    değişikliği ya da bozulma. Veri yolu yoksa aynı hata: indirilen yeni dosya kilidi geçemez."""
    m = manifest if manifest is not None else manifest_oku()
    ham = Path(kok) / "ham"
    baytlar: dict[str, bytes] = {}
    for ad, beklenen in m["kaynak"]["dosyalar"].items():
        yol = ham / ad
        if not yol.is_file():
            raise FrenchHatasi(f"{yol} yok: `sq data bagimsiz-indir` (yalnız aynı vintage kabul "
                               "edilir)")
        b = yol.read_bytes()
        if sha256(b) != beklenen["zip_sha256"]:
            raise FrenchHatasi(f"{ad}: zip SHA-256 manifestle uyuşmuyor — farklı vintage ya da "
                               "bozuk dosya; yeni vintage yeni K ister (K-127)")
        uye, csv = zip_icerigi(b)
        if uye != beklenen["csv"] or sha256(csv) != beklenen["csv_sha256"]:
            raise FrenchHatasi(f"{ad}: içerik ({uye}) manifestle uyuşmuyor")
        baytlar[ad] = b
    if list(KANONIK_SUTUNLAR) != m["sema"]["sutunlar"]:
        raise FrenchHatasi("manifest şeması koddaki kanonik şemayla aynı değil")
    satirlar = kanonik_satirlar(
        baytlar[SEKTOR_ZIP], baytlar[FAKTOR_ZIP],
        baslangic=int(m["donem"]["baslangic"].replace("-", "")),
        bitis=int(m["donem"]["bitis"].replace("-", "")),
    )
    if len(satirlar) != m["satir"]:
        raise FrenchHatasi(f"penceredeki satır {len(satirlar)}, manifest {m['satir']}")
    if satirlar[0][0] != m["ilk_islem_gunu"].replace("-", ""):
        raise FrenchHatasi(f"ilk işlem günü {satirlar[0][0]}, manifest {m['ilk_islem_gunu']}")
    if veri_sha256(satirlar) != m["veri_sha256"]:
        raise FrenchHatasi("kanonik veri SHA-256 manifestle uyuşmuyor — veri değişmiş (K-127)")
    return BagimsizVeri(manifest=m, satirlar=satirlar)


def indir(
    kok: str | Path = VARSAYILAN_KOK, manifest: dict[str, Any] | None = None
) -> dict[str, str]:
    """Kaynak zip'leri indirir; **yalnız manifestteki vintage'la aynıysa** `ham/` altına yazar.

    Farklı bayt (French her ay yeniden üretir) `ham/<ad>.yeni` olarak bırakılır ve hata verilir:
    kilitli veri sessizce değiştirilmez.
    """
    import requests

    m = manifest if manifest is not None else manifest_oku()
    ham = Path(kok) / "ham"
    ham.mkdir(parents=True, exist_ok=True)
    out: dict[str, str] = {}
    for ad, beklenen in m["kaynak"]["dosyalar"].items():
        r = requests.get(KAYNAK_KOK + ad, timeout=120)
        r.raise_for_status()
        h = sha256(r.content)
        out[ad] = h
        if h != beklenen["zip_sha256"]:
            (ham / f"{ad}.yeni").write_bytes(r.content)
            raise FrenchHatasi(f"{ad}: kaynaktaki vintage değişmiş ({h[:12]} ≠ "
                               f"{beklenen['zip_sha256'][:12]}); dondurulan veri yerinde kalır, "
                               "yeni vintage yeni K ister (K-127)")
        (ham / ad).write_bytes(r.content)
    return out


def revizyon_olc(eski_zip: bytes, yeni_zip: bytes, *, baslangic: int) -> dict[str, Any]:
    """İki vintage arasında VW sektör hücrelerinin revizyonu (yalnız fark sayımı; getiri
    istatistiği yok). Ortak tarihler `baslangic`tan eskinin sonuna kadar."""
    def tablo(b: bytes) -> tuple[str, dict[str, list[str]]]:
        _, csv = zip_icerigi(b)
        metin = csv.decode("latin-1")
        sut, sat = bolumler(metin)[VW_BOLUMU]
        if sut != ["", *SEKTORLER]:
            raise FrenchHatasi(f"şema farklı: {sut}")
        return metin.splitlines()[0], {s[0]: s[1:] for s in sat if int(s[0]) >= baslangic}

    e_bas, e = tablo(eski_zip)
    y_bas, y = tablo(yeni_zip)
    son = max(e)
    y = {t: v for t, v in y.items() if t <= son}
    ortak = sorted(set(e) & set(y))
    fark = np.array([[abs(float(a) - float(b)) for a, b in zip(e[t], y[t], strict=True)]
                     for t in ortak])
    return {
        "eski": e_bas, "yeni": y_bas, "donem": [ortak[0], ortak[-1]],
        "gun": len(ortak), "yalniz_eskide": len(set(e) - set(y)),
        "yalniz_yenide": len(set(y) - set(e)), "hucre": int(fark.size),
        "degisen_oran": float((fark > 0).mean()),
        "bp10_ustu_oran": float((fark >= 0.10 - 1e-9).mean()),
        "bp100_ustu_oran": float((fark >= 1.0 - 1e-9).mean()),
        "azami_fark_yuzde_puan": float(fark.max()),
    }


def bagimsizlik_denetimi(
    defter_satirlari: list[dict[str, Any]], m: dict[str, Any]
) -> dict[str, Any]:
    """Hipotez defterinde bu verinin ya da kaynak dosyaların kimliğiyle kayıtlı çekiliş var mı?

    Kanıt sınırı: defter bu projenin **kayıtlı** çekilişlerini tutar (K-039). Kayıt dışı keşif
    (K-124'ün IS ölçümü gibi) defterde görünmez; o yüzden K-124'ün kapsamı karar kaydından ayrıca
    okunur ve doğrulama penceresinin onunla örtüşmediği manifestte yazılıdır.
    """
    kimlikler = {m["veri_sha256"]} | {
        d[a] for d in m["kaynak"]["dosyalar"].values() for a in ("zip_sha256", "csv_sha256")
    }
    carpan = [s["kimlik"] for s in defter_satirlari if s.get("veri_sha256") in kimlikler]
    return {"defter_satiri": len(defter_satirlari), "carpisan_cekilis": carpan,
            "bagimsiz": not carpan}


__all__ = [
    "FAKTORLER",
    "KANONIK_SUTUNLAR",
    "MANIFEST_YOLU",
    "SEKTORLER",
    "VARSAYILAN_KOK",
    "VARSAYILAN_SET",
    "BagimsizVeri",
    "FrenchHatasi",
    "bagimsizlik_denetimi",
    "bolumler",
    "cerceve",
    "indir",
    "kanonik_metin",
    "kanonik_satirlar",
    "manifest_oku",
    "promotion_icin_kayit",
    "revizyon_olc",
    "veri_setleri",
    "veri_sha256",
    "yukle",
]
