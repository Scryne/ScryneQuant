import type { ReactNode } from "react";
import { cn, isaretliYuzde, yon } from "../lib";

/** Yüzeyler **opak** (DESIGN.md "Elevation & Depth"): cam yalnızca üst katmanda.
 *  Derinlik gölgeyle değil yüzey tonuyla anlatılıyor. */
export function Kart({
  baslik,
  aciklama,
  eylem,
  className,
  children,
}: {
  baslik?: string;
  aciklama?: string;
  eylem?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section
      className={cn(
        "rounded-lg border border-border bg-surface",
        className,
      )}
    >
      {(baslik || eylem) && (
        <header className="flex items-baseline justify-between gap-md border-b border-border px-lg py-md">
          <div className="min-w-0">
            {baslik && (
              <h2 className="text-h2 font-semibold text-primary">{baslik}</h2>
            )}
            {aciklama && (
              <p className="mt-xs text-label text-tertiary">{aciklama}</p>
            )}
          </div>
          {eylem}
        </header>
      )}
      <div className="p-lg">{children}</div>
    </section>
  );
}

/** Tek bir skaler değeri öne çıkarır ve sayfada **azdır**: her şey büyükse hiçbir şey
 *  büyük değildir (DESIGN.md "Typography"). */
export function Olcum({
  etiket,
  deger,
  alt,
  vurgu,
}: {
  etiket: string;
  deger: string;
  alt?: ReactNode;
  vurgu?: "risk" | "up" | "down" | "flat";
}) {
  return (
    <div className="rounded-lg border border-border bg-surface p-lg">
      <div className="text-label font-medium uppercase tracking-label text-tertiary">
        {etiket}
      </div>
      <div
        className={cn(
          "rakam mt-sm text-metric font-medium tracking-metric",
          vurgu === "risk" && "text-risk",
          vurgu === "up" && "text-direction-up",
          vurgu === "down" && "text-direction-down",
          (!vurgu || vurgu === "flat") && "text-primary",
        )}
      >
        {deger}
      </div>
      {alt && <div className="mt-sm text-label text-secondary">{alt}</div>}
    </div>
  );
}

/** Kâr/zarar. **İşaret her zaman yazılı**, renk düşük doygunluklu ve yalnızca destek.
 *  Ekranda parlayan bir şey varsa o şey para değil tehlikedir (DESIGN.md). */
export function Yon({ oran, basamak = 2 }: { oran: number | null; basamak?: number }) {
  const d = yon(oran);
  return (
    <span
      className={cn(
        "rakam",
        d === "up" && "text-direction-up",
        d === "down" && "text-direction-down",
        d === "flat" && "text-direction-flat",
      )}
    >
      {isaretliYuzde(oran, basamak)}
    </span>
  );
}

export function Rozet({
  ton = "notr",
  children,
  title,
}: {
  ton?: "notr" | "risk" | "etkilesim" | "sessiz";
  children: ReactNode;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex shrink-0 items-center gap-xs whitespace-nowrap rounded-full border px-sm py-[2px] text-label font-medium",
        ton === "notr" && "border-border bg-surface-raised text-secondary",
        ton === "sessiz" && "border-transparent bg-surface-sunken text-tertiary",
        ton === "risk" && "border-risk-border bg-risk-surface text-risk",
        ton === "etkilesim" &&
          "border-interactive-strong/40 bg-interactive-surface text-interactive",
      )}
    >
      {children}
    </span>
  );
}

export function Nokta({ ton }: { ton: "risk" | "iyi" | "sessiz" }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "size-[6px] shrink-0 rounded-full",
        ton === "risk" && "bg-risk",
        ton === "iyi" && "bg-direction-up",
        ton === "sessiz" && "bg-tertiary",
      )}
    />
  );
}

/** Etiket–değer çifti. Ekranın en çok tekrarlayan birimi; tek bir yerde tanımlı olması
 *  hizalamanın sayfadan sayfaya kaymamasını sağlıyor. */
export function Satir({
  etiket,
  children,
  ipucu,
}: {
  etiket: string;
  children: ReactNode;
  ipucu?: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-md border-b border-border/60 py-sm last:border-0">
      <dt className="text-label text-tertiary" title={ipucu}>
        {etiket}
      </dt>
      <dd className="rakam text-numeric text-primary">{children}</dd>
    </div>
  );
}

export function Liste({ children }: { children: ReactNode }) {
  return <dl className="flex flex-col">{children}</dl>;
}

/** Tablo ana bileşen (DESIGN.md "Components"): bu ürünün doğal veri şekli satır.
 *  Dar ekranda sütun **gizlenmiyor**, tablo yatay kaydırılıyor — gizlenen sütun,
 *  olmayan veri gibi görünür (DESIGN.md "Layout"). */
export function Tablo({
  basliklar,
  children,
  sayisal = [],
}: {
  basliklar: string[];
  children: ReactNode;
  sayisal?: number[];
}) {
  return (
    <div className="-mx-lg overflow-x-auto">
      <table className="w-full min-w-max border-collapse text-numeric">
        <thead>
          <tr className="border-b border-border">
            {basliklar.map((b, i) => (
              <th
                key={b}
                scope="col"
                className={cn(
                  "px-md py-sm text-label font-medium uppercase tracking-label text-tertiary",
                  sayisal.includes(i) ? "text-right" : "text-left",
                )}
              >
                {b}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export function Hucre({
  sag,
  className,
  children,
  ...rest
}: React.TdHTMLAttributes<HTMLTableCellElement> & { sag?: boolean }) {
  return (
    <td
      className={cn(
        "border-b border-border/50 px-md py-sm align-baseline",
        sag ? "rakam text-right" : "text-secondary",
        className,
      )}
      {...rest}
    >
      {children}
    </td>
  );
}

/** Boş durum bir sonraki adımı söyler — "henüz yok" demekle yetinmez (DESIGN.md). */
export function Bos({ baslik, komut }: { baslik: string; komut?: string }) {
  return (
    <div className="py-xl text-center">
      <p className="text-body text-secondary">{baslik}</p>
      {komut && (
        <p className="mt-sm text-label text-tertiary">
          Komut:{" "}
          <code className="rakam rounded-sm bg-surface-sunken px-sm py-[2px] text-numeric-sm text-primary">
            {komut}
          </code>
        </p>
      )}
    </div>
  );
}

/** Hata yutulmuyor. Boş bir tablo "her şey yolunda" izlenimi verirdi; oysa veri hiç
 *  gelmemiş olabilir ve kullanıcı risk uyarısı yok sanır. */
export function Hata({ mesaj, tazele }: { mesaj: string; tazele?: () => void }) {
  return (
    <div className="rounded-md border border-risk-border bg-risk-surface p-lg">
      <p className="text-h2 font-semibold text-risk">Veri alınamadı</p>
      <p className="mt-sm text-body text-secondary">{mesaj}</p>
      <p className="mt-sm text-label text-tertiary">
        Bu ekrandaki sayılar güncel değil. Koşu sürecinin ayakta olduğunu doğrulayın.
      </p>
      {tazele && (
        <button
          type="button"
          onClick={tazele}
          className="mt-md cursor-pointer rounded-md border border-border bg-surface-raised px-md py-sm text-label font-medium text-primary transition-colors duration-150 hover:bg-surface-sunken"
        >
          Yeniden dene
        </button>
      )}
    </div>
  );
}

export function Yukleniyor({ etiket = "Yükleniyor" }: { etiket?: string }) {
  return (
    <div className="py-xl text-center text-label text-tertiary" role="status">
      {etiket}…
    </div>
  );
}
