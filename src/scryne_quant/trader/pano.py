"""Operasyon panosu: tek ekran, salt okuma. (K-114, R9/R11)

`sq execution pano` (127.0.0.1:8790). On bölüm — SYSTEM, MARKET, STRATEGY, SIGNAL,
PORTFOLIO, RISK, ORDERS, EXECUTION, JEV, AUDIT — ve en üstte **CURRENT MODE**.

**Pano hiçbir şeyi değiştirmez.** Emir, iptal, mod geçişi, onay yok: bunların hepsi CLI'da
ve bilerek orada (onay TTY ister). Pano yalnızca diskteki kayıtları okur — koşuların
`durum.json`u, mod kaydı, preflight raporları, audit defterleri, Jev gölge durumu. Borsaya
hiç bağlanmaz; gösterdiği her sayı bir koşunun **yazdığı** sayıdır ve yazıldığı an yanında.

Tasarım `DESIGN.md`den: opak nötr yüzeyler, yoğun ölçek, Fira Sans + Fira Code (`tnum`);
**tek** doygun renk risk (`#FF5A1F`) ve LIVE modu da o renkle — canlı mod bir risk
durumudur. Kâr/zarar yalnızca düşük doygunluklu yön rengi + işaretle.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from scryne_quant.common.hash import git_durumu
from scryne_quant.common.zaman import simdi_ms, utc_str
from scryne_quant.execution.canli_kapi import R8_KRITER_SHA256_ONEK, r8_kriter_sha256
from scryne_quant.execution.mod import ModDefteri


def _json(p: Path) -> dict[str, Any] | None:
    try:
        v = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return v if isinstance(v, dict) else None


def _audit_son(yol: Path, n: int = 15) -> dict[str, Any]:
    if not yol.is_file():
        return {"yol": str(yol), "var": False, "satirlar": []}
    try:
        db = sqlite3.connect(f"file:{yol}?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        satirlar = [
            dict(s) for s in db.execute(
                "SELECT id, tur, zaman_ms, sembol, substr(govde, 1, 240) AS govde, satir_hash "
                "FROM audit ORDER BY id DESC LIMIT ?", (n,)
            )
        ]
        toplam = db.execute("SELECT COUNT(*) FROM audit").fetchone()[0]
        db.close()
    except sqlite3.Error as hata:
        return {"yol": str(yol), "var": True, "hata": str(hata), "satirlar": []}
    return {"yol": str(yol), "var": True, "toplam": toplam, "satirlar": satirlar}


def _jev(kok: Path) -> dict[str, Any]:
    dosyalar = sorted((kok / "runs/jev").glob("*.sqlite.durum.json"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
    if not dosyalar:
        return {"var": False}
    d = _json(dosyalar[0]) or {}
    return {
        "var": True,
        "kosu": d.get("kosu"),
        "mod": d.get("mod"),
        "model": d.get("model"),
        "toplam": d.get("toplam"),
        "hata": d.get("hata"),
        "yon_dagilimi": d.get("yon_dagilimi"),
        "rejim_dagilimi": d.get("rejim_dagilimi"),
        "cekimserlik_orani": d.get("cekimserlik_orani"),
        "son_bar_utc": utc_str(d["son_bar_ms"]) if d.get("son_bar_ms") else None,
        "yazildi_utc": utc_str(d["yazildi_ms"]) if d.get("yazildi_ms") else None,
        "not": "Jev yalnızca gölge/ölçüm: sinyal üretmez, işlem katmanına ulaşamaz (K-067, K-074).",
    }


def durum_topla(kok: Path, kosu: str | None = None) -> dict[str, Any]:
    ex = kok / "runs/execution"
    kayit = ModDefteri(ex / "mod.json").oku()
    kosular = []
    for p in sorted(ex.glob("*/durum.json")) if ex.is_dir() else []:
        d = _json(p)
        if d is not None:
            d["_ad"] = p.parent.name
            kosular.append(d)
    kosular.sort(key=lambda d: int(d.get("zaman_ms", 0)), reverse=True)
    secili = next((d for d in kosular if d["_ad"] == kosu), kosular[0] if kosular else None)
    preflight = {}
    for p in sorted(ex.glob("preflight-*.json")) if ex.is_dir() else []:
        r = _json(p) or {}
        preflight[r.get("hedef", p.stem)] = {
            "gecti": r.get("gecti"),
            "zaman_utc": utc_str(r["zaman_ms"]) if r.get("zaman_ms") else None,
            "engeller": r.get("engeller", []),
            "hash": r.get("hash"),
        }
    r8 = kok / "config/r8_kriterler.json"
    r8_sha = r8_kriter_sha256(r8) if r8.is_file() else ""
    defter = kok / "docs/Hipotez-Defteri.jsonl"
    git = git_durumu(kok)
    promotion = None
    if secili is not None:
        strateji = (secili.get("kosu") or {}).get("strateji")
        pr = _json(kok / "runs/promotion" / f"{strateji}.json") if strateji else None
        promotion = (pr or {}).get("asama", "yok") if strateji else None
    return {
        "zaman_ms": simdi_ms(),
        "zaman_utc": utc_str(simdi_ms()),
        "sistem": {
            "mod": str(kayit.mod),
            "mod_bozuk": kayit.bozuk,
            "mod_gecmisi": kayit.gecmis[-6:],
            "commit": git.get("commit"),
            "dirty": git.get("dirty"),
            "preflight": preflight,
            "testler": _json(ex / "testler.json"),
            "r8": {
                "kriter_sozlesmesi": "dondurulmuş" if r8_sha.startswith(R8_KRITER_SHA256_ONEK)
                else "DEĞİŞMİŞ",
                "kriter_sha256": r8_sha[:16],
                "sonuc": (_json(kok / "config/operasyon_dogrulama.json") or {}).get("r8"),
            },
            "arastirma": {
                "askida": True,
                "karar": "K-111",
                "defter_satiri": sum(1 for _ in defter.open(encoding="utf-8"))
                if defter.is_file() else None,
            },
        },
        "kosular": [
            {"ad": d["_ad"], "mod": d.get("mod"), "halt": d.get("halt"),
             "safe_mode": d.get("safe_mode"), "zaman_utc": utc_str(int(d.get("zaman_ms", 0)))}
            for d in kosular
        ],
        "secili": secili,
        "promotion_asamasi": promotion,
        "jev": _jev(kok),
        "audit": {
            "kosu": _audit_son(ex / secili["_ad"] / "audit.sqlite") if secili else None,
            "global": _audit_son(kok / "runs/audit.sqlite", 8),
        },
    }


def uygulama(kok: Path) -> FastAPI:
    app = FastAPI(title="ScryneQuant execution panosu", docs_url=None, redoc_url=None)

    @app.get("/api/durum")
    def api_durum(kosu: str | None = None) -> JSONResponse:
        return JSONResponse(durum_topla(kok, kosu))

    @app.get("/", response_class=HTMLResponse)
    def sayfa() -> str:
        return SAYFA

    return app


SAYFA = """<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ScryneQuant · Execution</title>
<meta name="description" content="ScryneQuant execution panosu: mod, piyasa, strateji, risk, emirler, audit.">
<meta name="robots" content="noindex">
<style>
:root{
  --bg:#0A0C14;--surface:#12141E;--raised:#171A26;--sunken:#0D0F18;--border:#252A3A;
  --t1:#E8EAF0;--t2:#9AA1B4;--t3:#7C8397;--risk:#FF5A1F;--risk-s:#2A150C;--risk-b:#7A3312;
  --on-risk:#0A0C14;--up:#7FB5A2;--down:#C08B7D;--int:#8AA6E4;--int-s:#171C2E;
  --m-paper:#8AA6E4;--m-gozlem:#7C8397;
  --sans:"Fira Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  --mono:"Fira Code",ui-monospace,"Cascadia Mono",Consolas,monospace;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--t1);font:400 14px/1.5 var(--sans)}
header{position:sticky;top:0;z-index:10;display:flex;gap:12px;align-items:center;flex-wrap:wrap;
  padding:12px 16px;background:var(--surface);border-bottom:1px solid var(--border)}
h1{font:600 18px/1.3 var(--sans);margin:0}
h2{font:600 12px/1.4 var(--sans);letter-spacing:.06em;color:var(--t2);margin:0 0 8px}
.mod{font:600 14px/1 var(--mono);padding:8px 12px;border-radius:4px;border:1px solid var(--border);color:var(--t1)}
.mod[data-m="LIVE"]{background:var(--risk);color:var(--on-risk);border-color:var(--risk)}
.mod[data-m="LIVE_PENDING_APPROVAL"]{background:var(--risk-s);color:var(--risk);border-color:var(--risk-b)}
.mod[data-m="PAPER"]{color:var(--m-paper);border-color:var(--m-paper)}
.mod[data-m="SHADOW"],.mod[data-m="TESTNET"]{color:var(--int);border-color:var(--int)}
.mod[data-m="DISABLED"]{color:var(--t3)}
.meta{color:var(--t3);font:400 12px/1.35 var(--mono);overflow-wrap:anywhere}
main{display:grid;overflow-x:hidden;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:12px;padding:16px}
section{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:12px;min-width:0}
section.genis{grid-column:1/-1}
dl{display:grid;grid-template-columns:max-content 1fr;gap:2px 12px;margin:0}
dt{color:var(--t2);font:500 12px/1.4 var(--sans)}
dd{margin:0;font:400 13px/1.45 var(--mono);font-feature-settings:"tnum" 1,"zero" 1;overflow-wrap:anywhere}
.risk{color:var(--risk)}
.banner{background:var(--risk-s);border:1px solid var(--risk-b);color:var(--risk);border-radius:4px;padding:8px 12px;margin:0 16px}
.up{color:var(--up)} .down{color:var(--down)}
table{width:100%;border-collapse:collapse;font:400 12px/1.35 var(--mono);font-feature-settings:"tnum" 1,"zero" 1}
th{text-align:left;color:var(--t2);font:500 12px/1.4 var(--sans);border-bottom:1px solid var(--border);padding:4px 6px}
td{padding:4px 6px;border-bottom:1px solid var(--sunken);vertical-align:top;overflow-wrap:anywhere}
ul{margin:0;padding-left:18px} li{margin:2px 0}
select{background:var(--raised);color:var(--t1);border:1px solid var(--border);border-radius:4px;padding:4px 8px;font:inherit}
select:focus-visible{outline:2px solid var(--int);outline-offset:2px}
.bos{color:var(--t3)}
@media (max-width:420px){main{padding:8px;grid-template-columns:1fr}}
</style>
</head>
<body>
<header>
  <h1>ScryneQuant · Execution</h1>
  <span class="mod" id="mod" data-m="DISABLED" aria-live="polite">CURRENT MODE: —</span>
  <label class="meta" for="kosu">koşu</label>
  <select id="kosu" aria-label="Gösterilen koşu"></select>
  <span class="meta" id="saat"></span>
</header>
<div id="uyari" role="alert"></div>
<main>
  <section><h2>SYSTEM</h2><div id="system"></div></section>
  <section><h2>MARKET</h2><div id="market"></div></section>
  <section><h2>STRATEGY</h2><div id="strategy"></div></section>
  <section><h2>SIGNAL</h2><div id="signal"></div></section>
  <section><h2>PORTFOLIO</h2><div id="portfolio"></div></section>
  <section><h2>RISK</h2><div id="risk"></div></section>
  <section class="genis"><h2>ORDERS</h2><div id="orders"></div></section>
  <section class="genis"><h2>EXECUTION</h2><div id="execution"></div></section>
  <section><h2>JEV</h2><div id="jev"></div></section>
  <section class="genis"><h2>AUDIT</h2><div id="audit"></div></section>
</main>
<script>
const $=id=>document.getElementById(id);
const esc=v=>String(v??"—").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const sayi=(v,b=2)=>v==null||isNaN(v)?"—":Number(v).toLocaleString("tr-TR",{minimumFractionDigits:b,maximumFractionDigits:b});
const yuzde=v=>v==null?"—":sayi(v*100,2)+" %";
const yon=v=>v==null?"—":`<span class="${v>0?"up":v<0?"down":""}">${v>0?"+":v<0?"−":""}${sayi(Math.abs(v))}</span>`;
const utc=ms=>ms?new Date(ms).toISOString().replace("T"," ").slice(0,19)+" UTC":"—";
const dl=o=>"<dl>"+Object.entries(o).map(([k,v])=>`<dt>${esc(k)}</dt><dd>${v}</dd>`).join("")+"</dl>";
const tablo=(sut,satir)=>satir.length?`<table><thead><tr>${sut.map(s=>`<th scope="col">${esc(s)}</th>`).join("")}</tr></thead><tbody>${satir.map(r=>`<tr>${r.map(c=>`<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`:'<p class="bos">kayıt yok</p>';
let secili=null;
async function yenile(){
  let d;
  try{d=await (await fetch("/api/durum"+(secili?`?kosu=${encodeURIComponent(secili)}`:""))).json();}
  catch(e){$("uyari").innerHTML=`<p class="banner">Pano verisi okunamadı: ${esc(e)}. Sunucu çalışıyor mu? (sq execution pano)</p>`;return;}
  const s=d.sistem,k=d.secili||{};
  $("mod").dataset.m=s.mod;$("mod").textContent="CURRENT MODE: "+s.mod;
  $("saat").textContent="güncellendi "+d.zaman_utc;
  const sel=$("kosu");const adlar=d.kosular.map(x=>x.ad);
  if(sel.options.length!==adlar.length){sel.innerHTML=adlar.map(a=>`<option>${esc(a)}</option>`).join("");}
  if(k._ad)sel.value=k._ad;
  const uyarilar=[];
  if(s.mod_bozuk)uyarilar.push("Mod kaydı bozuk — DISABLED okunuyor: "+s.mod_bozuk);
  if(k.halt)uyarilar.push("HALT: "+k.halt);
  if(k.safe_mode)uyarilar.push("SAFE_MODE açık — yeni giriş yok (kaldırmak: sq execution safe-kaldir)");
  if(k.baglanti&&k.baglanti.ok===false)uyarilar.push("Borsa bağlantısı yok: "+k.baglanti.hata);
  if(s.r8.kriter_sozlesmesi!=="dondurulmuş")uyarilar.push("R8 kriter dosyası değişmiş (K-111)");
  const vt=k.veri_tazeligi||{};
  if(vt.son_bar_ms&&vt.beklenen_son_bar_ms&&vt.son_bar_ms<vt.beklenen_son_bar_ms)uyarilar.push("Bayat veri: son bar "+utc(vt.son_bar_ms)+", beklenen "+utc(vt.beklenen_son_bar_ms));
  $("uyari").innerHTML=uyarilar.map(u=>`<p class="banner">${esc(u)}</p>`).join("");
  const pf=Object.entries(s.preflight).map(([h,p])=>`${esc(h)}: ${p.gecti?"geçti":`<span class="risk">kapalı</span> (${p.engeller.map(e=>esc(e.ad)).join(", ")})`}`).join("<br>")||"—";
  $("system").innerHTML=dl({"mod":esc(s.mod),"commit":esc((s.commit||"").slice(0,10))+(s.dirty?' <span class="risk">kirli</span>':""),
    "testler":s.testler?esc(s.testler.ozet):"kayıt yok","R8 sözleşmesi":esc(s.r8.kriter_sozlesmesi)+" ("+esc(s.r8.kriter_sha256)+"…)",
    "R8 sonucu":s.r8.sonuc?esc(s.r8.sonuc.sonuc):"henüz yok (25 Eyl → 9 Eki, K-112)","araştırma":"askıda (K-111), defter "+esc(s.arastirma.defter_satiri),
    "kapılar":pf,"son geçişler":s.mod_gecmisi.map(g=>esc(g.zaman_utc)+" "+esc(g.nereden)+"→"+esc(g.nereye)).join("<br>")||"—"});
  const sb=k.son_bar||{};
  $("market").innerHTML=k._ad?dl({"sembol":esc(k.sembol),"son bar":utc(sb.open_time),"açılış / kapanış":sayi(sb.open)+" / "+sayi(sb.close),
    "kaynak":esc(sb.kaynak),"kapanıştan beri":vt.kapanistan_beri_ms==null?"—":sayi(vt.kapanistan_beri_ms/1000,0)+" s",
    "borsa bağlantısı":k.baglanti?(k.baglanti.ok?"açık, saat sapması "+esc(k.baglanti.saat_sapmasi_ms)+" ms":'<span class="risk">yok</span>'):"—"}):'<p class="bos">koşu yok — sq execution calistir</p>';
  const ks=k.kosu||{};
  $("strategy").innerHTML=k._ad?dl({"strateji":esc(ks.strateji),"parametreler":esc(JSON.stringify(ks.parametreler)),"koşu modu":esc(ks.mod),
    "risk modu":esc(ks.risk_modu)+(ks.risk_modu==="gozlem"?" (kanıt üretmez, K-035)":""),"promotion":esc(d.promotion_asamasi),"timeframe":esc(ks.timeframe)}):"—";
  const sk=k.son_karar||{};
  $("signal").innerHTML=sk.sinyal?dl({"bar":esc(sk.bar_utc),"yön / hedef":esc(sk.sinyal.yon)+" / "+yuzde(sk.sinyal.hedef),"sebep":esc(sk.sinyal.sebep),
    "risk kararı":esc(sk.risk&&sk.risk.karar)+(sk.risk&&sk.risk.sebep?" — "+esc(sk.risk.sebep):""),
    "execution":sk.execution?esc(sk.execution.sonuc)+(sk.execution.engel?" ("+esc(sk.execution.engel)+")":""):"—"}):'<p class="bos">henüz sinyal yok</p>';
  const h=k.hesap||{};
  $("portfolio").innerHTML=h.hata?`<p class="risk">${esc(h.hata)}</p>`:dl({"özkaynak":sayi(h.ozkaynak),"PnL":yon(h.pnl),"nakit":sayi(h.nakit),
    "pozisyon":sayi(h.miktar,6)+" @ "+sayi(h.fiyat),"maruziyet":yuzde(h.maruziyet),"drawdown":yuzde(h.drawdown),"günlük":yuzde(h.gunluk_getiri),
    "komisyon":sayi(h.komisyon_toplam),"bakiye (borsa)":Object.entries(k.bakiye||{}).map(([a,v])=>esc(a)+" "+sayi(v.toplam,6)).join(" · ")||"—"});
  const r=k.risk||{},rd=r.durum||{},lim=k.limitler||{};
  $("risk").innerHTML=dl({"SAFE_MODE (risk)":rd.safe_mode?'<span class="risk">açık — '+esc(rd.safe_mode_sebep)+"</span>":"kapalı",
    "SAFE_MODE (hat)":k.safe_mode?'<span class="risk">açık</span>':"kapalı","halt":k.halt?'<span class="risk">'+esc(k.halt)+"</span>":"yok",
    "sermaye tavanı":sayi(lim.sermaye_usdt),"azami maruziyet":yuzde(lim.azami_maruziyet),"günlük zarar / drawdown limiti":yuzde(lim.gunluk_zarar_limiti)+" / "+yuzde(lim.drawdown_limiti),
    "risk redleri":esc(JSON.stringify(r.red_sayimi||{}))});
  const em=k.emirler||{};
  $("orders").innerHTML=`<p class="meta">sayım ${esc(JSON.stringify(em.sayim||{}))} · açık ${esc(em.acik)} · belirsiz ${em.belirsiz?'<span class="risk">'+esc(em.belirsiz)+"</span>":"0"} · borsada açık ${esc((k.acik_emirler_borsa||[]).length)}</p>`+
    tablo(["kimlik","yön","tür","miktar","dolan","ort. fiyat","durum","karar","hata"],(em.son||[]).slice(0,20).map(e=>[esc(e.istemci_kimligi.slice(0,14))+"…",esc(e.yon),esc(e.tur),sayi(e.miktar,6),sayi(e.dolan_miktar,6),sayi(e.ortalama_fiyat),esc(e.durum),esc(e.karar_utc),esc(e.hata)]));
  const m=k.mutabakat||{},pm=k.pozisyon_mutabakati||{};
  $("execution").innerHTML=`<p class="meta">emir mutabakatı: incelenen ${esc(m.incelenen)}, çözülen ${esc((m.cozulen||[]).length)}, uyuşmazlık ${esc((m.uyusmazlik||[]).length)} · pozisyon mutabakatı: ${pm.halt?'<span class="risk">FARK</span>':"temiz"} · sayaç ${esc(JSON.stringify(k.sayac||{}))}</p>`+
    tablo(["karar","yön","onaylı","sonuç","engel","miktar","notional","kısıtlayan"],(k.son_kararlar||[]).slice(-15).reverse().map(u=>[esc(u.karar_utc),esc(u.yon),yuzde(u.onayli_maruziyet),esc(u.sonuc),esc(u.engel),sayi(u.miktar,6),sayi(u.notional),esc((u.kisitlayan||[]).join(","))]));
  const j=d.jev||{};
  $("jev").innerHTML=j.var?dl({"koşu":esc(j.kosu)+" ("+esc(j.mod)+")","model":esc(j.model),"karar / hata":esc(j.toplam)+" / "+esc(j.hata),
    "yön dağılımı":esc(JSON.stringify(j.yon_dagilimi)),"çekimserlik":yuzde(j.cekimserlik_orani),"son bar":esc(j.son_bar_utc),"not":esc(j.not)}):'<p class="bos">Jev gölge koşusu yok</p>';
  const a=d.audit||{},ka=a.kosu||{satirlar:[]};
  $("audit").innerHTML=`<p class="meta">koşu audit: ${esc(ka.toplam)} satır · global: ${esc((a.global||{}).toplam)} satır</p>`+
    tablo(["id","tür","zaman","olay","hash"],ka.satirlar.map(x=>[esc(x.id),esc(x.tur),utc(x.zaman_ms),esc(x.govde),esc(String(x.satir_hash).slice(0,12))]));
}
$("kosu").addEventListener("change",e=>{secili=e.target.value;yenile();});
yenile();setInterval(yenile,5000);
</script>
</body>
</html>
"""


__all__ = ["durum_topla", "uygulama"]
