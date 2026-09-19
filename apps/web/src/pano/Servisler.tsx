import { Link } from "react-router-dom";
import { cn, kisaZaman, useApi, yas } from "../lib";
import { Nokta, Rozet } from "../bilesenler/Ilkel";
import type { Servis, Servisler as ServisListesi } from "./tipler";

/** Tek ekranın ilk satırı: hangi süreç yaşıyor. Cevap üç değerli — çalışıyor, durmuş,
 *  **bilinmiyor** — ve üçüncüsü ikinciyle aynı renkte çizilmez: pid dosyası olmayan bir
 *  süreç "ölü" değil, "ölçülemedi"dir (K-024'ün ruhu). */
export function ServisSeridi() {
  const { veri } = useApi<ServisListesi>("/api/servisler", 20_000);
  if (!veri) return null;
  const kotu = veri.ozet.duran > 0;
  return (
    <section
      aria-label="Servisler"
      className={cn(
        "rounded-lg border px-lg py-md",
        kotu ? "border-risk-border bg-risk-surface" : "border-border bg-surface",
      )}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-md">
        <p className={cn("text-body font-medium", kotu ? "text-risk" : "text-primary")}>
          {kotu
            ? `${veri.ozet.duran} servis durmuş`
            : `${veri.ozet.yasayan}/${veri.ozet.toplam} servis çalışıyor`}
          {veri.ozet.bilinmeyen > 0 && (
            <span className="text-tertiary"> · {veri.ozet.bilinmeyen} bilinmiyor</span>
          )}
        </p>
        <Rozet ton="sessiz" title="Hiçbir süreç borsaya emir göndermiyor (K-074, K-035).">
          GERÇEK EMİR YOK
        </Rozet>
      </div>
      <ul className="mt-md grid gap-sm sm:grid-cols-2 lg:grid-cols-3">
        {veri.servisler.map((s) => (
          <ServisSatiri key={`${s.tur}-${s.ad}`} s={s} simdi={veri.zaman_ms} />
        ))}
      </ul>
    </section>
  );
}

function ServisSatiri({ s, simdi }: { s: Servis; simdi: number }) {
  const ton = s.yasiyor === false ? "risk" : s.yasiyor ? "iyi" : "sessiz";
  const durum = s.yasiyor === false ? "DURMUŞ" : s.yasiyor ? "Çalışıyor" : "Bilinmiyor";
  const baglanti =
    s.tur === "paper"
      ? `/kosu/${encodeURIComponent(s.ad)}`
      : s.tur === "jev"
        ? `/jev/${encodeURIComponent(s.ad)}`
        : null;
  return (
    <li className="flex items-start gap-sm rounded-md border border-border bg-surface-raised px-md py-sm">
      <span className="mt-[7px]">
        <Nokta ton={ton} />
      </span>
      <div className="min-w-0">
        <div className="flex flex-wrap items-baseline gap-xs">
          {baglanti ? (
            <Link
              to={baglanti}
              className="cursor-pointer text-body text-interactive underline decoration-border underline-offset-2 hover:decoration-interactive"
            >
              {s.ad}
            </Link>
          ) : (
            <span className="text-body text-primary">{s.ad}</span>
          )}
          <span className={cn("text-label", ton === "risk" ? "text-risk" : "text-tertiary")}>
            {durum}
          </span>
        </div>
        <p className="text-label text-tertiary">{s.aciklama}</p>
        <p className="rakam text-numeric-sm text-tertiary">
          {s.son_utc
            ? `son: ${s.son_utc.slice(5, 16)} UTC`
            : s.son_ms
              ? `son: ${kisaZaman(s.son_ms)} (${yas(s.son_ms, simdi)})`
              : "son: —"}
        </p>
      </div>
    </li>
  );
}
