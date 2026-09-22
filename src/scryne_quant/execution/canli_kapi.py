"""Mod kapıları ve live gate: her yukarı geçişin makine kontrol listesi. (K-114)

Her kontrol geçer/kalır döndürür ve **ölçülemeyen kontrol geçmiş sayılmaz** (K-019'un
cümlesi: *"'Veri yoktu' ile 'kapıdan geçti' aynı şey değil"*). Bir kontrolün `gecti` alanı
`None` ise ölçülemedi demektir ve rapor `gecti=False` olur.

**Bu modül eşik icat etmez.** Kontrollerin ölçtüğü her sayı ya mevcut bir karardan gelir
(K-010 promotion zinciri, K-046 pozisyon farkı 0, K-041 saat sıçraması 0, K-065 kill
tatbikatı, K-111 R8 sözleşme hash'i) ya da Scryne'ın vereceği bir karardır ve o hâlde
`config/kademe.json`da `DECISION REQUIRED` olarak durur ve **kapıyı kapalı tutar**.
Engelleyen katman her yerde olabilir; izin veren katman yalnızca bu kontrol listesinin
tamamı + insan onayıdır (K-037, K-050).

**`CanliYetki`yi üreten tek yer `canli_yetki_ver`.** Mod LIVE olmalı, LIVE kapısı o an
yeniden çalışıp geçmeli ve raporun hash'i insanın onayladığı hash ile aynı olmalı. Yetki
diske yazılmaz; her canlı koşu başlangıcında yeniden türetilir.

Ağ gerektiren kontroller (`AgYoklamasi`) dışarıdan verilir: bu modül ağa çıkmaz, test
edilebilir kalır, ve ağ verilmeyen bir değerlendirme o kontrolleri **ölçülemedi** yazar.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from scryne_quant.common.hash import git_durumu, nesne_hash
from scryne_quant.common.zaman import simdi_ms, utc_str
from scryne_quant.exchange import yetki as yetki_mod
from scryne_quant.execution.mod import CalismaModu, ModDefteri, ModKaydi
from scryne_quant.risk import limitler as limitler_mod
from scryne_quant.risk.audit import Defter
from scryne_quant.risk.promotion import Asama, PromotionDefteri, PromotionHatasi

#: R8'in dondurulmuş kriter dosyasının SHA-256'sı (K-111). Değişirse R8 sözleşmesi bozulmuş
#: demektir ve **hiçbir** yukarı geçiş yapılmaz.
R8_KRITER_SHA256_ONEK: Final = "2c3d520e8f3fe5d2"

KADEME_YOLU: Final = Path("config/kademe.json")
VENUE_YOLU: Final = Path("config/venue_statu.json")
OPERASYON_YOLU: Final = Path("config/operasyon_dogrulama.json")
R8_KRITER_YOLU: Final = Path("config/r8_kriterler.json")
KOSU_KOKU: Final = Path("runs/execution")
TEST_KAYDI: Final = KOSU_KOKU / "testler.json"

KARAR_BEKLIYOR: Final = "DECISION REQUIRED"

LF: Final = bytes([10])
CRLF: Final = bytes([13, 10])


@dataclass(frozen=True, slots=True)
class Kontrol:
    """Tek bir kapı kontrolü. `gecti=None` → ölçülemedi → kapı kapalı."""

    ad: str
    gecti: bool | None
    ayrinti: str
    engel: str = ""
    """Geçmediyse neyin gerektiği ve hangi K/R kararına bağlı olduğu."""

    kanit: str = ""
    """Kararlı kanıt kimliği (dosya hash'i, satır hash'i). Rapor hash'ine **bu** girer,
    `ayrinti` girmez — ağ gecikmesi gibi oynak ölçümler onayı geçersiz kılmasın."""

    def sozluk(self) -> dict[str, Any]:
        return {
            "ad": self.ad,
            "gecti": self.gecti,
            "ayrinti": self.ayrinti,
            "engel": self.engel,
            "kanit": self.kanit,
        }


@dataclass
class AgYoklamasi:
    """Ağ gerektiren ölçümler. Her biri çağrıldığında borsaya gider; `None` = verilmedi."""

    okuma_anahtari_kisitlari: Callable[[], dict[str, Any]] | None = None
    islem_anahtari_kisitlari: Callable[[], dict[str, Any]] | None = None
    testnet_baglantisi: Callable[[], dict[str, Any]] | None = None
    canli_baglantisi: Callable[[], dict[str, Any]] | None = None


@dataclass
class KapiBaglami:
    kok: Path = field(default_factory=lambda: Path("."))
    strateji: str | None = None
    audit: Defter | None = None
    ag: AgYoklamasi = field(default_factory=AgYoklamasi)
    mod_defteri: ModDefteri | None = None

    def yol(self, goreli: Path) -> Path:
        return self.kok / goreli

    def mod_kaydi(self) -> ModKaydi:
        defter = self.mod_defteri or ModDefteri(self.yol(Path("runs/execution/mod.json")))
        return defter.oku()


def _sha256(yol: Path) -> str:
    return hashlib.sha256(yol.read_bytes()).hexdigest()


def _json(yol: Path) -> dict[str, Any] | None:
    if not yol.is_file():
        return None
    try:
        veri = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return veri if isinstance(veri, dict) else None


# ============================================================ temel kontroller


def mod_kaydi_kontrolu(b: KapiBaglami) -> Kontrol:
    kayit = b.mod_kaydi()
    if kayit.bozuk:
        return Kontrol("mod_kaydi", False, f"mod kaydı bozuk: {kayit.bozuk}",
                       "kayıt incelenmeli; bozuk kayıt DISABLED okunur (K-114)")
    # Kanıt boş: onay satırı zincire eklenince son hash değişir, ama kararı değiştirmez.
    return Kontrol("mod_kaydi", True, f"zincir sağlam, mod {kayit.mod}")


def r8_kriter_sha256(yol: Path) -> str:
    """R8 kriter dosyasının **CRLF biçimindeki** SHA-256'sı (K-111'in hash'lediği biçim).

    K-111 hash'i (`2c3d520e…`) dosya Windows'ta CRLF satır sonlarıyla dururken alındı; git
    dosyayı LF olarak saklıyor (`core.autocrlf=true`) ve LF biçimin hash'i `9519524c…`.
    İçerik aynı, yalnızca satır sonu farklı — ve bir checkout'un satır sonu ayarına göre
    sözleşmeyi "bozulmuş" saymak yanlış alarm olurdu. Satır sonları normalize edilip CRLF'e
    çevrilerek hash'lenir; **içerikteki** her değişiklik hash'i yine değiştirir (K-114).
    """
    lf = yol.read_bytes().replace(CRLF, LF)
    return hashlib.sha256(lf.replace(LF, CRLF)).hexdigest()


def r8_sozlesmesi_kontrolu(b: KapiBaglami) -> Kontrol:
    yol = b.yol(R8_KRITER_YOLU)
    if not yol.is_file():
        return Kontrol("r8_sozlesmesi", False, "config/r8_kriterler.json yok",
                       "R8 dondurulmuş kriterleri geri getirilmeli (K-111)")
    sha = r8_kriter_sha256(yol)
    if not sha.startswith(R8_KRITER_SHA256_ONEK):
        return Kontrol("r8_sozlesmesi", False, f"R8 kriter hash'i değişmiş: {sha[:16]}…",
                       "R8 frozen sözleşmesi değiştirilemez (K-111); dosya geri alınmalı")
    return Kontrol("r8_sozlesmesi", True, f"R8 kriterleri dondurulduğu gibi ({sha[:16]}…)",
                   kanit=sha)


def risk_config_kontrolu(b: KapiBaglami) -> Kontrol:
    try:
        limitler = limitler_mod.yukle(b.yol(Path("config/risk.json")))
    except (OSError, ValueError) as hata:
        return Kontrol("risk_config", False, f"config/risk.json okunamadı: {hata}",
                       "risk limitleri yüklenmeden hiçbir mod açılmaz (K-032)")
    return Kontrol("risk_config", True, f"limit kimliği {limitler.kimlik()[:16]}…",
                   kanit=limitler.kimlik())


def kosu_raporlari(b: KapiBaglami) -> list[tuple[Path, dict[str, Any]]]:
    """`runs/execution/<koşu>/rapor.json` dosyaları, yeniden eskiye."""
    kok = b.yol(KOSU_KOKU)
    out: list[tuple[Path, dict[str, Any]]] = []
    for p in sorted(kok.glob("*/rapor.json")) if kok.is_dir() else []:
        veri = _json(p)
        if veri is not None:
            out.append((p, veri))
    out.sort(key=lambda x: int(x[1].get("bitis_ms", 0)), reverse=True)
    return out


def kosu_raporu_kontrolu(
    b: KapiBaglami,
    mod: CalismaModu,
    *,
    ad: str,
    engel: str,
    olcut: Callable[[dict[str, Any]], str | None] | None = None,
    kanitli: bool = False,
) -> Kontrol:
    """`mod`da koşmuş, `gecti=true` bir rapor var mı (ve `olcut` sağlanıyor mu)?"""
    adaylar = [(p, r) for p, r in kosu_raporlari(b) if r.get("mod") == str(mod)]
    if not adaylar:
        return Kontrol(ad, False, f"{mod} koşu raporu yok", engel)
    son_sebep = ""
    for p, r in adaylar:
        if not r.get("gecti"):
            son_sebep = f"{p.parent.name}: gecti=false ({'; '.join(r.get('kalan', []))})"
            continue
        if olcut is not None:
            sebep = olcut(r)
            if sebep:
                son_sebep = f"{p.parent.name}: {sebep}"
                continue
        # Altyapı kanıtında (paper/testnet) varlık yeter; kanıt hash'e girmez, yoksa her yeni
        # koşu onayı geçersiz kılardı. Shadow'un canlı kanıtı ise **belirli** bir rapordur.
        return Kontrol(ad, True, f"{p.parent.name} ({utc_str(int(r.get('bitis_ms', 0)))})",
                       kanit=_sha256(p) if kanitli else "")
    return Kontrol(ad, False, son_sebep, engel)


# ============================================================ live kontrolleri


def strateji_onayi_kontrolu(b: KapiBaglami) -> Kontrol:
    if not b.strateji:
        return Kontrol("strateji_onayi", False, "strateji verilmedi",
                       "promotion zincirini (K-010) geçmiş strateji gerekiyor")
    try:
        kayit = PromotionDefteri(b.yol(Path("runs/promotion"))).oku(b.strateji, audit=b.audit)
    except (PromotionHatasi, OSError, ValueError) as hata:
        return Kontrol("strateji_onayi", False, f"promotion kaydı doğrulanamadı: {hata}",
                       "K-082: zincirli ve audit'e bağlı kayıt gerekiyor (fail closed)")
    if b.audit is None:
        return Kontrol("strateji_onayi", None, "audit verilmedi; K-082 çapraz kontrolü yok",
                       "live gate audit defteriyle çalıştırılmalı (runs/audit.sqlite)")
    if kayit.asama is not Asama.LIVE:
        return Kontrol(
            "strateji_onayi", False, f"{b.strateji}: aşama {kayit.asama}",
            "promotion zincirinin sonu (LIVE) gerekiyor — bugün geçen strateji yok "
            "(K-078/1, K-110; araştırma K-111 ile askıda)",
        )
    son = kayit.gecmis[-1].get("satir_hash", "") if kayit.gecmis else ""
    return Kontrol("strateji_onayi", True, f"{b.strateji}: LIVE (K-010)", kanit=son)


def kademe_tablosu(b: KapiBaglami) -> dict[str, Any] | None:
    return _json(b.yol(KADEME_YOLU))


def aktif_kademe(tablo: dict[str, Any]) -> dict[str, Any] | None:
    no = tablo.get("aktif_kademe")
    for k in tablo.get("kademeler", []):
        if k.get("kademe") == no:
            return k
    return None


def kademe_kontrolu(b: KapiBaglami) -> Kontrol:
    tablo = kademe_tablosu(b)
    if tablo is None:
        return Kontrol("kademe", False, "config/kademe.json yok",
                       "kademe tablosu açılmalı (Faz-8-Hazirlik §2, K-050/3)")
    sermaye = tablo.get("risk_sermayesi_usdt")
    if not isinstance(sermaye, (int, float)) or sermaye <= 0:
        return Kontrol("kademe", False, "risk_sermayesi_usdt boş",
                       "Scryne kararı: risk sermayesi (Final-Doküman §Bütçeler, "
                       "Faz-8-Hazirlik §6/3)")
    k = aktif_kademe(tablo)
    if k is None or int(k.get("kademe", 0)) < 1:
        return Kontrol("kademe", False, "aktif kademe ≥ 1 değil",
                       "Kademe 0 = shadow; canlı en az Kademe 1 ister (K-050/3)")
    ks = k.get("sermaye_usdt")
    if not isinstance(ks, (int, float)) or ks <= 0:
        return Kontrol("kademe", False, f"Kademe {k['kademe']} sermayesi boş",
                       "shadow notional p5 / minNotional marjından ölçülür (Faz-8-Hazirlik §2.2)")
    if ks > sermaye:
        return Kontrol("kademe", False, f"kademe sermayesi {ks} > risk sermayesi {sermaye}",
                       "kademe risk sermayesini aşamaz")
    onay = k.get("onay") or {}
    if not (onay.get("not") and onay.get("tarih")):
        return Kontrol("kademe", False, f"Kademe {k['kademe']} onayı boş",
                       "onay `null` olan kademe yoktur (Faz-8-Hazirlik §2.1)")
    onceki = [x for x in tablo.get("kademeler", [])
              if int(x.get("kademe", -1)) == int(k["kademe"]) - 1]
    if int(k["kademe"]) > 1 and not (onceki and (onceki[0].get("onay") or {}).get("tarih")):
        return Kontrol("kademe", False, "kademe atlanamaz: önceki kademe onaysız",
                       "Faz-8-Hazirlik §2.1")
    return Kontrol("kademe", True, f"Kademe {k['kademe']}: {ks} USDT (risk sermayesi {sermaye})",
                   kanit=nesne_hash(tablo))


def kademe_kararlari_kontrolu(b: KapiBaglami) -> Kontrol:
    """`DECISION REQUIRED` işaretli kalem kaldıysa kapı kapalı (Faz-8-Hazirlik §6)."""
    tablo = kademe_tablosu(b)
    if tablo is None:
        return Kontrol("acik_kararlar", False, "config/kademe.json yok", "Faz-8-Hazirlik §6")
    acik = [ad for ad, k in (tablo.get("kararlar") or {}).items()
            if isinstance(k, dict) and str(k.get("durum", "")).startswith(KARAR_BEKLIYOR)]
    if acik:
        return Kontrol("acik_kararlar", False, f"açık kararlar: {', '.join(sorted(acik))}",
                       "Scryne kararları K olarak yazılmalı (Faz-8-Hazirlik §6)")
    return Kontrol("acik_kararlar", True, "Faz-8-Hazirlik §6 kararları kapalı",
                   kanit=nesne_hash(tablo.get("kararlar") or {}))


def venue_kontrolu(b: KapiBaglami) -> Kontrol:
    v = _json(b.yol(VENUE_YOLU))
    if v is None:
        return Kontrol("venue_statusu", False, "config/venue_statu.json yok",
                       "venue hukuki statü kaydı (Faz-8-Hazirlik §3, Denetim-v2 D2)")
    sonuc = v.get("sonuc")
    if sonuc != "AÇIK":
        return Kontrol("venue_statusu", False, f"sonuc={sonuc!r}",
                       "yalnız `AÇIK` canlıyı açar; `BELİRSİZ` de bir sonuçtur ve açmaz "
                       "(Faz-8-Hazirlik §3.2) — kaynaklı kayıt Scryne'dan")
    if not v.get("kaynaklar"):
        return Kontrol("venue_statusu", False, "kaynaksız statü", "her iddia kaynaklı olmalı")
    return Kontrol("venue_statusu", True, f"{v.get('venue')}: AÇIK ({v.get('kayit_tarihi')})",
                   kanit=nesne_hash(v))


def operasyon_kontrolu(b: KapiBaglami) -> Kontrol:
    """R8 PASS (K-112) — önceden varsayılmaz; kapanış kaydı yoksa kapı kapalı."""
    v = _json(b.yol(OPERASYON_YOLU))
    if v is None or not isinstance(v.get("r8"), dict):
        return Kontrol(
            "operasyon_r8", False, "R8 kapanış kaydı yok",
            "R8 (r8-kiyas, 2026-09-25 → 2026-10-09) kapanmalı ve K-112 PASS olmalı; "
            "sonuç önceden kabul edilmez (K-111)",
        )
    r8 = v["r8"]
    kriter = b.yol(R8_KRITER_YOLU)
    sha = r8_kriter_sha256(kriter) if kriter.is_file() else ""
    if r8.get("kriter_sha256") != sha:
        return Kontrol("operasyon_r8", False, "R8 sonucu başka bir kriter dosyasına ait",
                       "R8 sonucu dondurulmuş kriterlerle (K-111) ölçülmüş olmalı")
    if r8.get("sonuc") != "PASS" or r8.get("karar") != "K-112":
        return Kontrol("operasyon_r8", False, f"R8 sonucu {r8.get('sonuc')!r}",
                       "R8 FAIL ise giderme + yeni koşu adı (K-111 sonuç kuralı)")
    return Kontrol("operasyon_r8", True, f"R8 PASS ({r8.get('kayit')})", kanit=nesne_hash(r8))


def golge_olcutu(b: KapiBaglami) -> Callable[[dict[str, Any]], str | None]:
    """Faz-8-Hazirlik §1.5 kapısı; sayılar `config/kademe.json` `golge_olcutu`ndan."""
    tablo = kademe_tablosu(b) or {}
    o = tablo.get("golge_olcutu") or {}

    def olc(r: dict[str, Any]) -> str | None:
        if o.get("asgari_gun") is None or o.get("asgari_golge") is None:
            return "shadow ölçütü tanımsız (config/kademe.json golge_olcutu)"
        if b.strateji and r.get("strateji") != b.strateji:
            return f"başka strateji ({r.get('strateji')})"
        if r.get("risk_modu") != "shadow":
            return f"risk modu {r.get('risk_modu')!r}: kanıt yalnız `shadow` risk modundan"
        if float(r.get("sure_gun", 0.0)) < float(o["asgari_gun"]):
            return f"süre {r.get('sure_gun')} < {o['asgari_gun']} gün"
        if int(r.get("golge_sayisi", 0)) < int(o["asgari_golge"]):
            return f"GOLGE {r.get('golge_sayisi')} < {o['asgari_golge']}"
        for alan in ("kural_reddi", "pozisyon_farki", "saat_sicramasi", "aciklanamaz_kesinti"):
            if int(r.get(alan, 1)) != 0:
                return f"{alan} = {r.get(alan)} (0 olmalı)"
        return None

    return olc


def kill_tatbikati_kontrolu(b: KapiBaglami) -> Kontrol:
    """Canlı host'a karşı kill tatbikatı (K-065, Faz-8-Hazirlik §1.3/6)."""
    kok = b.yol(KOSU_KOKU)
    for p in sorted(kok.glob("*/kill.json"), reverse=True) if kok.is_dir() else []:
        r = _json(p) or {}
        # Kanıt: canlı host + başarılı iptal doğrulaması + **yaşayan** bir sürecin gerçekten
        # sonlandırılması. Zaten kapanmış bir koşuya karşı kill, K-065'in ölçtüğü şeyi
        # (donmuş/çalışan süreci dışarıdan durdurmak) ölçmez.
        surec = r.get("surec") or {}
        if (r.get("canli_host") and r.get("basarili") and surec.get("sonlandirildi")
                and surec.get("not") != "zaten ölüydü"):
            return Kontrol("kill_tatbikati", True, f"{p.parent.name}: başarılı",
                           kanit=_sha256(p))
    return Kontrol("kill_tatbikati", False, "canlı host'a karşı başarılı kill tatbikatı yok",
                   "shadow sırasında `sq execution kill --kosu <shadow>` (K-065)")


def testler_kontrolu(b: KapiBaglami) -> Kontrol:
    kayit = _json(b.yol(TEST_KAYDI))
    git = git_durumu(b.kok)
    if kayit is None:
        return Kontrol("testler", False, "test kaydı yok",
                       "`sq execution test-kaydet` (temiz ağaç, HEAD)")
    if git.get("commit") is None:
        return Kontrol("testler", None, "git durumu okunamadı", "git gerekli (K-009)")
    if kayit.get("commit") != git["commit"] or kayit.get("dirty") or git.get("dirty"):
        return Kontrol("testler", False,
                       f"test kaydı HEAD'e ait değil ya da ağaç kirli "
                       f"({str(kayit.get('commit'))[:8]} vs {git['commit'][:8]})",
                       "temiz ağaçta `sq execution test-kaydet` yeniden")
    if int(kayit.get("kalan", 1)) != 0 or int(kayit.get("gecen", 0)) <= 0:
        return Kontrol("testler", False, f"kalan test {kayit.get('kalan')}", "test takımı yeşil")
    return Kontrol("testler", True, f"{kayit['gecen']} test yeşil @ {git['commit'][:8]}",
                   kanit=f"{git['commit']}:{kayit['gecen']}")


def kritik_hata_kontrolu(b: KapiBaglami) -> Kontrol:
    """Açık SAFE_MODE işareti, durdurulmuş (halt) koşu ya da çözülmemiş UNKNOWN emir."""
    kok = b.yol(KOSU_KOKU)
    sorunlar: list[str] = []
    for p in sorted(kok.glob("*/durum.json")) if kok.is_dir() else []:
        d = _json(p) or {}
        if (p.parent / "kosu.safemode").is_file():
            sorunlar.append(f"{p.parent.name}: SAFE_MODE işareti açık")
        if d.get("halt"):
            sorunlar.append(f"{p.parent.name}: halt ({d.get('halt')})")
        if int((d.get("emirler") or {}).get("belirsiz", 0)):
            sorunlar.append(f"{p.parent.name}: çözülmemiş UNKNOWN emir")
    if sorunlar:
        return Kontrol("kritik_hata_yok", False, "; ".join(sorunlar),
                       "her biri gerekçeyle kapatılmalı (K-008/4, K-038)")
    return Kontrol("kritik_hata_yok", True, "açık SAFE_MODE/halt/UNKNOWN yok")


def _ag_kontrolu(
    ad: str,
    yoklama: Callable[[], dict[str, Any]] | None,
    degerlendir: Callable[[dict[str, Any]], str | None],
    engel: str,
) -> Kontrol:
    if yoklama is None:
        return Kontrol(ad, None, "ağ yoklaması verilmedi (ölçülemedi)", engel)
    try:
        sonuc = yoklama()
    except Exception as hata:  # noqa: BLE001 — her hata "ölçülemedi"ye değil "kaldı"ya düşer
        return Kontrol(ad, False, f"{type(hata).__name__}: {hata}", engel)
    sebep = degerlendir(sonuc)
    if sebep:
        return Kontrol(ad, False, sebep, engel)
    return Kontrol(ad, True, json.dumps(sonuc, ensure_ascii=False, sort_keys=True)[:160],
                   kanit=ad)


def _yetki_degerlendir(mod: str) -> Callable[[dict[str, Any]], str | None]:
    from scryne_quant.exchange.canli import yetki_ihlalleri

    def degerlendir(kisitlar: dict[str, Any]) -> str | None:
        ihlal = yetki_ihlalleri(mod, kisitlar)
        return "; ".join(ihlal) if ihlal else None

    return degerlendir


def _baglanti_degerlendir(sonuc: dict[str, Any]) -> str | None:
    if not sonuc.get("ok"):
        return str(sonuc.get("hata", "bağlantı yok"))
    return None


# ============================================================ kapılar


def _kontroller(hedef: CalismaModu, b: KapiBaglami) -> list[Kontrol]:
    temel = [mod_kaydi_kontrolu(b), r8_sozlesmesi_kontrolu(b), risk_config_kontrolu(b)]
    if hedef is CalismaModu.PAPER:
        return temel
    paper = kosu_raporu_kontrolu(
        b, CalismaModu.PAPER, ad="paper_kaniti",
        engel="≥1 paper koşusu uçtan uca: emir→fill→mutabakat temiz (`sq execution calistir "
              "--mod paper`)",
    )
    if hedef is CalismaModu.SHADOW:
        return [
            *temel,
            paper,
            _ag_kontrolu("okuma_anahtari_yetkisi", b.ag.okuma_anahtari_kisitlari,
                         _yetki_degerlendir("shadow"),
                         "salt okunur anahtar: işlem/çekim kapalı (Faz-8-Hazirlik §1.2)"),
            _ag_kontrolu("canli_baglanti", b.ag.canli_baglantisi, _baglanti_degerlendir,
                         "canlı borsaya okuma bağlantısı"),
        ]
    golge_altyapi = kosu_raporu_kontrolu(
        b, CalismaModu.SHADOW, ad="shadow_kaniti",
        engel="≥1 shadow koşusu uçtan uca, GOLGE kaydı + pozisyon farkı 0",
    )
    if hedef is CalismaModu.TESTNET:
        return [
            *temel,
            paper,
            golge_altyapi,
            _ag_kontrolu("testnet_baglanti", b.ag.testnet_baglantisi, _baglanti_degerlendir,
                         "testnet anahtarı + bağlantı (SQ_BINANCE_TESTNET_API_KEY)"),
        ]
    # LIVE_PENDING_APPROVAL ve LIVE: aynı liste; LIVE yalnızca insan onayıyla açılır.
    return [
        *temel,
        paper,
        kosu_raporu_kontrolu(
            b, CalismaModu.TESTNET, ad="testnet_kaniti",
            engel="≥1 testnet koşusu: sinyal→risk→niyet→kapı→emir→fill→mutabakat→portföy, "
                  "duplicate engellendi",
        ),
        kosu_raporu_kontrolu(
            b, CalismaModu.SHADOW, ad="shadow_live_kaniti",
            engel="aynı stratejinin `shadow` risk modunda §1.5 kapısını geçen shadow koşusu "
                  "(≥ asgari gün/GOLGE, kural reddi/pozisyon farkı/saat sıçraması/kesinti 0)",
            olcut=golge_olcutu(b),
            kanitli=True,
        ),
        strateji_onayi_kontrolu(b),
        operasyon_kontrolu(b),
        kademe_kontrolu(b),
        kademe_kararlari_kontrolu(b),
        venue_kontrolu(b),
        kill_tatbikati_kontrolu(b),
        testler_kontrolu(b),
        kritik_hata_kontrolu(b),
        _ag_kontrolu("islem_anahtari_yetkisi", b.ag.islem_anahtari_kisitlari,
                     _yetki_degerlendir("live"),
                     "işlem anahtarı: spot işlem açık, çekim/transfer/margin/futures kapalı, "
                     "IP kısıtlı (Faz-8-Hazirlik §1.2/§1.6) — promotion elle onayından "
                     "(K-010) sonra üretilir"),
        _ag_kontrolu("canli_baglanti", b.ag.canli_baglantisi, _baglanti_degerlendir,
                     "canlı borsa bağlantısı ve saat"),
    ]


def kapi_raporu(hedef: CalismaModu, b: KapiBaglami) -> dict[str, Any]:
    """Hedef modun kontrol listesi. `gecti` yalnızca **her** kontrol `True` ise doğru.

    `hash` yalnızca kararlı alanlardan (ad, gecti, kanit) + hedef + strateji + kademe:
    onaylanan rapor ile başlangıçta yeniden üretilen rapor, yalnızca **karar değiştiren**
    bir şey değiştiyse farklıdır.
    """
    kontroller = _kontroller(hedef, b)
    tablo = kademe_tablosu(b) or {}
    k = aktif_kademe(tablo) if tablo else None
    govde = {
        "hedef": str(hedef),
        "strateji": b.strateji or "",
        "kademe": None if k is None else k.get("kademe"),
        "sermaye_usdt": None if k is None else k.get("sermaye_usdt"),
        "kontroller": [(x.ad, x.gecti, x.kanit) for x in kontroller],
    }
    gecti = all(x.gecti is True for x in kontroller)
    return {
        "hedef": str(hedef),
        "strateji": b.strateji or "",
        "kademe": govde["kademe"],
        "sermaye_usdt": govde["sermaye_usdt"],
        "gecti": gecti,
        "kontroller": [x.sozluk() for x in kontroller],
        "engeller": [
            {"ad": x.ad, "engel": x.engel, "ayrinti": x.ayrinti}
            for x in kontroller if x.gecti is not True
        ],
        "hash": nesne_hash(govde),
        "zaman_ms": simdi_ms(),
    }


class CanliKapiKapali(PermissionError):
    """Canlı yetki üretilemedi: mod, kapı ya da onay hash'i tutmuyor."""


def canli_yetki_ver(b: KapiBaglami) -> tuple[yetki_mod.CanliYetki, dict[str, Any]]:
    """Canlı koşu başlangıcında yetkiyi **yeniden** türetir. Tek `yetki.ver` çağrısı burada.

    Üç şart, üçü de her başlangıçta yeniden:
    1. Mod kaydı LIVE ve zinciri sağlam (bozuk kayıt DISABLED okunur).
    2. LIVE kapısı şimdi yeniden çalışıyor ve geçiyor.
    3. Şimdiki raporun hash'i, insanın onay satırındaki `kapi_hash` ile aynı. Onaydan sonra
       karar değiştiren bir şey değiştiyse (strateji aşaması, kademe, test kaydı, anahtar
       yetkisi…) yetki yok — yeniden onay gerekir.
    """
    kayit = b.mod_kaydi()
    onay = kayit.son_onay
    if onay is None:
        raise CanliKapiKapali(f"mod LIVE değil ({kayit.mod}); canlı yetki üretilmez")
    rapor = kapi_raporu(CalismaModu.LIVE, b)
    if not rapor["gecti"]:
        eksik = ", ".join(e["ad"] for e in rapor["engeller"])
        raise CanliKapiKapali(f"LIVE kapısı şimdi geçmiyor: {eksik}")
    if rapor["hash"] != onay.get("kapi_hash"):
        raise CanliKapiKapali(
            "onaylanan kapı raporu ile şimdiki rapor farklı; onaydan sonra karar değiştiren "
            "bir şey değişti. Yeniden `sq execution preflight` + `sq execution onayla`."
        )
    if rapor["strateji"] != onay.get("strateji"):
        raise CanliKapiKapali("onaylanan strateji ile başlatılan strateji farklı")
    yetki = yetki_mod.ver(
        kanit_hash=rapor["hash"],
        onay_hash=str(onay.get("satir_hash", "")),
        strateji=rapor["strateji"],
        kademe=int(rapor["kademe"]),
        sermaye_usdt=float(rapor["sermaye_usdt"]),
    )
    return yetki, rapor


__all__ = [
    "KADEME_YOLU",
    "KARAR_BEKLIYOR",
    "OPERASYON_YOLU",
    "R8_KRITER_SHA256_ONEK",
    "TEST_KAYDI",
    "VENUE_YOLU",
    "AgYoklamasi",
    "CanliKapiKapali",
    "KapiBaglami",
    "Kontrol",
    "aktif_kademe",
    "canli_yetki_ver",
    "kademe_tablosu",
    "kapi_raporu",
    "r8_kriter_sha256",
    "kosu_raporlari",
]
