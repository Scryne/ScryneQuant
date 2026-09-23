import { useState } from "react";
import { Check, Copy, OctagonX } from "lucide-react";
import { cn } from "../lib";
import { KartBasligi } from "./parcalar";
import type { BotYaniti } from "./tipler";

/** Sistem ve acil durdurma. Pano salt okunur (K-036): durdurma burada bir düğme değil, kopyalanan
 *  bir komuttur; çalıştırmak terminalde ve bilinçli bir adım. */
export function Sistem({ v, kosu }: { v: BotYaniti; kosu: string | null }) {
  const t = v.sistem.testler;
  const testTamam = Boolean(t && t.kalan === 0 && !t.dirty && t.commit === v.sistem.commit);
  const komut = `sq execution kill --kosu ${kosu ?? "<koşu>"} --sebep "elle durdurma"`;
  const [kopyalandi, setKopyalandi] = useState(false);

  async function kopyala() {
    try {
      await navigator.clipboard.writeText(komut);
      setKopyalandi(true);
      window.setTimeout(() => setKopyalandi(false), 1800);
    } catch {
      setKopyalandi(false);
    }
  }

  return (
    <section id="sistem" aria-labelledby="sistem-baslik" className="kart flex h-full scroll-mt-24 flex-col gap-4 p-6">
      <KartBasligi id="sistem-baslik" baslik="Sistem" />
      <dl className="grid grid-cols-2 gap-x-3 gap-y-3 text-[13px]">
        <div>
          <dt className="text-[12px] text-bot-text-3">Sürüm</dt>
          <dd className="sayi mt-0.5 text-bot-text">
            {v.sistem.commit?.slice(0, 7) ?? "—"}
            <span className={cn("ml-1.5 text-[11.5px]", v.sistem.dirty ? "text-bot-risk" : "text-bot-text-3")}>
              {v.sistem.dirty ? "kirli" : "temiz"}
            </span>
          </dd>
        </div>
        <div>
          <dt className="text-[12px] text-bot-text-3">Testler</dt>
          <dd className={cn("sayi mt-0.5", testTamam ? "text-bot-text" : "text-bot-risk")}>
            {t?.gecen != null ? `${t.gecen.toLocaleString("tr-TR")} geçti` : "kayıt yok"}
            {!testTamam && t ? <span className="block text-[11.5px]">bu sürüm için değil</span> : null}
          </dd>
        </div>
        <div>
          <dt className="text-[12px] text-bot-text-3">Sistem modu</dt>
          <dd className="mt-0.5 font-semibold text-bot-text">{v.sistem.mod}</dd>
        </div>
        <div>
          <dt className="text-[12px] text-bot-text-3">Sunucu saati</dt>
          <dd className="sayi mt-0.5 text-bot-text">{v.zaman_utc.slice(11, 16)} UTC</dd>
        </div>
      </dl>

      <div className="mt-auto rounded-xl border border-bot-line bg-bot-surface-2 p-3">
        <p className="flex items-center gap-1.5 text-[13px] font-semibold text-bot-text">
          <OctagonX className="size-4 text-bot-risk" aria-hidden />
          Acil durdurma
        </p>
        <p className="mt-1 text-[12px] text-pretty text-bot-text-3">
          Botu durdurur ve açık emirleri iptal eder. Terminalde çalıştır:
        </p>
        <div className="mt-2 flex items-center gap-2">
          <code className="sayi min-w-0 flex-1 truncate rounded-lg bg-bot-bg px-2 py-1.5 text-[11.5px] text-bot-text-2">
            {komut}
          </code>
          <button
            type="button"
            onClick={kopyala}
            aria-label="Durdurma komutunu kopyala"
            className="grid size-9 shrink-0 place-items-center rounded-lg border border-bot-line text-bot-text-2 transition-colors duration-150 hover:border-bot-line-strong hover:text-bot-text"
          >
            {kopyalandi ? <Check className="size-4 text-bot-mint" aria-hidden /> : <Copy className="size-4" aria-hidden />}
          </button>
        </div>
        <p aria-live="polite" className="sr-only">
          {kopyalandi ? "Komut kopyalandı" : ""}
        </p>
      </div>
    </section>
  );
}
