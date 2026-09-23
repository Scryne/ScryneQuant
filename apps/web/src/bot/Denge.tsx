import { ArrowDownToLine, ArrowUpFromLine, Scale } from "lucide-react";
import { cn } from "../lib";
import { fiyat, KartBasligi, oran } from "./parcalar";
import type { Denge as DengeTipi } from "./tipler";

/** Denge: sabit oranlı yatırımın (K-132) imza göstergesi.
 *
 *  Tek bir yatay ölçek: %0-100 BTC oranı, hedef (%50) çizgisi, izin verilen bant (%45-55) ve
 *  hesabın şu anki oranı. Altında botun bir sonraki alış ve satış yapacağı BTC fiyatları:
 *  "bot ne zaman bir şey yapacak?" sorusunun tek bakışlık cevabı. */
export function Denge({ d, sembol }: { d: DengeTipi | null; sembol?: string }) {
  if (!d) {
    return (
      <section aria-labelledby="denge-baslik" className="kart flex h-full flex-col gap-4 p-6">
        <KartBasligi id="denge-baslik" baslik="Denge" alt="Bu koşu sabit oranlı yatırım kuralını kullanmıyor." />
        <p className="text-[13px] text-bot-text-3">
          Denge göstergesi yalnız <span className="sayi">sabit_oran</span> stratejisinde anlamlı. Üstteki listeden
          ürün koşusunu seçin.
        </p>
      </section>
    );
  }
  const alt = d.hedef - d.bant;
  const ust = d.hedef + d.bant;
  const m = Math.min(1, Math.max(0, d.maruziyet));
  const pozisyonYok = d.alis_tetigi == null && d.satis_tetigi == null;
  const durum = pozisyonYok
    ? { metin: "Pozisyon yok. İlk alım bir sonraki saat başı kapanışta.", risk: false }
    : m < alt
      ? { metin: "Oran bandın altında. Bot hedefe tamamlamak için alım yapacak.", risk: false }
      : m > ust
        ? { metin: "Oran bandın üstünde. Bot hedefe inmek için satış yapacak.", risk: false }
        : { metin: "Bant içinde. İşlem gerekmiyor.", risk: false };

  const uzaklik = (tetik: number | null) =>
    tetik != null && d.fiyat ? tetik / d.fiyat - 1 : null;

  return (
    <section aria-labelledby="denge-baslik" className="kart flex h-full flex-col gap-5 p-6">
      <KartBasligi
        id="denge-baslik"
        baslik="Denge"
        alt={`Hedef %${Math.round(d.hedef * 100)} ${sembol?.replace("USDT", "") ?? "BTC"}, bant %${Math.round(alt * 100)}–${Math.round(ust * 100)}`}
        sag={<Scale className="size-5 text-bot-text-3" aria-hidden />}
      />

      <div>
        <p className="sayi text-[28px] leading-none font-medium text-bot-text">
          {oran(d.maruziyet, 1)}
          <span className="ml-2 font-bot-body text-[13px] font-medium text-bot-text-3">BTC oranı</span>
        </p>

        {/* Ölçek */}
        <div className="relative mt-5 h-9" role="img" aria-label={`BTC oranı ${oran(d.maruziyet, 1)}, hedef ${oran(d.hedef, 0)}, bant ${oran(alt, 0)} ile ${oran(ust, 0)} arası`}>
          <div className="absolute inset-x-0 top-3.5 h-2 rounded-full bg-bot-surface-3" />
          <div
            className="absolute top-3.5 h-2 bg-bot-mint-soft ring-1 ring-bot-mint/40 ring-inset"
            style={{ left: `${alt * 100}%`, width: `${(ust - alt) * 100}%` }}
          />
          <div className="absolute top-2 h-5 w-px bg-bot-text-2" style={{ left: `${d.hedef * 100}%` }} />
          {!pozisyonYok || m > 0 ? (
            <div
              className="absolute top-0 -translate-x-1/2"
              style={{ left: `${m * 100}%` }}
            >
              <div className={cn("size-4 rounded-full border-2 border-bot-bg shadow", m >= alt && m <= ust ? "bg-bot-mint" : "bg-bot-risk")} />
            </div>
          ) : null}
          <div className="sayi absolute inset-x-0 top-7 flex justify-between text-[10.5px] text-bot-text-3">
            <span>%0</span>
            <span>%50</span>
            <span>%100</span>
          </div>
        </div>
      </div>

      <p className={cn("text-[13px] text-pretty", durum.risk ? "text-bot-risk" : "text-bot-text-2")}>{durum.metin}</p>

      <dl className="grid grid-cols-2 gap-2">
        <Tetik
          ikon={<ArrowDownToLine className="size-4" aria-hidden />}
          etiket="Alır"
          deger={d.alis_tetigi}
          uzaklik={uzaklik(d.alis_tetigi)}
          aciklama="BTC bu fiyatın altına inerse"
        />
        <Tetik
          ikon={<ArrowUpFromLine className="size-4" aria-hidden />}
          etiket="Satar"
          deger={d.satis_tetigi}
          uzaklik={uzaklik(d.satis_tetigi)}
          aciklama="BTC bu fiyatın üstüne çıkarsa"
        />
      </dl>
    </section>
  );
}

function Tetik({
  ikon,
  etiket,
  deger,
  uzaklik,
  aciklama,
}: {
  ikon: React.ReactNode;
  etiket: string;
  deger: number | null;
  uzaklik: number | null;
  aciklama: string;
}) {
  return (
    <div className="rounded-xl border border-bot-line bg-bot-surface-2 px-3 py-2.5">
      <dt className="flex items-center gap-1.5 text-[12px] text-bot-text-2" title={aciklama}>
        <span className="text-bot-text-3">{ikon}</span>
        {etiket}
      </dt>
      <dd className="mt-1">
        <span className="sayi block text-[14px] text-bot-text">{deger == null ? "—" : fiyat(deger)}</span>
        <span className="block text-[11.5px] text-bot-text-3">
          {deger == null ? "İlk alımdan sonra hesaplanır" : uzaklik == null ? aciklama : `Şu andan ${uzaklik > 0 ? "+" : "−"}${oran(Math.abs(uzaklik), 1)}`}
        </span>
      </dd>
    </div>
  );
}
