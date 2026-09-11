import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { cn, sureMs, yas } from "../lib";
import type { Ozet } from "../tipler";
import { Nokta, Rozet } from "./Ilkel";

const SAYFALAR = [
  { yol: "/", etiket: "Genel", ucu: "Overview" },
  { yol: "/strateji", etiket: "Strateji", ucu: "Strategies" },
  { yol: "/pozisyon", etiket: "Pozisyon", ucu: "Positions" },
  { yol: "/gunluk", etiket: "Günlük", ucu: "Logs" },
] as const;

/** Dört sayfa — §28'in on sayfası değil (K-012). Beşinci eklenmeden önce K-012'ye bakılır. */
export function Kabuk({
  ozet,
  bagli,
  children,
}: {
  ozet: Ozet | null;
  bagli: boolean;
  children: ReactNode;
}) {
  const mod = ozet?.kosu.mod ?? "gozlem";

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[15rem_1fr]">
      <a href="#icerik" className="atla">
        İçeriğe atla
      </a>
      {/* Live ve paper görsel olarak birbirine benzemez: live modda olunduğu ekranın
          her yerinden bir saniyede anlaşılmalı (DESIGN.md "Don't"). Live'da kenar
          şeridi risk rengini alıyor. */}
      <aside
        className={cn(
          "border-b border-border bg-surface-sunken lg:sticky lg:top-0 lg:h-dvh lg:border-b-0 lg:border-r",
          mod === "live" && "border-risk-border lg:border-r-risk-border",
        )}
        style={{ zIndex: "var(--z-gezinme)" }}
      >
        <div className="flex flex-col gap-lg p-lg">
          <div>
            <div className="flex items-center gap-sm">
              <span className="text-h1 font-semibold tracking-tight text-primary">
                ScryneQuant
              </span>
              <ModRozeti mod={mod} />
            </div>
            {ozet && (
              <p className="rakam mt-xs text-numeric-sm text-tertiary">
                {ozet.kosu.sembol} · {ozet.kosu.timeframe} · {ozet.kosu.kosu_adi}
              </p>
            )}
          </div>

          <nav aria-label="Sayfalar">
            <ul className="flex gap-xs lg:flex-col">
              {SAYFALAR.map((s) => (
                <li key={s.yol}>
                  <NavLink
                    to={s.yol}
                    end={s.yol === "/"}
                    className={({ isActive }) =>
                      cn(
                        "block cursor-pointer rounded-md border px-md py-sm text-label font-medium transition-colors duration-150",
                        isActive
                          ? "border-interactive-strong/40 bg-interactive-surface text-interactive"
                          : "border-transparent text-secondary hover:bg-surface hover:text-primary",
                      )
                    }
                  >
                    {s.etiket}
                    <span className="sr-only"> ({s.ucu})</span>
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>

          <BaglantiDurumu bagli={bagli} ozet={ozet} />
        </div>
      </aside>

      <main id="icerik" className="min-w-0 p-lg lg:p-xl">
        {children}
      </main>
    </div>
  );
}

function ModRozeti({ mod }: { mod: string }) {
  if (mod === "live") {
    return (
      <Rozet ton="risk" title="Gerçek para. Her karar geri alınamaz.">
        LIVE
      </Rozet>
    );
  }
  if (mod === "paper") {
    return (
      <Rozet ton="etkilesim" title="Simüle emir; promotion kanıtı üretir.">
        PAPER
      </Rozet>
    );
  }
  return (
    <Rozet ton="sessiz" title="Simüle emir. Promotion kanıtı ÜRETMEZ (K-035).">
      GÖZLEM
    </Rozet>
  );
}

/** Canlı olduğunu sanıp ölü bir sayfaya bakmak kabul edilebilir değil: bağlantı durumu
 *  ve verinin yaşı her zaman görünür (DESIGN.md "Do's"). */
function BaglantiDurumu({ bagli, ozet }: { bagli: boolean; ozet: Ozet | null }) {
  return (
    <div className="mt-auto flex flex-col gap-xs text-label">
      <span className="flex items-center gap-sm text-secondary">
        <Nokta ton={bagli ? "iyi" : "risk"} />
        {bagli ? "Canlı akış bağlı" : "Canlı akış kopuk"}
      </span>
      {ozet && (
        <>
          <span className="text-tertiary">
            Son bar: {yas(ozet.son_bar_ms)}
          </span>
          <span className={cn("text-tertiary", ozet.tazelik.bayat && "text-risk")}>
            Veri yaşı: {sureMs(ozet.tazelik.yas_ms)}
            {ozet.tazelik.bayat && " · bayat"}
          </span>
        </>
      )}
    </div>
  );
}
