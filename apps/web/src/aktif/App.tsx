import { useCallback, useState } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { cn, useApi, yas } from "../lib";
import { DurumNoktasi, Iskelet, isaretliOran, usdt } from "../bot/parcalar";
import { Grafik } from "./Grafik";
import { Ayar, Islemler, Karne, Olaylar, Pozisyonlar } from "./Tablolar";
import type { AktifYaniti, HesapOzeti } from "./tipler";

const YENILEME_MS = 15_000;

const HESAP_ADI: Record<string, { ad: string; piyasa: string }> = {
  "kripto-trend": { ad: "Kripto · Trend", piyasa: "10 coin" },
  "kripto-kirilim": { ad: "Kripto · Kırılım", piyasa: "10 coin" },
  "kripto-donus": { ad: "Kripto · Dönüş", piyasa: "10 coin" },
  "mt5-demo": { ad: "MT5 · FX ve endeks", piyasa: "7 parite, altın, S&P, Nasdaq, Dow" },
};

function hesapAdi(ad: string) {
  return HESAP_ADI[ad] ?? { ad, piyasa: "" };
}

function ilkSecim(): string | null {
  return new URLSearchParams(window.location.search).get("hesap");
}

/** Bir hesabın başlangıçtan bu yana değişimi. */
function toplamDegisim(h: HesapOzeti): number | null {
  return h.ozkaynak != null && h.sermaye ? h.ozkaynak / h.sermaye - 1 : null;
}

function renk(o: number | null) {
  return o == null || o === 0 ? "text-bot-text-2" : o > 0 ? "text-bot-mint" : "text-bot-down";
}

export function App() {
  const { veri, hata, tazele } = useApi<AktifYaniti>("/api/aktif", YENILEME_MS);
  const [secim, setSecim] = useState<string | null>(ilkSecim);

  const sec = useCallback((ad: string) => {
    setSecim(ad);
    const url = new URL(window.location.href);
    url.searchParams.set("hesap", ad);
    window.history.replaceState(null, "", url);
  }, []);

  const hesaplar = veri?.hesaplar ?? [];
  const secili = hesaplar.find((h) => h.ad === secim) ?? hesaplar[0] ?? null;
  const duran = hesaplar.filter((h) => h.var && !h.calisiyor && !h.kapali);

  return (
    <div className="flex min-h-dvh flex-col">
      <header
        className="sticky top-0 border-b border-bot-line bg-bot-bg/85 backdrop-blur-md supports-[backdrop-filter]:bg-bot-bg/70"
        style={{ zIndex: "var(--z-yapiskan)", paddingTop: "env(safe-area-inset-top)" }}
      >
        <div className="mx-auto flex min-h-16 w-full max-w-[1480px] flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 sm:px-6 lg:px-8">
          <div className="flex items-center gap-2.5">
            <span className="grid size-8 place-items-center rounded-xl bg-bot-mint text-bot-mint-ink" aria-hidden>
              <svg viewBox="0 0 32 32" className="size-5">
                <path d="M8 22h16M10 22V14h4v8M18 22V9h4v13" stroke="currentColor" strokeWidth="2.8" fill="none" strokeLinejoin="round" />
              </svg>
            </span>
            <h1 className="text-[15px] font-semibold text-balance text-bot-text">Demo botlar</h1>
            <span className="rounded-full border border-bot-line-strong bg-bot-surface-2 px-2 py-0.5 text-[11px] font-semibold text-bot-text-2">
              Demo · gerçek para yok
            </span>
          </div>
          <button
            type="button"
            onClick={tazele}
            className="ml-auto flex min-h-9 items-center gap-2 rounded-full border border-bot-line bg-bot-surface px-3 text-[12px] text-bot-text-2 transition-colors duration-150 hover:border-bot-line-strong hover:text-bot-text"
          >
            <RefreshCw className="size-3.5" aria-hidden />
            <span className="sayi">{veri ? yas(veri.zaman_ms) : "yükleniyor"}</span>
            <span className="sr-only">Şimdi yenile</span>
          </button>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1480px] flex-1 px-4 pt-4 pb-10 sm:px-6 lg:px-8">
        {hata ? (
          <div role="alert" className="mb-4 flex items-start gap-2 rounded-2xl border border-bot-risk/40 bg-bot-risk-surface px-4 py-3 text-[13px] text-bot-risk">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
            <span className="text-pretty">
              Veri alınamadı: {hata}. Ekrandaki sayılar son başarılı okumadan. Pano sunucusunu başlatmak için:{" "}
              <span className="sayi">sq execution pano</span>
            </span>
          </div>
        ) : null}

        {veri ? (
          <div
            role={duran.length ? "alert" : "status"}
            className={cn(
              "mb-4 flex items-center gap-2.5 rounded-2xl border px-4 py-2.5 text-[13px]",
              duran.length ? "border-bot-risk/40 bg-bot-risk-surface text-bot-risk" : "border-bot-line bg-bot-surface text-bot-text-2",
            )}
          >
            {duran.length ? <AlertTriangle className="size-4 shrink-0" aria-hidden /> : <DurumNoktasi saglik="iyi" etiket="çalışıyor" />}
            <span className="text-pretty">
              {duran.length
                ? `${duran.map((h) => hesapAdi(h.ad).ad).join(", ")} durmuş görünüyor. Gözetmen 10 dakika içinde yeniden başlatır; sürerse: sq aktif calistir --hesap ${duran[0]?.ad ?? ""}`
                : `${hesaplar.filter((h) => h.calisiyor).length} bot çalışıyor · simüle hesaplar, gerçek para yok`}
            </span>
          </div>
        ) : null}

        {!veri ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <Iskelet key={i} className="h-40" />
            ))}
            <Iskelet className="h-96 sm:col-span-2 xl:col-span-4" />
          </div>
        ) : !hesaplar.length ? (
          <div className="kart p-10 text-center text-[13px] text-bot-text-3">
            Tanımlı hesap yok. <span className="sayi">config/aktif.json</span> dosyasına bir hesap ekle.
          </div>
        ) : (
          <>
            <div role="group" aria-label="Bot hesapları" className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {hesaplar.map((h) => (
                <HesapKarti key={h.ad} h={h} secili={secili?.ad === h.ad} sec={sec} />
              ))}
            </div>
            {secili ? <Detay h={secili} risk={veri.risk} /> : null}
          </>
        )}
      </main>
    </div>
  );
}

function HesapKarti({ h, secili, sec }: { h: HesapOzeti; secili: boolean; sec: (ad: string) => void }) {
  const ad = hesapAdi(h.ad);
  const toplam = toplamDegisim(h);
  const hafta = h.fren?.hafta_getiri ?? null;
  const durum = !h.var ? "henüz başlamadı" : h.kapali ? "kapatıldı" : h.calisiyor ? "çalışıyor" : "durmuş";
  return (
    <button
      type="button"
      aria-pressed={secili}
      onClick={() => sec(h.ad)}
      className={cn(
        "kart flex flex-col gap-3 p-5 text-left transition-colors duration-150",
        secili ? "border-bot-mint/60 bg-bot-surface-2" : "hover:border-bot-line-strong",
      )}
    >
      <div className="flex w-full items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-semibold text-bot-text">{ad.ad}</p>
          <p className="truncate text-[12px] text-bot-text-3">{ad.piyasa}</p>
        </div>
        <span className="flex shrink-0 items-center gap-1.5 text-[11.5px] text-bot-text-3">
          <DurumNoktasi saglik={h.calisiyor ? "iyi" : h.var && !h.kapali ? "risk" : "durgun"} etiket={durum} />
          {durum}
        </span>
      </div>
      <div>
        <p className="sayi text-[22px] leading-tight font-semibold text-bot-text">
          {usdt(h.ozkaynak)} <span className="text-[13px] font-medium text-bot-text-3">{h.para_birimi}</span>
        </p>
        <p className={cn("sayi text-[13px] font-semibold", renk(toplam))}>
          {isaretliOran(toplam)} <span className="font-normal text-bot-text-3">başlangıçtan beri</span>
        </p>
      </div>
      <div className="flex w-full items-center justify-between border-t border-bot-line pt-2 text-[12px]">
        <span className="text-bot-text-3">
          Bu hafta <span className={cn("sayi font-semibold", renk(hafta))}>{isaretliOran(hafta)}</span>
        </span>
        <span className="sayi text-bot-text-3">{h.hafta_islem} işlem</span>
      </div>
    </button>
  );
}

function Detay({ h, risk }: { h: HesapOzeti; risk: Record<string, number> }) {
  const birimAdi = h.para_birimi === "USD" ? "lot" : "adet";
  return (
    <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-12">
      <div className="lg:col-span-8">
        <Grafik egri={h.egri} sermaye={h.sermaye} birim={h.para_birimi} />
      </div>
      <div className="lg:col-span-4">
        <Pozisyonlar p={h.pozisyonlar} birimAdi={birimAdi} />
      </div>
      <div className="lg:col-span-8">
        <Islemler islemler={h.islemler} birim={h.para_birimi} birimAdi={birimAdi} />
      </div>
      <div className="flex flex-col gap-4 lg:col-span-4">
        <Karne karne={h.karne} />
        <Ayar h={h} risk={risk} />
      </div>
      {h.olaylar.length ? (
        <div className="lg:col-span-12">
          <Olaylar olaylar={h.olaylar} />
        </div>
      ) : null}
    </div>
  );
}
