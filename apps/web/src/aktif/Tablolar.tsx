import { ArrowDownLeft, ArrowUpRight } from "lucide-react";
import { cn, yas } from "../lib";
import { isaretliOran, KartBasligi, oran, usdt } from "../bot/parcalar";
import type { Hafta, HesapOzeti, Islem, Olay, Pozisyon } from "./tipler";

const NEDEN: Record<string, string> = {
  giris: "Giriş",
  cikis: "Çıkış",
  donus: "Yön değişimi",
  fren: "Kayıp freni",
};

function saat(ms: number): string {
  return new Date(ms).toLocaleString("tr-TR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function adet(a: number): string {
  return Math.abs(a).toLocaleString("tr-TR", { maximumFractionDigits: 6 });
}

function fiyatYaz(f: number | null): string {
  if (f == null || !Number.isFinite(f)) return "—";
  return f.toLocaleString("tr-TR", { maximumFractionDigits: f < 10 ? 5 : 2 });
}

/** Yön: ikon + metin; renk tek başına anlam taşımaz (DESIGN.md). */
function Yon({ alis, etiket }: { alis: boolean; etiket: string }) {
  return (
    <span className="inline-flex items-center gap-1 font-semibold text-bot-text">
      {alis ? <ArrowDownLeft className="size-3.5 text-bot-mint" aria-hidden /> : <ArrowUpRight className="size-3.5 text-bot-down" aria-hidden />}
      {etiket}
    </span>
  );
}

function BosSatir({ metin }: { metin: string }) {
  return <p className="rounded-xl border border-dashed border-bot-line-strong px-4 py-6 text-center text-[13px] text-pretty text-bot-text-3">{metin}</p>;
}

export function Pozisyonlar({ p, birimAdi }: { p: Pozisyon[]; birimAdi: string }) {
  return (
    <section aria-labelledby="poz-baslik" className="kart flex h-full flex-col gap-3 p-6">
      <KartBasligi id="poz-baslik" baslik="Açık pozisyonlar" alt={p.length ? `${p.length} pozisyon` : undefined} />
      {p.length ? (
        <table className="w-full border-separate border-spacing-y-1 text-[13px]">
          <caption className="sr-only">Açık pozisyonlar</caption>
          <thead>
            <tr className="text-left text-[11.5px] text-bot-text-3">
              <th scope="col" className="px-2 font-medium">Sembol</th>
              <th scope="col" className="px-2 font-medium">Yön</th>
              <th scope="col" className="px-2 text-right font-medium">Miktar</th>
              <th scope="col" className="px-2 text-right font-medium">Giriş</th>
            </tr>
          </thead>
          <tbody>
            {p.map((x) => (
              <tr key={x.sembol} className="bg-bot-surface-2">
                <td className="rounded-l-lg px-2 py-2 font-semibold text-bot-text">{x.sembol}</td>
                <td className="px-2 py-2">
                  <Yon alis={x.yon === "long"} etiket={x.yon === "long" ? "Long" : "Short"} />
                </td>
                <td className="sayi px-2 py-2 text-right text-bot-text-2">
                  {adet(x.adet)} {birimAdi}
                </td>
                <td className="sayi rounded-r-lg px-2 py-2 text-right text-bot-text">
                  {fiyatYaz(x.giris_fiyat)}
                  {x.giris_ms ? <span className="block text-[11px] text-bot-text-3">{yas(x.giris_ms)}</span> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <BosSatir metin="Açık pozisyon yok. Bot sinyal gelene kadar nakitte bekliyor." />
      )}
    </section>
  );
}

export function Islemler({ islemler, birim, birimAdi }: { islemler: Islem[]; birim: string; birimAdi: string }) {
  return (
    <section aria-labelledby="islem-baslik" className="kart flex h-full flex-col gap-3 p-6">
      <KartBasligi id="islem-baslik" baslik="Son işlemler" alt={islemler.length ? `Son ${islemler.length} · yerel saat` : undefined} />
      {islemler.length ? (
        <div className="-mx-2 max-h-[440px] overflow-auto">
          <table className="w-full border-separate border-spacing-y-1 text-[13px]">
            <caption className="sr-only">Son işlemler, yeniden eskiye</caption>
            <thead>
              <tr className="text-left text-[11.5px] text-bot-text-3">
                <th scope="col" className="px-2 font-medium">Zaman</th>
                <th scope="col" className="px-2 font-medium">Sembol</th>
                <th scope="col" className="px-2 font-medium">İşlem</th>
                <th scope="col" className="px-2 text-right font-medium">Fiyat</th>
                <th scope="col" className="px-2 text-right font-medium">Tutar</th>
                <th scope="col" className="px-2 text-right font-medium">Maliyet</th>
              </tr>
            </thead>
            <tbody>
              {islemler.map((e, i) => (
                <tr key={`${e.t}-${e.sembol}-${i}`} className="bg-bot-surface-2">
                  <td className="sayi rounded-l-lg px-2 py-2 whitespace-nowrap text-bot-text-2">{saat(e.t)}</td>
                  <td className="px-2 py-2 font-semibold text-bot-text">{e.sembol}</td>
                  <td className="px-2 py-2">
                    <Yon alis={e.adet > 0} etiket={e.adet > 0 ? "Alış" : "Satış"} />
                    <span className="block text-[11.5px] text-bot-text-3">
                      {NEDEN[e.neden] ?? e.neden} · <span className="sayi">{adet(e.adet)} {birimAdi}</span>
                    </span>
                  </td>
                  <td className="sayi px-2 py-2 text-right text-bot-text">{fiyatYaz(e.fiyat)}</td>
                  <td className="sayi px-2 py-2 text-right text-bot-text-2">{usdt(Math.abs(e.notional), 0)}</td>
                  <td className="sayi rounded-r-lg px-2 py-2 text-right text-bot-text-3">
                    {usdt(e.ucret)} <span className="sr-only">{birim}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <BosSatir metin="Henüz işlem yok. İlk sinyalde burada görünür." />
      )}
    </section>
  );
}

export function Karne({ karne }: { karne: Hafta[] }) {
  const son = [...karne].reverse().slice(0, 8);
  return (
    <section aria-labelledby="karne-baslik" className="kart flex flex-col gap-3 p-6">
      <KartBasligi id="karne-baslik" baslik="Haftalık karne" alt="Pazartesi 00:00 UTC'de yeni hafta" />
      {son.length ? (
        <ul className="flex flex-col gap-1">
          {son.map((h) => (
            <li key={h.hafta} className="flex items-center justify-between rounded-lg bg-bot-surface-2 px-3 py-2 text-[13px]">
              <span className="text-bot-text-2">
                {h.hafta.replace("-W", " · hafta ")}
                {h.suruyor ? <span className="ml-2 text-[11px] text-bot-text-3">sürüyor</span> : null}
              </span>
              <span className={cn("sayi font-semibold", h.getiri > 0 ? "text-bot-mint" : h.getiri < 0 ? "text-bot-down" : "text-bot-text-2")}>
                {isaretliOran(h.getiri)}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <BosSatir metin="İlk hafta sürüyor; karne bot çalıştıkça dolar." />
      )}
    </section>
  );
}

const STRATEJI: Record<string, string> = {
  ema_trend: "Trend takibi (EMA 20/50)",
  kirilim: "Kırılım (20 bar kanal)",
  rsi_donus: "Ortalamaya dönüş (RSI 3)",
};

export function Ayar({ h, risk }: { h: HesapOzeti; risk: Record<string, number> }) {
  const satir = (ad: string, deger: string) => (
    <div className="flex items-baseline justify-between gap-3 py-1.5">
      <dt className="text-bot-text-3">{ad}</dt>
      <dd className="m-0 text-right text-bot-text">{deger}</dd>
    </div>
  );
  return (
    <section aria-labelledby="ayar-baslik" className="kart flex flex-col gap-2 p-6">
      <KartBasligi id="ayar-baslik" baslik="Kurallar" alt="config/aktif.json" />
      <dl className="m-0 divide-y divide-bot-line text-[13px]">
        {satir("Strateji", STRATEJI[h.strateji] ?? h.strateji)}
        {satir("Grafik", h.timeframe === "1h" ? "1 saat" : h.timeframe.replace("m", " dk"))}
        {satir("Yön", h.yalniz_long ? "Yalnız alış (spot)" : "Alış ve açığa satış")}
        {satir("Günlük kayıp freni", oran(risk.gunluk_kayip, 0))}
        {satir("Haftalık kayıp freni", oran(risk.haftalik_kayip, 0))}
        {satir("Toplam maliyet", `${usdt(h.toplam_ucret)} ${h.para_birimi}`)}
        {h.swap_toplam != null ? satir("Gecelik swap (toplam)", `${h.swap_toplam > 0 ? "+" : ""}${usdt(h.swap_toplam)} ${h.para_birimi}`) : null}
      </dl>
      <p className="mt-1 text-[12px] text-pretty text-bot-text-3">{h.semboller.join(" · ")}</p>
    </section>
  );
}

const OLAY: Record<string, string> = {
  fren: "Kayıp freni",
  emir_hatasi: "Emir yapılamadı",
  tur_hatasi: "Tur hatası",
  dur: "Durduruldu",
};

export function Olaylar({ olaylar }: { olaylar: Olay[] }) {
  if (!olaylar.length) return null;
  return (
    <section aria-labelledby="olay-baslik" className="kart flex flex-col gap-3 p-6">
      <KartBasligi id="olay-baslik" baslik="Uyarılar" alt="Son kayıtlar, yeniden eskiye" />
      <ul className="flex flex-col gap-1 text-[13px]">
        {olaylar.map((o, i) => (
          <li key={`${o.t}-${i}`} className="flex flex-wrap items-baseline gap-x-3 rounded-lg bg-bot-surface-2 px-3 py-2">
            <span className="sayi text-bot-text-3">{saat(o.t)}</span>
            <span className={cn("font-semibold", o.tur === "fren" ? "text-bot-risk" : "text-bot-text")}>{OLAY[o.tur] ?? o.tur}</span>
            <span className="min-w-0 flex-1 text-pretty break-words text-bot-text-2">{o.ayrinti}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
