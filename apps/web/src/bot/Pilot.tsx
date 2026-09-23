import { Check, CircleDashed, X } from "lucide-react";
import { cn } from "../lib";
import { usdt } from "./parcalar";
import type { BotYaniti } from "./tipler";

const ADLAR: Record<string, string> = {
  testler: "Test takımı yeşil",
  "kosu:gosterim-testnet": "Testnet gösterimi",
  "kosu:gosterim-shadow": "Shadow gösterimi",
  kill_tatbikati: "Acil durdurma tatbikatı",
};

/** Canlı pilot kartı: referanstaki "öne çıkan" kartın karşılığı. Bu ekranın tek yeşil dolgulu
 *  yüzeyi; içinde ne kaldığı ve gerçek paraya geçmek için sırada ne olduğu yazılı (K-129). */
export function Pilot({ v }: { v: BotYaniti }) {
  const h = v.hazirlik;
  const kontroller = h?.pilot ?? [];
  const gecen = kontroller.filter((k) => k.gecti === true).length;
  const hedefGun = h?.pilot_gosterim_gun ?? 7;
  const gun = Math.min(hedefGun, h?.gosterim_gun ?? 0);
  const hazir = h?.pilot_hazir === true;
  const p = v.pilot;

  return (
    <section
      aria-labelledby="pilot-baslik"
      className="relative flex h-full flex-col gap-4 overflow-hidden rounded-[20px] bg-gradient-to-br from-bot-mint to-bot-mint-deep p-6 text-bot-mint-ink"
    >
      <div
        aria-hidden
        className="pointer-events-none absolute -top-10 -right-10 size-40 rotate-45 rounded-3xl border-[14px] border-bot-mint-ink/10"
      />
      <div>
        <p className="text-[12.5px] font-semibold opacity-80">
          {p ? `${usdt(p.sermaye_usdt, 0)} USDT · kayıp tavanı ${usdt(p.azami_kayip_usdt, 0)} USDT` : "Kademe 1"}
        </p>
        <h2 id="pilot-baslik" className="mt-1 font-bot-display text-[26px] leading-tight font-extrabold text-balance">
          {hazir ? "Canlı pilot hazır" : "Canlı pilot"}
        </h2>
        <p className="mt-1 text-[13px] font-medium opacity-85">
          {hazir ? "Açmak için son adım senin onayın." : `${gecen}/${kontroller.length || 4} hazırlık kontrolü tamam`}
        </p>
      </div>

      <div>
        <div className="flex justify-between text-[12px] font-semibold">
          <span>Gösterim</span>
          <span className="sayi">
            {gun.toLocaleString("tr-TR", { maximumFractionDigits: 1 })} / {hedefGun} gün
          </span>
        </div>
        <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-bot-mint-ink/15" role="progressbar" aria-label="Gösterim süresi" aria-valuemin={0} aria-valuemax={hedefGun} aria-valuenow={Number(gun.toFixed(1))}>
          <div className="h-full origin-left rounded-full bg-bot-mint-ink" style={{ transform: `scaleX(${gun / hedefGun})` }} />
        </div>
      </div>

      <ul className="flex flex-col gap-1.5">
        {kontroller.map((k) => (
          <li key={k.ad} className="flex items-center gap-2 text-[13px] font-medium">
            <span
              className={cn(
                "grid size-5 shrink-0 place-items-center rounded-full",
                k.gecti === true ? "bg-bot-mint-ink text-bot-mint" : "bg-bot-mint-ink/15",
              )}
            >
              {k.gecti === true ? (
                <Check className="size-3.5" aria-hidden />
              ) : k.gecti === false ? (
                <X className="size-3.5" aria-hidden />
              ) : (
                <CircleDashed className="size-3.5" aria-hidden />
              )}
            </span>
            <span className="truncate">{ADLAR[k.ad] ?? k.ad}</span>
            <span className="sr-only">{k.gecti === true ? "tamam" : "eksik"}</span>
          </li>
        ))}
        {h?.hata ? <li className="text-[12px]">Hazırlık okunamadı: {h.hata}</li> : null}
      </ul>

      <p className="mt-auto border-t border-bot-mint-ink/15 pt-3 text-[12px] leading-snug font-medium opacity-85">
        Senden: işlem yetkili ve çekimsiz API anahtarı, hesapta ~100 USDT, sonra{" "}
        <span className="sayi">sq execution onayla</span>.
      </p>
    </section>
  );
}
