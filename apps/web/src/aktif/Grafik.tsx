import { useEffect, useMemo, useRef, useState } from "react";
import { AreaSeries, createChart, type UTCTimestamp } from "lightweight-charts";
import { cn } from "../lib";
import { isaretliOran, KartBasligi, usdt } from "../bot/parcalar";
import type { EgriNoktasi } from "./tipler";

const ARALIKLAR = [
  { ad: "Tümü", ms: null },
  { ad: "7 gün", ms: 7 * 86_400_000 },
  { ad: "24 saat", ms: 86_400_000 },
] as const;

/** Hesap değeri eğrisi (her bar kapanışı turu bir nokta). Başlangıç sermayesi kesikli çizgi:
 *  kâr mı zarar mı sorusu, eğrinin çizginin hangi tarafında olduğudur. */
export function Grafik({
  egri,
  sermaye,
  birim,
}: {
  egri: EgriNoktasi[];
  sermaye: number | null;
  birim: string;
}) {
  const [aralik, setAralik] = useState<(typeof ARALIKLAR)[number]["ad"]>("Tümü");
  const kap = useRef<HTMLDivElement>(null);

  const seri = useMemo(() => {
    const ms = ARALIKLAR.find((a) => a.ad === aralik)?.ms ?? null;
    if (ms == null || !egri.length) return egri;
    const sinir = (egri.at(-1)?.t ?? 0) - ms;
    return egri.filter((n) => n.t >= sinir);
  }, [egri, aralik]);

  useEffect(() => {
    if (!kap.current || seri.length < 2) return;
    const stil = getComputedStyle(document.documentElement);
    const renk = (ad: string, yedek: string) => stil.getPropertyValue(ad).trim() || yedek;
    const mint = renk("--color-bot-mint", "#2FE3A0");
    const cizgi = renk("--color-bot-line-strong", "#2C3935");
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
      timeScale: { borderVisible: false, timeVisible: true, secondsVisible: false },
      crosshair: {
        vertLine: { color: cizgi, labelBackgroundColor: renk("--color-bot-surface-3", "#1A2320") },
        horzLine: { color: cizgi, labelBackgroundColor: renk("--color-bot-surface-3", "#1A2320") },
      },
      localization: {
        locale: "tr-TR",
        priceFormatter: (p: number) => p.toLocaleString("tr-TR", { maximumFractionDigits: 2 }),
      },
      handleScale: false,
      handleScroll: false,
    });
    const alan = g.addSeries(AreaSeries, {
      lineColor: mint,
      lineWidth: 2,
      topColor: `${mint}55`,
      bottomColor: `${mint}00`,
      priceLineVisible: false,
      lastValueVisible: true,
    });
    // Aynı saniyeye düşen iki nokta grafiği kırar; son değer kalır.
    const noktalar = new Map<number, number>();
    for (const n of seri) noktalar.set(Math.floor(n.t / 1000), n.v);
    alan.setData([...noktalar].map(([t, v]) => ({ time: t as UTCTimestamp, value: v })));
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
    g.timeScale().fitContent();
    return () => g.remove();
  }, [seri, sermaye]);

  const son = seri.at(-1)?.v ?? null;
  const ilk = seri.at(0)?.v ?? null;
  const degisim = son != null && ilk ? son / ilk - 1 : null;

  return (
    <section aria-labelledby="grafik-baslik" className="kart flex h-full min-h-[380px] flex-col gap-4 p-6">
      <KartBasligi
        id="grafik-baslik"
        baslik="Hesap değeri"
        alt={
          seri.length >= 2
            ? `Seçili aralıkta ${isaretliOran(degisim)} · son ${usdt(son)} ${birim}`
            : "Her bar kapanışında bir nokta eklenir"
        }
        sag={
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
        }
      />
      {seri.length >= 2 ? (
        <figure className="m-0 flex flex-1 flex-col">
          <div
            ref={kap}
            className="min-h-[260px] flex-1"
            role="img"
            aria-label={`Hesap değeri grafiği, ${seri.length} nokta, son değer ${usdt(son)} ${birim}`}
          />
          <figcaption className="mt-2 text-[12px] text-bot-text-3">Kesikli çizgi başlangıç sermayesi</figcaption>
        </figure>
      ) : (
        <div className="flex flex-1 items-center justify-center rounded-2xl border border-dashed border-bot-line-strong p-8 text-center">
          <div className="w-full max-w-[24rem]">
            <p className="font-semibold text-bot-text-2">Grafik ilk barlarda dolacak</p>
            <p className="mt-1 text-[13px] text-pretty text-bot-text-3">
              Bot her bar kapanışında hesap değerini kaydeder. İki kayıttan sonra eğri burada görünür.
            </p>
          </div>
        </div>
      )}
    </section>
  );
}
