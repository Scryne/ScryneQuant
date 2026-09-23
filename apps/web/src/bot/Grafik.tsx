import { useEffect, useMemo, useRef, useState } from "react";
import { AreaSeries, createChart, LineSeries, type IChartApi, type UTCTimestamp } from "lightweight-charts";
import { cn } from "../lib";
import { isaretliOran, KartBasligi, usdt } from "./parcalar";
import type { EgriNoktasi } from "./tipler";

const ARALIKLAR = [
  { ad: "Tümü", ms: null },
  { ad: "7 gün", ms: 7 * 86_400_000 },
  { ad: "24 saat", ms: 86_400_000 },
] as const;

/** Hesap değeri eğrisi. Yürütücü her saat başı bir nokta ekler (`egri.jsonl`). Nane alan dolgusu
 *  referansın grafiği; BTC fiyatı isteğe bağlı ikinci çizgi (sol eksen). Başlangıç sermayesi yatay
 *  kesikli çizgi: kâr mı zarar mı sorusu göz kararı değil, çizginin hangi tarafta olduğudur. */
export function Grafik({ egri, sermaye }: { egri: EgriNoktasi[]; sermaye: number | null }) {
  const [aralik, setAralik] = useState<(typeof ARALIKLAR)[number]["ad"]>("Tümü");
  const [btc, setBtc] = useState(false);
  const kap = useRef<HTMLDivElement>(null);
  const grafik = useRef<IChartApi | null>(null);

  const seri = useMemo(() => {
    const ms = ARALIKLAR.find((a) => a.ad === aralik)?.ms ?? null;
    if (ms == null || !egri.length) return egri;
    const sinir = (egri.at(-1)?.bar_ms ?? 0) - ms;
    return egri.filter((n) => n.bar_ms >= sinir);
  }, [egri, aralik]);

  useEffect(() => {
    if (!kap.current || seri.length < 2) return;
    const stil = getComputedStyle(document.documentElement);
    const renk = (ad: string, yedek: string) => stil.getPropertyValue(ad).trim() || yedek;
    const mint = renk("--color-bot-mint", "#2FE3A0");
    const g = createChart(kap.current, {
      autoSize: true,
      layout: {
        background: { color: "transparent" },
        textColor: renk("--color-bot-text-3", "#7C8C86"),
        fontFamily: "Fira Code, ui-monospace, monospace",
        fontSize: 11,
        attributionLogo: false,
      },
      grid: { vertLines: { visible: false }, horzLines: { color: renk("--color-bot-line", "#1F2A27") } },
      rightPriceScale: { borderVisible: false },
      leftPriceScale: { visible: btc, borderVisible: false },
      timeScale: { borderVisible: false, timeVisible: true, secondsVisible: false },
      crosshair: {
        vertLine: { color: renk("--color-bot-line-strong", "#2C3935"), labelBackgroundColor: renk("--color-bot-surface-3", "#1A2320") },
        horzLine: { color: renk("--color-bot-line-strong", "#2C3935"), labelBackgroundColor: renk("--color-bot-surface-3", "#1A2320") },
      },
      localization: {
        locale: "tr-TR",
        priceFormatter: (p: number) => p.toLocaleString("tr-TR", { maximumFractionDigits: 2 }),
      },
      handleScale: false,
      handleScroll: false,
    });
    grafik.current = g;

    const alan = g.addSeries(AreaSeries, {
      lineColor: mint,
      lineWidth: 2,
      topColor: `${mint}55`,
      bottomColor: `${mint}00`,
      priceLineVisible: false,
      lastValueVisible: true,
    });
    alan.setData(seri.map((n) => ({ time: Math.floor(n.bar_ms / 1000) as UTCTimestamp, value: n.ozkaynak })));
    if (sermaye != null) {
      alan.createPriceLine({
        price: sermaye,
        color: renk("--color-bot-text-3", "#7C8C86"),
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: false,
        title: "başlangıç",
      });
    }
    if (btc) {
      const cizgi = g.addSeries(LineSeries, {
        color: renk("--color-bot-text-2", "#9FAEA8"),
        lineWidth: 1,
        priceScaleId: "left",
        priceLineVisible: false,
        lastValueVisible: false,
      });
      cizgi.setData(seri.map((n) => ({ time: Math.floor(n.bar_ms / 1000) as UTCTimestamp, value: n.fiyat })));
    }
    g.timeScale().fitContent();
    return () => {
      g.remove();
      grafik.current = null;
    };
  }, [seri, sermaye, btc]);

  const son = seri.at(-1)?.ozkaynak ?? null;
  const ilk = seri.at(0)?.ozkaynak ?? null;
  const degisim = son != null && ilk ? son / ilk - 1 : null;

  return (
    <section aria-labelledby="grafik-baslik" className="kart flex h-full min-h-[380px] flex-col gap-4 p-6">
      <KartBasligi
        id="grafik-baslik"
        baslik="Hesap değeri"
        alt={
          seri.length >= 2
            ? `Seçili aralıkta ${isaretliOran(degisim)} · son ${usdt(son)} USDT`
            : "Saatlik kapanışlarla dolar"
        }
        sag={
          <div className="flex items-center gap-2">
            <div role="group" aria-label="Zaman aralığı" className="flex rounded-full bg-bot-surface-2 p-1">
              {ARALIKLAR.map((a) => (
                <button
                  key={a.ad}
                  type="button"
                  aria-pressed={aralik === a.ad}
                  onClick={() => setAralik(a.ad)}
                  className={cn(
                    "min-h-7 rounded-full px-3 text-[12px] font-semibold transition-colors duration-150",
                    aralik === a.ad ? "bg-bot-mint text-bot-mint-ink" : "text-bot-text-2 hover:text-bot-text",
                  )}
                >
                  {a.ad}
                </button>
              ))}
            </div>
            <button
              type="button"
              aria-pressed={btc}
              onClick={() => setBtc((b) => !b)}
              className={cn(
                "hidden min-h-9 rounded-full border px-3 text-[12px] font-semibold transition-colors duration-150 sm:block",
                btc ? "border-bot-text-2 text-bot-text" : "border-bot-line text-bot-text-2 hover:text-bot-text",
              )}
            >
              BTC fiyatı
            </button>
          </div>
        }
      />
      {seri.length >= 2 ? (
        <figure className="m-0 flex flex-1 flex-col">
          <div
            ref={kap}
            className="min-h-[260px] flex-1"
            role="img"
            aria-label={`Hesap değeri grafiği, ${seri.length} saatlik nokta, son değer ${usdt(son)} USDT`}
          />
          <figcaption className="mt-2 text-[12px] text-bot-text-3">
            Kesikli çizgi başlangıç sermayesi{btc ? " · gri çizgi BTC fiyatı (sol eksen)" : ""}
          </figcaption>
        </figure>
      ) : (
        <div className="flex flex-1 items-center justify-center rounded-2xl border border-dashed border-bot-line-strong p-8 text-center">
          <div className="w-full max-w-[24rem]">
            <p className="font-semibold text-bot-text-2">Grafik ilk saatlerde dolacak</p>
            <p className="mt-1 text-[13px] text-pretty text-bot-text-3">
              Bot her saat başı kapanışta bir nokta ekler. İki noktadan sonra eğri burada görünür.
            </p>
          </div>
        </div>
      )}
    </section>
  );
}
