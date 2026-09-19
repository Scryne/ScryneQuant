import { Link, useParams } from "react-router-dom";
import { cn, kisaZaman, useApi, yuzde } from "../lib";
import { Bos, Hata, Hucre, Kart, Liste, Olcum, Rozet, Satir, Tablo, Yukleniyor } from "../bilesenler/Ilkel";
import type { JevDetayi, JevKarar } from "./tipler";

/** Tek bir Jev gölge koşusu. Bu sayfa iki şeyi ayırır ve ayrı tutar:
 *  - **ürün durumu**: süreç yaşıyor mu, kaç karar, kaç hata, zincir sağlam mı, gecikme;
 *  - **ölçüm sonucu**: burada YOK. İsabet, kâr, kalibrasyon `sq jev degerlendir` ile ayrı
 *    bir rapordur ve pencere dolmadan üretilmez (K-074/7). Sayfa bunu şeritle söyler. */
export function Jev() {
  const { ad = "" } = useParams();
  const { veri, hata, yukleniyor, tazele } = useApi<JevDetayi>(
    `/api/jev/${encodeURIComponent(ad)}`,
    20_000,
  );
  if (hata && !veri) return <Hata mesaj={hata} tazele={tazele} />;
  if (yukleniyor && !veri) return <Yukleniyor etiket="Gölge koşusu alınıyor" />;
  if (!veri) return null;

  const d = (veri.durum ?? {}) as Record<string, unknown>;
  const git = veri.kimlik?.git;
  const ayar = (veri.kimlik?.ayarlar ?? {}) as Record<string, unknown>;
  const gecikme = (d.gecikme_ms ?? {}) as { p50?: number | null; p95?: number | null };
  const kararlar = veri.kararlar ?? [];
  const olaylar = veri.olaylar ?? [];

  return (
    <div className="flex flex-col gap-lg">
      <div className="flex flex-wrap items-baseline justify-between gap-md">
        <div className="min-w-0">
          <Link
            to="/"
            className="cursor-pointer text-label text-interactive underline decoration-border underline-offset-2 hover:decoration-interactive"
          >
            ← Bütün koşular
          </Link>
          <h1 className="mt-xs text-display font-semibold tracking-tight text-primary">
            {veri.ad}
          </h1>
          <p className="mt-xs text-label text-tertiary">
            Jev gölge · {String(ayar.model ?? "—")} · {String(ayar.sembol ?? "—")} 1h · marj{" "}
            {String(ayar.yon_marji ?? "—")} · başladı {veri.kimlik?.baslangic_utc ?? "—"}
          </p>
        </div>
        <div className="flex gap-sm">
          <Rozet ton="sessiz" title="Sinyal, risk kararı ve emir üretmez (K-074/1).">
            ÖLÇÜM · EMİR YOK
          </Rozet>
          {git?.dirty && (
            <Rozet ton="risk" title="Koşu kirli bir çalışma ağacında başladı; promotion kanıtı olamaz (K-009).">
              DIRTY
            </Rozet>
          )}
        </div>
      </div>

      <div
        className="rounded-lg border border-border bg-surface-sunken px-lg py-md text-label text-secondary"
        role="note"
      >
        Bu sayfa ürünün <strong className="text-primary">çalıştığını</strong> gösterir; Jev'in
        isabetli olup olmadığını göstermez. İsabet, kalibrasyon ve kıyas ayrı bir rapordur
        (<code className="rakam">sq jev degerlendir</code>) ve gölge penceresi dolmadan
        üretilmez. Kesim tarihi bilinmediği için geçmiş replay kanıt sayılmaz (K-074/3).
      </div>

      <div className="grid gap-md sm:grid-cols-2 lg:grid-cols-4">
        <Olcum
          etiket="Süreç"
          deger={veri.surec_yasiyor === false ? "DURMUŞ" : veri.surec_yasiyor ? "Çalışıyor" : "Bilinmiyor"}
          vurgu={veri.surec_yasiyor === false ? "risk" : undefined}
          alt={veri.pid ? `pid ${veri.pid}` : "pid dosyası yok"}
        />
        <Olcum
          etiket="Karar"
          deger={`${String(d.gecerli ?? "—")} / ${String(d.toplam ?? "—")}`}
          alt={`hata ${String(d.hata ?? "—")} · çekimser ${d.cekimserlik_orani == null ? "—" : yuzde(d.cekimserlik_orani as number, 0)}`}
          vurgu={typeof d.hata === "number" && d.hata > 0 ? "risk" : undefined}
        />
        <Olcum
          etiket="Gecikme"
          deger={gecikme.p50 == null ? "—" : `${gecikme.p50} ms`}
          alt={gecikme.p95 == null ? undefined : `p95 ${gecikme.p95} ms · bar bütçesi 1 saat`}
        />
        <Olcum
          etiket="Defter zinciri"
          deger={d.zincir_gecerli == null ? "—" : d.zincir_gecerli ? "Geçerli" : "BOZUK"}
          vurgu={d.zincir_gecerli === false ? "risk" : undefined}
          alt={
            typeof d.yazildi_ms === "number" ? `durum yazıldı ${kisaZaman(d.yazildi_ms)}` : undefined
          }
        />
      </div>

      <Kart baslik="Son kararlar" aciklama={`${kararlar.length} kayıt · olasılıklar ham, yön = olasılık + marj (K-074/6)`}>
        {kararlar.length === 0 ? (
          <Bos baslik="Henüz karar yok; ilk karar ilk kapanmış barda." />
        ) : (
          <Tablo
            basliklar={["Bar (UTC)", "Durum", "Yön", "P long", "P flat", "P short", "Güven", "Rejim", "Kurulum", "Çekimser", "Gecikme", "İleriye dönük"]}
            sayisal={[3, 4, 5, 6, 8, 9, 10]}
          >
            {[...kararlar].reverse().map((k) => (
              <KararSatiri key={`${k.karar_ms}-${k.uretim_ms}`} k={k} />
            ))}
          </Tablo>
        )}
      </Kart>

      <div className="grid gap-lg lg:grid-cols-2">
        <Kart baslik="Kimlik" aciklama="Koşunun kaydettiği şey: bunlar değişirse yeni koşudur (K-074/6)">
          <Liste>
            <Satir etiket="Model">{String(ayar.model ?? "—")}</Satir>
            <Satir etiket="Soru hash'i">
              <span className="rakam text-numeric-sm">{(veri.kimlik?.soru_sha256 ?? "—").slice(0, 16)}…</span>
            </Satir>
            <Satir etiket="Kesim tarihi">
              {ayar.egitim_kesim_ms ? String(ayar.egitim_kesim_ms) : "BİLİNMİYOR (K-074/3)"}
            </Satir>
            <Satir etiket="Commit">
              <span className="rakam text-numeric-sm">
                {git?.commit ? git.commit.slice(0, 12) : "—"}
                {git?.dirty ? " · dirty" : ""}
              </span>
            </Satir>
            <Satir etiket="Pencere">
              {typeof d.pencere === "object" && d.pencere
                ? `${String((d.pencere as { bar_sayisi?: number }).bar_sayisi ?? "—")} bar`
                : "—"}
            </Satir>
            <Satir etiket="Funding">{String(d.funding_odeme ?? "—")} ödeme</Satir>
          </Liste>
        </Kart>
        <Kart baslik="Olaylar" aciklama="Süreç günlüğü: başladı, durdu, hata, tutarlılık, atlanan bar">
          {olaylar.length === 0 ? (
            <Bos baslik="Olay yok." />
          ) : (
            <ul className="flex flex-col gap-xs">
              {[...olaylar].reverse().map((o, i) => (
                <li key={`${o.zaman_ms}-${i}`} className="flex gap-md text-label">
                  <span className="rakam shrink-0 text-tertiary">{o.zaman_utc.slice(5, 16)}</span>
                  <span className={cn("shrink-0 font-medium", o.tur === "hata" ? "text-risk" : "text-secondary")}>
                    {o.tur}
                  </span>
                  <span className="min-w-0 truncate text-tertiary" title={JSON.stringify(o.ayrinti)}>
                    {ozetle(o.ayrinti)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Kart>
      </div>
    </div>
  );
}

function KararSatiri({ k }: { k: JevKarar }) {
  const p = k.yon_olasiliklari ?? null;
  const gecerli = k.durum === "gecerli";
  return (
    <tr>
      <Hucre>
        <span className="rakam">{k.karar_utc.slice(5, 16)}</span>
      </Hucre>
      <Hucre>
        {gecerli ? (
          <span className="text-secondary">geçerli</span>
        ) : (
          <span className="text-risk" title={k.hata ?? undefined}>
            {k.durum}
          </span>
        )}
      </Hucre>
      <Hucre className="text-primary">{gecerli ? (k.yon ?? "—") : "—"}</Hucre>
      <Hucre sag>{p?.long == null ? "—" : p.long.toFixed(2)}</Hucre>
      <Hucre sag>{p?.flat == null ? "—" : p.flat.toFixed(2)}</Hucre>
      <Hucre sag>{p?.short == null ? "—" : p.short.toFixed(2)}</Hucre>
      <Hucre sag>{k.yon_guven == null ? "—" : k.yon_guven.toFixed(2)}</Hucre>
      <Hucre>{k.rejim ?? "—"}</Hucre>
      <Hucre sag>{k.kurulum_skor == null ? "—" : k.kurulum_skor.toFixed(2)}</Hucre>
      <Hucre sag>{k.cekimser == null ? "—" : k.cekimser.toFixed(2)}</Hucre>
      <Hucre sag>{k.gecikme_ms == null ? "—" : `${k.gecikme_ms} ms`}</Hucre>
      <Hucre>
        {k.ileriye_donuk == null ? "—" : k.ileriye_donuk ? "evet" : <span className="text-risk">hayır</span>}
      </Hucre>
    </tr>
  );
}

function ozetle(a: Record<string, unknown>): string {
  return Object.entries(a)
    .filter(([anahtar]) => anahtar !== "pencere")
    .slice(0, 5)
    .map(([anahtar, deger]) => `${anahtar}=${typeof deger === "object" ? "…" : String(deger)}`)
    .join(" · ");
}
