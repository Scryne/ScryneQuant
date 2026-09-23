import { ArrowDownLeft, ArrowUpRight } from "lucide-react";
import { cn } from "../lib";
import { fiyat, KartBasligi } from "./parcalar";
import type { Emir } from "./tipler";

const DURUM: Record<string, { ad: string; ton: "iyi" | "notr" | "risk" }> = {
  FILLED: { ad: "Doldu", ton: "iyi" },
  PARTIALLY_FILLED: { ad: "Kısmen", ton: "notr" },
  NEW: { ad: "Açık", ton: "notr" },
  SENT: { ad: "Gönderildi", ton: "notr" },
  CREATED: { ad: "Hazırlandı", ton: "notr" },
  VALIDATED: { ad: "Doğrulandı", ton: "notr" },
  CANCELED: { ad: "İptal", ton: "notr" },
  REJECTED: { ad: "Reddedildi", ton: "risk" },
  EXPIRED: { ad: "Süresi doldu", ton: "notr" },
  UNKNOWN: { ad: "Belirsiz", ton: "risk" },
  GOLGE: { ad: "Gölge", ton: "notr" },
};

/** Son emirler: referanstaki "son işlemler" listesinin karşılığı, ama gerçek emir kaydından
 *  (`emirler.sqlite`). Yön ikon + metinle; renk tek başına anlam taşımaz. */
export function Emirler({ emirler, strateji }: { emirler: Emir[]; strateji?: string }) {
  return (
    <section id="emirler" aria-labelledby="emirler-baslik" className="kart flex h-full scroll-mt-24 lg:min-h-[380px] flex-col gap-3 p-6">
      <KartBasligi id="emirler-baslik" baslik="Son emirler" alt={emirler.length ? `${emirler.length} kayıt · yerel saat` : undefined} />
      {emirler.length ? (
        <div className="-mx-2 max-h-[420px] overflow-y-auto">
          <table className="w-full border-separate border-spacing-y-1 text-[13px]">
            <caption className="sr-only">Son emirler, yeniden eskiye</caption>
            <thead>
              <tr className="text-left text-[11.5px] text-bot-text-3">
                <th scope="col" className="px-2 font-medium">Zaman</th>
                <th scope="col" className="px-2 font-medium">Yön</th>
                <th scope="col" className="px-2 text-right font-medium">Fiyat</th>
                <th scope="col" className="px-2 text-right font-medium">Durum</th>
              </tr>
            </thead>
            <tbody>
              {emirler.map((e) => {
                const alis = e.yon === "BUY";
                const d = DURUM[e.durum] ?? { ad: e.durum, ton: "notr" as const };
                return (
                  <tr key={e.istemci_kimligi} className="bg-bot-surface-2">
                    <td className="sayi rounded-l-lg px-2 py-2 whitespace-nowrap text-bot-text-2">
                      {new Date(e.olusturuldu_ms).toLocaleString("tr-TR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}
                    </td>
                    <td className="px-2 py-2">
                      <span className="inline-flex items-center gap-1 font-semibold text-bot-text">
                        {alis ? (
                          <ArrowDownLeft className="size-3.5 text-bot-mint" aria-hidden />
                        ) : (
                          <ArrowUpRight className="size-3.5 text-bot-down" aria-hidden />
                        )}
                        {alis ? "Alış" : "Satış"}
                      </span>
                      <span className="sayi block text-[11.5px] text-bot-text-3">
                        {(e.dolan_miktar || e.miktar).toLocaleString("tr-TR", { maximumFractionDigits: 6 })} BTC
                      </span>
                    </td>
                    <td className="sayi px-2 py-2 text-right text-bot-text">{fiyat(e.ortalama_fiyat)}</td>
                    <td className="rounded-r-lg px-2 py-2 text-right">
                      <span
                        className={cn(
                          "rounded-md px-1.5 py-0.5 text-[11.5px] font-semibold",
                          d.ton === "iyi" && "bg-bot-mint-soft text-bot-mint",
                          d.ton === "notr" && "bg-bot-surface-3 text-bot-text-2",
                          d.ton === "risk" && "bg-bot-risk-surface text-bot-risk",
                        )}
                        title={e.hata ?? undefined}
                      >
                        {d.ad}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="grid flex-1 place-items-center rounded-2xl border border-dashed border-bot-line-strong p-6 text-center">
          <div className="w-full max-w-xs">
            <p className="font-semibold text-bot-text-2">Henüz emir yok</p>
            <p className="mt-1 text-[13px] text-pretty text-bot-text-3">
              {strateji === "sabit_oran"
                ? "İlk alım bir sonraki saat başı kapanışta verilir; sonra yalnız oran bant dışına çıkınca."
                : "Strateji sinyal ürettiğinde emirler burada listelenir."}
            </p>
          </div>
        </div>
      )}
    </section>
  );
}
