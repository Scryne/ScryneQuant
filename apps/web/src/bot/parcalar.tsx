import type { ReactNode } from "react";
import { cn } from "../lib";
import type { KosuOzeti } from "./tipler";

/** Kartın başlık satırı: başlık solda, sağda isteğe bağlı küçük bir ek (rozet, sekme). */
export function KartBasligi({
  baslik,
  alt,
  sag,
  id,
}: {
  baslik: string;
  alt?: ReactNode;
  sag?: ReactNode;
  id?: string;
}) {
  return (
    <header className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <h2 id={id} className="font-bot-title text-bot-title font-semibold text-balance text-bot-text">
          {baslik}
        </h2>
        {alt ? <p className="mt-0.5 text-[13px] text-pretty text-bot-text-3">{alt}</p> : null}
      </div>
      {sag ? <div className="shrink-0">{sag}</div> : null}
    </header>
  );
}

const MOD_RENGI: Record<string, string> = {
  LIVE: "border-bot-risk/50 bg-bot-risk-surface text-bot-risk",
  TESTNET: "border-bot-sky/35 bg-bot-sky/10 text-bot-sky",
  SHADOW: "border-bot-line-strong bg-bot-surface-2 text-bot-text-2",
  PAPER: "border-bot-line-strong bg-bot-surface-2 text-bot-text-2",
};

const MOD_ADI: Record<string, string> = {
  LIVE: "Canlı",
  TESTNET: "Testnet",
  SHADOW: "Shadow",
  PAPER: "Paper",
  DISABLED: "Kapalı",
};

/** Çalışma modu rozeti. Canlı mod risk rengindedir (DESIGN.md: canlı mod bir risk durumudur). */
export function ModRozeti({ mod, className }: { mod: string | null | undefined; className?: string }) {
  const m = (mod ?? "").toUpperCase();
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase",
        MOD_RENGI[m] ?? "border-bot-line-strong text-bot-text-3",
        className,
      )}
    >
      {MOD_ADI[m] ?? (mod || "bilinmiyor")}
    </span>
  );
}

export type Saglik = "iyi" | "risk" | "durgun";

/** Koşunun sağlığı: çalışıyor ve verisi taze → iyi; durdurulmuş/SAFE_MODE/bayat → risk;
 *  süreç yok (eski ya da kapatılmış koşu) → durgun. */
export function kosuSagligi(k: KosuOzeti): Saglik {
  if (k.halt || k.safe_mode) return "risk";
  if (!k.canli) return "durgun";
  if (k.veri_yasi_ms != null && k.veri_yasi_ms > 2 * 3_600_000) return "risk";
  return "iyi";
}

export function DurumNoktasi({ saglik, etiket }: { saglik: Saglik; etiket: string }) {
  return (
    <span
      role="img"
      aria-label={etiket}
      className={cn(
        "relative inline-block size-2 shrink-0 rounded-full",
        saglik === "iyi" && "nabiz bg-bot-mint text-bot-mint",
        saglik === "risk" && "bg-bot-risk",
        saglik === "durgun" && "bg-bot-text-3/60",
      )}
    />
  );
}

/** Doluluk ölçeri. Oran [0, 1]. Eşiği geçince risk rengine döner; renk tek taşıyıcı değildir,
 *  değer her zaman yanında metin olarak yazılır. */
export function Olcer({ oran, esik = 0.75, etiket }: { oran: number; esik?: number; etiket: string }) {
  const o = Math.min(1, Math.max(0, Number.isFinite(oran) ? oran : 0));
  return (
    <div
      role="meter"
      aria-label={etiket}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(o * 100)}
      className="h-1.5 w-full overflow-hidden rounded-full bg-bot-surface-3"
    >
      <div
        className={cn("h-full origin-left rounded-full", o >= esik ? "bg-bot-risk" : "bg-bot-mint")}
        style={{ transform: `scaleX(${o})` }}
      />
    </div>
  );
}

/** Yükleniyor iskeleti: kartın yerini tutar, düzen kaymaz. */
export function Iskelet({ className }: { className?: string }) {
  return <div className={cn("kart animate-pulse bg-bot-surface", className)} aria-hidden="true" />;
}

const KOSU_ADLARI: Record<string, string> = {
  "urun-testnet": "Ürün · testnet",
  "gosterim-testnet": "Gösterim · testnet",
  "gosterim-shadow": "Gösterim · shadow",
};

export function kosuAdi(ad: string): string {
  return KOSU_ADLARI[ad] ?? ad;
}

/** Türkçe yüzde: işaret önde (%50). */
export function oran(o: number | null | undefined, basamak = 1): string {
  if (o == null || !Number.isFinite(o)) return "—";
  return `%${(o * 100).toLocaleString("tr-TR", { minimumFractionDigits: basamak, maximumFractionDigits: basamak })}`;
}

/** İşaretli Türkçe yüzde: +%1,20 / −%0,40. İşaret her zaman yazılır; renk tek taşıyıcı değildir. */
export function isaretliOran(o: number | null | undefined, basamak = 2): string {
  if (o == null || !Number.isFinite(o)) return "—";
  const i = o > 0 ? "+" : o < 0 ? "−" : "±";
  return `${i}${oran(Math.abs(o), basamak)}`;
}

/** USDT tutarı: Türkçe biçim, iki ondalık. */
export function usdt(v: number | null | undefined, basamak = 2): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return v.toLocaleString("tr-TR", { minimumFractionDigits: basamak, maximumFractionDigits: basamak });
}

/** BTC fiyatı: dolar işaretiyle, kuruşsuz. */
export function fiyat(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `$${v.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}
