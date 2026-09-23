import { ShieldAlert, ShieldCheck } from "lucide-react";
import { cn } from "../lib";
import { KartBasligi, Olcer, oran, usdt } from "./parcalar";
import type { BotYaniti, Secili } from "./tipler";

/** Risk sınırları: botu durduracak üç şeyin ne kadar yakın olduğu. Eşik %75'i geçince ölçer risk
 *  rengine döner; her satırda değer ve sınır metin olarak da yazılı. */
export function Risk({ s, pilot }: { s: Secili; pilot: BotYaniti["pilot"] }) {
  const sermaye = s.kosu.sermaye_usdt ?? s.limitler.sermaye_usdt ?? 0;
  const ozkaynak = s.hesap.ozkaynak ?? sermaye;
  const kayipTavani = pilot?.azami_kayip_usdt ?? null;
  const kayip = Math.max(0, sermaye - ozkaynak);
  const dd = s.risk.drawdown ?? s.hesap.drawdown ?? 0;
  const ddSinir = s.limitler.drawdown_limiti ?? 0.2;
  const gunluk = Math.max(0, -(s.risk.gunluk_getiri ?? s.hesap.gunluk_getiri ?? 0));
  const gunlukSinir = s.limitler.gunluk_zarar_limiti ?? 0.02;
  const safe = s.safe_mode || s.risk.safe_mode;
  const durdu = Boolean(s.halt) || safe;

  return (
    <section id="risk" aria-labelledby="risk-baslik" className="kart flex h-full scroll-mt-24 flex-col gap-5 p-6">
      <KartBasligi
        id="risk-baslik"
        baslik="Risk sınırları"
        alt="Bunlardan biri dolarsa bot yeni alım yapmaz"
        sag={
          <span
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px] font-semibold",
              durdu ? "bg-bot-risk text-bot-risk-ink" : "bg-bot-mint-soft text-bot-mint",
            )}
          >
            {durdu ? <ShieldAlert className="size-3.5" aria-hidden /> : <ShieldCheck className="size-3.5" aria-hidden />}
            {durdu ? (safe ? "SAFE_MODE açık" : "Durduruldu") : "Normal"}
          </span>
        }
      />
      {durdu ? (
        <p className="rounded-xl border border-bot-risk/40 bg-bot-risk-surface px-3 py-2 text-[13px] text-pretty text-bot-risk">
          {s.halt || s.risk.safe_mode_sebep || "SAFE_MODE"}. Bot yeni pozisyon açmıyor; çıkış yalnız elle ve gerekçeyle:{" "}
          <span className="sayi">sq execution safe-kaldir</span>.
        </p>
      ) : null}
      <ul className="flex flex-col gap-4">
        {kayipTavani != null ? (
          <Satir
            etiket="Pilot kayıp tavanı"
            deger={`${usdt(kayip)} / ${usdt(kayipTavani)} USDT`}
            oran={kayip / kayipTavani}
            not={s.mod === "LIVE" ? "Dolunca bot SAFE_MODE'a geçer" : "Canlı pilotta geçerli; burada gösterim"}
          />
        ) : null}
        <Satir
          etiket="Zirveden düşüş"
          deger={`${oran(dd, 1)} / ${oran(ddSinir, 0)}`}
          oran={dd / ddSinir}
          not="Sınır aşılırsa acil durdurma (kill) devreye girer"
        />
        <Satir
          etiket="Bugünkü zarar"
          deger={`${oran(gunluk, 2)} / ${oran(gunlukSinir, 0)}`}
          oran={gunluk / gunlukSinir}
          not="Aşılırsa alımlar ertesi güne kadar durur"
        />
      </ul>
    </section>
  );
}

function Satir({ etiket, deger, oran, not }: { etiket: string; deger: string; oran: number; not: string }) {
  return (
    <li>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[13px] font-medium text-bot-text">{etiket}</span>
        <span className="sayi text-[12.5px] text-bot-text-2">{deger}</span>
      </div>
      <div className="mt-2">
        <Olcer oran={oran} etiket={`${etiket}: ${deger}`} />
      </div>
      <p className="mt-1.5 text-[12px] text-bot-text-3">{not}</p>
    </li>
  );
}
