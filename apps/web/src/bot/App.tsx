import { useCallback, useMemo, useState } from "react";
import { AlertTriangle, ArrowLeftRight, ChevronsRight, LayoutGrid, RefreshCw, Server, ShieldCheck } from "lucide-react";
import { cn, useApi, yas } from "../lib";
import { Bakiye } from "./Bakiye";
import { Denge } from "./Denge";
import { Emirler } from "./Emirler";
import { Grafik } from "./Grafik";
import { Kosular } from "./Kosular";
import { DurumNoktasi, fiyat, Iskelet, kosuAdi, kosuSagligi, ModRozeti } from "./parcalar";
import { Pilot } from "./Pilot";
import { Risk } from "./Risk";
import { Sistem } from "./Sistem";
import type { BotYaniti } from "./tipler";

const YENILEME_MS = 15_000;

function ilkSecim(): string | null {
  return new URLSearchParams(window.location.search).get("kosu");
}

export function App() {
  const [secim, setSecim] = useState<string | null>(ilkSecim);
  const yol = secim ? `/api/bot?kosu=${encodeURIComponent(secim)}` : "/api/bot";
  const { veri, hata, tazele } = useApi<BotYaniti>(yol, YENILEME_MS);

  const sec = useCallback((ad: string) => {
    setSecim(ad);
    const url = new URL(window.location.href);
    url.searchParams.set("kosu", ad);
    window.history.replaceState(null, "", url);
  }, []);

  const s = veri?.secili ?? null;
  const ozet = useMemo(() => veri?.kosular.find((k) => k.ad === s?.ad) ?? null, [veri, s]);

  return (
    <div className="flex min-h-dvh">
      <Ray />
      <div className="flex min-w-0 flex-1 flex-col">
        <Ust veri={veri} secili={s?.ad ?? null} sec={sec} tazele={tazele} />
        <main className="mx-auto w-full max-w-[1480px] flex-1 px-4 pt-4 pb-10 sm:px-6 lg:px-8">
          {hata ? (
            <div role="alert" className="mb-4 flex items-start gap-2 rounded-2xl border border-bot-risk/40 bg-bot-risk-surface px-4 py-3 text-[13px] text-bot-risk">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
              <span>
                Veri alınamadı: {hata}. Ekrandaki sayılar son başarılı okumadan. Sunucu çalışıyor mu:{" "}
                <span className="sayi">sq execution pano</span>
              </span>
            </div>
          ) : null}
          {ozet ? <RiskSeridi saglik={kosuSagligi(ozet)} halt={ozet.halt} safe={ozet.safe_mode} yasMs={ozet.veri_yasi_ms} /> : null}

          {!veri || !s ? (
            veri && !s ? (
              <BosEkran />
            ) : (
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
                <Iskelet className="h-64 lg:col-span-5" />
                <Iskelet className="h-64 lg:col-span-4" />
                <Iskelet className="h-64 lg:col-span-3" />
                <Iskelet className="h-96 lg:col-span-8" />
                <Iskelet className="h-96 lg:col-span-4" />
              </div>
            )
          ) : (
            <div id="ozet" className="grid scroll-mt-24 grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-12">
              <div className="md:col-span-2 lg:col-span-5">
                <Bakiye s={s} />
              </div>
              <div className="lg:col-span-4">
                <Denge d={s.denge} sembol={s.kosu.sembol} />
              </div>
              <div className="lg:col-span-3">
                <Pilot v={veri} />
              </div>
              <div className="md:col-span-2 lg:col-span-8">
                <Grafik egri={s.egri} sermaye={s.kosu.sermaye_usdt ?? null} />
              </div>
              <div className="md:col-span-2 lg:col-span-4">
                <Emirler emirler={s.emirler} strateji={s.kosu.strateji} />
              </div>
              <div className="lg:col-span-5">
                <Risk s={s} pilot={veri.pilot} />
              </div>
              <div className="lg:col-span-4">
                <Kosular kosular={veri.kosular} secili={s.ad} sec={sec} />
              </div>
              <div className="md:col-span-2 lg:col-span-3">
                <Sistem v={veri} kosu={s.ad} />
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

const GEZINME = [
  { href: "#ozet", ad: "Özet", ikon: LayoutGrid },
  { href: "#emirler", ad: "Emirler", ikon: ArrowLeftRight },
  { href: "#risk", ad: "Risk", ikon: ShieldCheck },
  { href: "#kosular", ad: "Koşular", ikon: Server },
] as const;

function Ray() {
  return (
    <nav
      aria-label="Bölümler"
      className="sticky top-0 hidden h-dvh w-[76px] shrink-0 flex-col items-center gap-2 border-r border-bot-line py-5 md:flex"
      style={{ zIndex: "var(--z-gezinme)" }}
    >
      <a href="#ozet" aria-label="ScryneQuant, başa dön" className="mb-5 grid size-11 place-items-center rounded-2xl bg-bot-mint text-bot-mint-ink">
        <svg viewBox="0 0 32 32" className="size-6" aria-hidden>
          <path d="M8 22h16M10 22V14h4v8M18 22V9h4v13" stroke="currentColor" strokeWidth="2.6" fill="none" strokeLinejoin="round" />
        </svg>
      </a>
      {GEZINME.map(({ href, ad, ikon: Ikon }) => (
        <a
          key={href}
          href={href}
          aria-label={ad}
          title={ad}
          className="grid size-11 place-items-center rounded-xl text-bot-text-3 transition-colors duration-150 hover:bg-bot-surface-2 hover:text-bot-text"
        >
          <Ikon className="size-5" aria-hidden />
        </a>
      ))}
    </nav>
  );
}

function Ust({
  veri,
  secili,
  sec,
  tazele,
}: {
  veri: BotYaniti | null;
  secili: string | null;
  sec: (ad: string) => void;
  tazele: () => void;
}) {
  const aktif = veri?.kosular.filter((k) => k.canli && !k.kapatildi) ?? [];
  const secenekler = secili && !aktif.some((k) => k.ad === secili) ? [...aktif, ...(veri?.kosular.filter((k) => k.ad === secili) ?? [])] : aktif;
  const s = veri?.secili;
  return (
    <header
      className="sticky top-0 border-b border-bot-line bg-bot-bg/85 backdrop-blur-md supports-[backdrop-filter]:bg-bot-bg/70"
      style={{ zIndex: "var(--z-yapiskan)", paddingTop: "env(safe-area-inset-top)" }}
    >
      <div className="mx-auto flex min-h-16 w-full max-w-[1480px] flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 sm:px-6 lg:px-8">
        <div className="flex items-center gap-2 text-[15px] font-semibold">
          <span className="grid size-8 place-items-center rounded-xl bg-bot-mint text-bot-mint-ink md:hidden" aria-hidden>
            <svg viewBox="0 0 32 32" className="size-5">
              <path d="M8 22h16M10 22V14h4v8M18 22V9h4v13" stroke="currentColor" strokeWidth="2.8" fill="none" strokeLinejoin="round" />
            </svg>
          </span>
          <ChevronsRight className="hidden size-4 text-bot-text-3 md:block" aria-hidden />
          <h1 className="text-bot-text">Bot paneli</h1>
        </div>

        <label className="ml-auto flex items-center gap-2 text-[12.5px] text-bot-text-3 sm:ml-4">
          <span className="hidden sm:inline">Koşu</span>
          <select
            value={secili ?? ""}
            onChange={(e) => sec(e.target.value)}
            className="min-h-9 max-w-[210px] cursor-pointer rounded-full border border-bot-line bg-bot-surface px-3 text-[13px] font-semibold text-bot-text hover:border-bot-line-strong"
          >
            {secenekler.map((k) => (
              <option key={k.ad} value={k.ad}>
                {kosuAdi(k.ad)}
              </option>
            ))}
          </select>
        </label>

        <div className="flex items-center gap-2 sm:ml-auto">
          {s?.hesap.fiyat ? (
            <span className="sayi hidden rounded-full border border-bot-line bg-bot-surface px-3 py-1.5 text-[12.5px] text-bot-text sm:inline">
              BTC {fiyat(s.hesap.fiyat)}
            </span>
          ) : null}
          {s ? <ModRozeti mod={s.mod} /> : null}
          <button
            type="button"
            onClick={tazele}
            className="flex min-h-9 items-center gap-2 rounded-full border border-bot-line bg-bot-surface px-3 text-[12px] text-bot-text-2 transition-colors duration-150 hover:border-bot-line-strong hover:text-bot-text"
          >
            <RefreshCw className="size-3.5" aria-hidden />
            <span className="sayi">{veri ? yas(veri.zaman_ms) : "yükleniyor"}</span>
            <span className="sr-only">Şimdi yenile</span>
          </button>
        </div>
      </div>
    </header>
  );
}

/** Risk şeridi: her zaman aynı yerde. Sorun yoksa da görünür ("sorun yok" bir bilgidir). */
function RiskSeridi({
  saglik,
  halt,
  safe,
  yasMs,
}: {
  saglik: ReturnType<typeof kosuSagligi>;
  halt: string;
  safe: boolean;
  yasMs: number | null;
}) {
  const risk = saglik === "risk";
  const metin = halt
    ? `Bot durduruldu: ${halt}`
    : safe
      ? "SAFE_MODE açık: bot yeni pozisyon açmıyor"
      : risk
        ? `Veri bayat: son bar ${yasMs != null ? Math.round(yasMs / 60000) : "?"} dakika önce kapandı`
        : saglik === "durgun"
          ? "Bu koşunun süreci çalışmıyor; gösterilen son kayıt"
          : "Bot çalışıyor, risk durumu normal";
  return (
    <div
      role={risk ? "alert" : "status"}
      className={cn(
        "mb-4 flex items-center gap-2.5 rounded-2xl border px-4 py-2.5 text-[13px]",
        risk ? "border-bot-risk/40 bg-bot-risk-surface text-bot-risk" : "border-bot-line bg-bot-surface text-bot-text-2",
      )}
    >
      {risk ? <AlertTriangle className="size-4 shrink-0" aria-hidden /> : <DurumNoktasi saglik={saglik} etiket={saglik === "iyi" ? "çalışıyor" : "durmuş"} />}
      <span className="text-pretty">{metin}</span>
    </div>
  );
}

function BosEkran() {
  return (
    <div className="kart grid place-items-center p-10 text-center">
      <div className="w-full max-w-md">
        <p className="font-bot-title text-bot-title font-semibold">Henüz koşu yok</p>
        <p className="mt-1 text-[13px] text-pretty text-bot-text-3">
          Gözetmen görevini başlat ya da bir koşu aç:{" "}
          <span className="sayi">sq execution calistir --mod testnet --kosu urun-testnet --strateji sabit_oran --sermaye 100</span>
        </p>
      </div>
    </div>
  );
}
