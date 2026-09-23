import { ChevronRight } from "lucide-react";
import { cn, yas } from "../lib";
import { DurumNoktasi, KartBasligi, kosuAdi, kosuSagligi, ModRozeti } from "./parcalar";
import type { KosuOzeti } from "./tipler";

/** Koşular: botun şu an çalışan süreçleri. Aktif olanlar üstte; eskiler katlanmış. Bir satıra
 *  basmak o koşuyu ekranın geri kalanında seçer. */
export function Kosular({
  kosular,
  secili,
  sec,
}: {
  kosular: KosuOzeti[];
  secili: string | null;
  sec: (ad: string) => void;
}) {
  const aktif = kosular.filter((k) => k.canli && !k.kapatildi);
  const eski = kosular.filter((k) => !(k.canli && !k.kapatildi));
  return (
    <section id="kosular" aria-labelledby="kosular-baslik" className="kart flex h-full scroll-mt-24 flex-col gap-3 p-6">
      <KartBasligi id="kosular-baslik" baslik="Koşular" alt={`${aktif.length} çalışıyor`} />
      <ul className="flex flex-col gap-1.5">
        {aktif.map((k) => (
          <Satir key={k.ad} k={k} secili={secili === k.ad} sec={sec} />
        ))}
        {!aktif.length ? (
          <li className="rounded-xl border border-dashed border-bot-risk/40 p-3 text-[13px] text-bot-risk">
            Çalışan koşu yok. Gözetmen görevi 10 dakikada bir yeniden başlatır; kontrol:{" "}
            <span className="sayi">runs/gosterim/gozetmen.log</span>
          </li>
        ) : null}
      </ul>
      {eski.length ? (
        <details className="group">
          <summary className="flex min-h-9 cursor-pointer list-none items-center gap-1 text-[12.5px] font-medium text-bot-text-3 hover:text-bot-text-2">
            <ChevronRight className="size-4 transition-transform duration-150 group-open:rotate-90" aria-hidden />
            Geçmiş koşular ({eski.length})
          </summary>
          <ul className="mt-1.5 flex flex-col gap-1.5">
            {eski.map((k) => (
              <Satir key={k.ad} k={k} secili={secili === k.ad} sec={sec} />
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}

function Satir({ k, secili, sec }: { k: KosuOzeti; secili: boolean; sec: (ad: string) => void }) {
  const saglik = kosuSagligi(k);
  const sonBarMs = k.veri_yasi_ms != null ? Date.now() - k.veri_yasi_ms : null;
  const etiket =
    saglik === "iyi" ? "çalışıyor" : saglik === "risk" ? "dikkat gerekiyor" : "durmuş";
  return (
    <li>
      <button
        type="button"
        onClick={() => sec(k.ad)}
        aria-current={secili ? "true" : undefined}
        className={cn(
          "flex w-full min-h-11 items-center gap-3 rounded-xl border px-3 py-2 text-left transition-colors duration-150",
          secili ? "border-bot-mint/50 bg-bot-mint-soft" : "border-bot-line bg-bot-surface-2 hover:border-bot-line-strong",
        )}
      >
        <DurumNoktasi saglik={saglik} etiket={etiket} />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] font-semibold text-bot-text">{kosuAdi(k.ad)}</span>
          <span className="block truncate text-[11.5px] text-bot-text-3">
            {k.strateji ?? "—"} · son bar {sonBarMs ? yas(sonBarMs) : "yok"}
            {k.hata ? ` · ${k.hata} uyarı` : ""}
          </span>
        </span>
        <ModRozeti mod={k.mod} />
      </button>
    </li>
  );
}
