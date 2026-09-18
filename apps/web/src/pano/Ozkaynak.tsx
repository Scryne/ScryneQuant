import { useEffect, useRef } from "react";
import { createChart, LineSeries, type IChartApi } from "lightweight-charts";
import type { SeriNoktasi } from "./tipler";

/** Özkaynak eğrisi.
 *
 *  Tek çizgi, ızgara ve iki eksen — daha fazlası değil. Başlangıç sermayesi yatay bir
 *  referans çizgisi olarak duruyor: "kâr mı zarar mı" sorusunun cevabı göz kararı değil,
 *  çizginin hangi tarafta olduğudur. Renk tek başına anlam taşımıyor (DESIGN.md); yön
 *  başlıktaki işaretli yüzdede yazılı.
 *
 *  Grafik `lightweight-charts` ile: bağımlılık zaten projede ve canvas'a çiziyor, yani
 *  yüzlerce noktada DOM şişmiyor.
 */
export function OzkaynakGrafigi({
  seri,
  sermaye,
  etiket = "Özkaynak",
}: {
  seri: SeriNoktasi[];
  sermaye: number | null;
  etiket?: string;
}) {
  const kap = useRef<HTMLDivElement>(null);
  const grafik = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!kap.current) return;
    const stil = getComputedStyle(document.documentElement);
    const renk = (ad: string, yedek: string) =>
      stil.getPropertyValue(ad).trim() || yedek;

    const g = createChart(kap.current, {
      height: 260,
      autoSize: true,
      layout: {
        background: { color: "transparent" },
        textColor: renk("--color-tertiary", "#7C8397"),
        fontFamily: "Fira Code, ui-monospace, monospace",
        fontSize: 11,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: renk("--color-chart-grid", "#1C2030") },
        horzLines: { color: renk("--color-chart-grid", "#1C2030") },
      },
      rightPriceScale: { borderColor: renk("--color-border", "#252A3A") },
      timeScale: {
        borderColor: renk("--color-border", "#252A3A"),
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: { mode: 0 },
      handleScale: false,
      handleScroll: false,
    });
    grafik.current = g;

    const cizgi = g.addSeries(LineSeries, {
      color: renk("--color-chart-line", "#9AA1B4"),
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
    });
    /* Aynı saniyeye düşen iki nokta kütüphaneyi kırar; koşu 1h ızgarasında olsa da
       tek sembollü koşunun serisi fill anlarından geliyor ve çakışabilir. */
    const gorulen = new Set<number>();
    cizgi.setData(
      seri
        .map((n) => ({ time: Math.floor(n.ms / 1000), value: n.ozkaynak }))
        .filter((n) => !gorulen.has(n.time) && gorulen.add(n.time))
        .sort((a, b) => a.time - b.time) as never,
    );

    if (sermaye != null && Number.isFinite(sermaye)) {
      cizgi.createPriceLine({
        price: sermaye,
        color: renk("--color-chart-benchmark", "#5C6478"),
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: "başlangıç",
      });
    }
    g.timeScale().fitContent();

    const boyut = new ResizeObserver(() => g.timeScale().fitContent());
    boyut.observe(kap.current);
    return () => {
      boyut.disconnect();
      g.remove();
      grafik.current = null;
    };
  }, [seri, sermaye]);

  if (!seri.length) {
    return (
      <p className="py-lg text-center text-label text-tertiary">
        Özkaynak serisi henüz yok.
      </p>
    );
  }
  return (
    <figure className="m-0">
      <div ref={kap} role="img" aria-label={`${etiket} eğrisi, ${seri.length} nokta`} />
      <figcaption className="mt-sm text-label text-tertiary">
        {seri.length} nokta · yatay çizgi başlangıç sermayesi
      </figcaption>
    </figure>
  );
}
