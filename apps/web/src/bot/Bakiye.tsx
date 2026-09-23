import { Bitcoin, Coins, Receipt } from "lucide-react";
import { kisaZaman, miktar } from "../lib";
import { cn } from "../lib";
import { isaretliOran, ModRozeti, usdt } from "./parcalar";
import type { EgriNoktasi, Secili } from "./tipler";

/** Hesap değeri: ekranın en büyük sayısı. Başlangıca göre değişim işaretle yazılır. */
export function Bakiye({ s }: { s: Secili }) {
  const h = s.hesap;
  const sermaye = s.kosu.sermaye_usdt ?? s.limitler.sermaye_usdt ?? null;
  const ozkaynak = h.ozkaynak ?? null;
  const degisim = sermaye && ozkaynak != null ? ozkaynak / sermaye - 1 : null;
  const yonu = degisim == null || degisim === 0 ? "flat" : degisim > 0 ? "up" : "down";
  const btcDegeri = h.pozisyon_degeri ?? (h.miktar != null && h.fiyat != null ? h.miktar * h.fiyat : null);

  return (
    <section aria-labelledby="bakiye-baslik" className="kart flex h-full flex-col justify-between gap-6 p-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p id="bakiye-baslik" className="text-[13px] font-medium text-bot-text-2">
            Hesap değeri
          </p>
          <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <p className="font-bot-display text-bot-display font-bold tracking-bot-display tabular-nums text-bot-text">
              {usdt(ozkaynak)}
              <span className="ml-2 text-lg font-semibold text-bot-text-3">USDT</span>
            </p>
            <span
              className={cn(
                "sayi rounded-md px-2 py-0.5 text-[12px] font-medium",
                yonu === "up" && "bg-bot-mint-soft text-bot-mint",
                yonu === "down" && "bg-bot-down/12 text-bot-down",
                yonu === "flat" && "bg-bot-surface-3 text-bot-text-2",
              )}
            >
              {isaretliOran(degisim)}
            </span>
          </div>
          <p className="mt-1.5 text-[12.5px] text-bot-text-3">
            Başlangıç {usdt(sermaye)} USDT
            {s.baslangic_ms ? ` · ${kisaZaman(s.baslangic_ms)}` : ""}
          </p>
        </div>
        <ModRozeti mod={s.mod} />
      </div>

      <Kiyas egri={s.egri} />

      <dl className="grid grid-cols-3 gap-2">
        <Kalem ikon={<Bitcoin className="size-4" aria-hidden />} etiket="BTC">
          <span className="block">{miktar(h.miktar, 6)}</span>
          <span className="block text-[11.5px] text-bot-text-3">{usdt(btcDegeri)} USDT</span>
        </Kalem>
        <Kalem ikon={<Coins className="size-4" aria-hidden />} etiket="Nakit">
          <span className="block">{usdt(h.nakit)}</span>
          <span className="block text-[11.5px] text-bot-text-3">USDT</span>
        </Kalem>
        <Kalem ikon={<Receipt className="size-4" aria-hidden />} etiket="Komisyon">
          <span className="block">{usdt(h.komisyon_toplam, 4)}</span>
          <span className="block text-[11.5px] text-bot-text-3">toplam</span>
        </Kalem>
      </dl>
    </section>
  );
}

function Kalem({ ikon, etiket, children }: { ikon: React.ReactNode; etiket: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-bot-line bg-bot-surface-2 px-3 py-2.5">
      <dt className="flex items-center gap-1.5 text-[12px] text-bot-text-2">
        <span className="text-bot-text-3">{ikon}</span>
        {etiket}
      </dt>
      <dd className="sayi mt-1 truncate text-[13px] text-bot-text">{children}</dd>
    </div>
  );
}

/** Aynı dönemde yalnız BTC tutmakla kıyas: sabit oranın (K-132) işi düşüşü yarıya indirmek,
 *  BTC'yi yenmek değil. Kıyas eğrinin ilk noktasından; koşu yeniden başladıysa oradan. */
function Kiyas({ egri }: { egri: EgriNoktasi[] }) {
  const ilk = egri.at(0);
  const son = egri.at(-1);
  if (!ilk || !son || egri.length < 2 || !(ilk.fiyat > 0) || !(ilk.ozkaynak > 0)) return null;
  const bot = son.ozkaynak / ilk.ozkaynak - 1;
  const btc = son.fiyat / ilk.fiyat - 1;
  const olcek = Math.max(Math.abs(bot), Math.abs(btc), 1e-9);
  const satirlar = [
    { ad: "Bot", deger: bot, ton: bot >= 0 ? "bg-bot-mint" : "bg-bot-down" },
    { ad: "Yalnız BTC", deger: btc, ton: "bg-bot-text-3" },
  ];
  return (
    <figure className="flex flex-col gap-2">
      <figcaption className="text-[12px] text-bot-text-3">Aynı dönemde yalnız BTC tutsaydın</figcaption>
      {satirlar.map((r) => (
        <div key={r.ad} className="grid grid-cols-[84px_1fr_64px] items-center gap-3 text-[12.5px]">
          <span className="text-bot-text-2">{r.ad}</span>
          <span className="h-1.5 overflow-hidden rounded-full bg-bot-surface-3">
            <span
              className={cn("block h-full origin-left rounded-full", r.ton)}
              style={{ transform: `scaleX(${Math.abs(r.deger) / olcek})` }}
            />
          </span>
          <span className="sayi text-right text-bot-text">{isaretliOran(r.deger)}</span>
        </div>
      ))}
    </figure>
  );
}
