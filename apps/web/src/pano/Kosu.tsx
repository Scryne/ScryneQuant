import { Link, useParams } from "react-router-dom";
import { cn, kisaZaman, miktar, para, sureMs, useApi, yas, yuzde } from "../lib";
import {
  Bos,
  Hata,
  Hucre,
  Kart,
  Liste,
  Olcum,
  Rozet,
  Satir,
  Tablo,
  Yon,
  Yukleniyor,
} from "../bilesenler/Ilkel";
import { OzkaynakGrafigi } from "./Ozkaynak";
import type { Islem, KosuDetayi, Pozisyon, Uretim } from "./tipler";

export function Kosu() {
  const { ad = "" } = useParams();
  const { veri, hata, yukleniyor, tazele } = useApi<KosuDetayi>(
    `/api/kosu/${encodeURIComponent(ad)}`,
    20_000,
  );
  /* Yeniden üretim arka planda koşuyor; hazır olana kadar daha sık sorulur, hazır
     olduktan sonra dakikada bir yeter (koşu saatte bir adım atıyor). */
  const uretimIstek = useApi<Uretim>(`/api/kosu/${encodeURIComponent(ad)}/uretim`, 5_000);
  const uretim = uretimIstek.veri ?? veri?.uretim ?? null;

  if (hata && !veri) return <Hata mesaj={hata} tazele={tazele} />;
  if (yukleniyor && !veri) return <Yukleniyor etiket="Koşu alınıyor" />;
  if (!veri) return null;

  const o = veri.ozet;
  const evren = veri.tur === "evren";

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
            {o.strateji ?? "—"}
            {evren ? " · evren (çok enstrüman)" : o.sembol ? ` · ${o.sembol}` : ""} ·{" "}
            {Object.entries(o.parametreler ?? {})
              .map(([k, v]) => `${k}=${String(v)}`)
              .join(" · ") || "parametresiz"}
          </p>
        </div>
        <Rozet ton="sessiz" title="Simüle emir. Promotion kanıtı ÜRETMEZ (K-035).">
          {(o.mod ?? "gozlem").toUpperCase()}
        </Rozet>
      </div>

      <div className="grid gap-md sm:grid-cols-2 xl:grid-cols-4">
        <Olcum
          etiket="Özkaynak"
          deger={para(o.ozkaynak)}
          alt={
            <>
              Başlangıç {para(o.baslangic_sermaye)} ·{" "}
              <Yon oran={o.getiri} />
            </>
          }
          vurgu={o.getiri == null ? "flat" : o.getiri > 0 ? "up" : o.getiri < 0 ? "down" : "flat"}
        />
        <Olcum
          etiket="Brüt maruziyet"
          deger={o.brut == null ? "—" : yuzde(o.brut)}
          alt={
            o.brut == null
              ? "Tek sembollü koşuda kaydedilmiyor"
              : `Nakitte kalan ${yuzde(1 - o.brut)}`
          }
        />
        <Olcum
          etiket="Açık pozisyon"
          deger={o.pozisyon_sayisi == null ? "—" : String(o.pozisyon_sayisi)}
          alt={`Toplam ${o.islem ?? "—"} işlem turu`}
        />
        <Olcum
          etiket="Adım"
          deger={o.adim == null ? "—" : String(o.adim)}
          alt={o.son_bar_utc ? `Son bar ${o.son_bar_utc} UTC` : "—"}
        />
      </div>

      <Kart
        baslik="Özkaynak eğrisi"
        aciklama={
          evren
            ? "Her ızgara barında bir nokta; ısınma adımları hariç"
            : "Tek sembollü koşuda yalnızca fill anları kaydediliyor"
        }
      >
        <OzkaynakGrafigi seri={veri.seri ?? []} sermaye={o.baslangic_sermaye} />
      </Kart>

      {evren ? (
        <>
          <Pozisyonlar uretim={uretim} />
          <Islemler uretim={uretim} />
        </>
      ) : (
        <Filller veri={veri} />
      )}

      {evren && veri.uyelik && veri.uyelik.length > 0 && (
        <Kart baslik="Evren üyeliği" aciklama="Ay başında sabitlenen liste (K-052)">
          <Liste>
            {veri.uyelik.map((u) => (
              <Satir key={u.ay} etiket={u.ay}>
                {u.sembol_sayisi} sembol
              </Satir>
            ))}
          </Liste>
        </Kart>
      )}

      <Olaylar veri={veri} />
    </div>
  );
}

/* --------------------------------------------------------------- pozisyonlar */

function Pozisyonlar({ uretim }: { uretim: Uretim | null }) {
  return (
    <Kart
      baslik="Açık pozisyonlar"
      aciklama="Koşunun kaydından yeniden üretildi — tahmin değil"
      eylem={<UretimRozeti uretim={uretim} />}
    >
      <UretimGovdesi
        uretim={uretim}
        bosBaslik="Şu anda açık pozisyon yok."
        varMi={(u) => u.pozisyonlar.length > 0}
      >
        {(u) => (
          <Tablo
            basliklar={[
              "Sembol",
              "Miktar",
              "Ort. maliyet",
              "Son fiyat",
              "Değer",
              "Ağırlık",
              "Gerçekleşmemiş",
              "Getiri",
              "Giriş",
            ]}
            sayisal={[1, 2, 3, 4, 5, 6, 7]}
          >
            {u.pozisyonlar.map((p: Pozisyon) => (
              <tr key={p.sembol}>
                <Hucre className="text-primary">{p.sembol}</Hucre>
                <Hucre sag>{miktar(p.miktar, 6)}</Hucre>
                <Hucre sag>{para(p.ortalama_maliyet, 4)}</Hucre>
                <Hucre sag>{para(p.son_fiyat, 4)}</Hucre>
                <Hucre sag>{para(p.deger)}</Hucre>
                <Hucre sag>{p.agirlik == null ? "—" : yuzde(p.agirlik)}</Hucre>
                <Hucre sag>
                  <span
                    className={cn(
                      p.gerceklesmemis_pnl == null
                        ? "text-tertiary"
                        : p.gerceklesmemis_pnl > 0
                          ? "text-direction-up"
                          : p.gerceklesmemis_pnl < 0
                            ? "text-direction-down"
                            : "text-direction-flat",
                    )}
                  >
                    {p.gerceklesmemis_pnl == null
                      ? "—"
                      : `${p.gerceklesmemis_pnl > 0 ? "+" : p.gerceklesmemis_pnl < 0 ? "−" : "±"}${para(Math.abs(p.gerceklesmemis_pnl))}`}
                  </span>
                </Hucre>
                <Hucre sag>
                  <Yon oran={p.getiri} />
                </Hucre>
                <Hucre>{p.giris_utc ? `${p.giris_utc.slice(5, 16)} UTC` : "—"}</Hucre>
              </tr>
            ))}
          </Tablo>
        )}
      </UretimGovdesi>
    </Kart>
  );
}

/* ------------------------------------------------------------------ işlemler */

function Islemler({ uretim }: { uretim: Uretim | null }) {
  return (
    <Kart
      baslik="İşlem defteri"
      aciklama="Bir satır = bir pozisyon turu (açılış → kapanış). Açık turlar da listede."
      eylem={<UretimRozeti uretim={uretim} />}
    >
      <UretimGovdesi
        uretim={uretim}
        bosBaslik="Bu koşuda henüz işlem yok."
        varMi={(u) => u.islemler.length > 0}
      >
        {(u) => (
          <Tablo
            basliklar={[
              "Sembol",
              "Durum",
              "Açılış",
              "Kapanış",
              "Süre",
              "Giriş",
              "Komisyon",
              "Net P&L",
              "Getiri",
              "Fill",
            ]}
            sayisal={[5, 6, 7, 8, 9]}
          >
            {[...u.islemler]
              .sort((a, b) => b.acilis_ms - a.acilis_ms)
              .map((i: Islem) => (
                <tr key={`${i.sembol}-${i.acilis_ms}`}>
                  <Hucre className="text-primary">{i.sembol || "—"}</Hucre>
                  <Hucre>
                    {i.acik ? (
                      <Rozet ton="etkilesim">Açık</Rozet>
                    ) : (
                      <Rozet ton="sessiz">Kapandı</Rozet>
                    )}
                  </Hucre>
                  <Hucre>{`${i.acilis_utc.slice(5, 16)} UTC`}</Hucre>
                  <Hucre>{i.kapanis_utc ? `${i.kapanis_utc.slice(5, 16)} UTC` : "—"}</Hucre>
                  <Hucre sag>{i.acik ? "—" : sureMs(i.sure_ms)}</Hucre>
                  <Hucre sag>{para(i.giris_notional)}</Hucre>
                  <Hucre sag>{para(i.komisyon, 4)}</Hucre>
                  <Hucre sag>
                    {i.acik ? (
                      <span className="text-tertiary">—</span>
                    ) : (
                      <span
                        className={cn(
                          i.net_pnl > 0
                            ? "text-direction-up"
                            : i.net_pnl < 0
                              ? "text-direction-down"
                              : "text-direction-flat",
                        )}
                      >
                        {`${i.net_pnl > 0 ? "+" : i.net_pnl < 0 ? "−" : "±"}${para(Math.abs(i.net_pnl))}`}
                      </span>
                    )}
                  </Hucre>
                  <Hucre sag>{i.acik ? "—" : <Yon oran={i.getiri} />}</Hucre>
                  <Hucre sag>{i.fill_sayisi}</Hucre>
                </tr>
              ))}
          </Tablo>
        )}
      </UretimGovdesi>
    </Kart>
  );
}

/* ------------------------------------------------- tek sembollü koşunun fill'i */

function Filller({ veri }: { veri: KosuDetayi }) {
  const filller = veri.filller ?? [];
  return (
    <Kart baslik="Fill defteri" aciklama="Tek sembollü koşunun emir kaydı (doğrudan depodan)">
      {filller.length === 0 ? (
        <Bos baslik="Bu koşuda henüz fill yok." />
      ) : (
        <Tablo
          basliklar={[
            "#",
            "Zaman",
            "Yön",
            "Miktar",
            "Fiyat",
            "Referans",
            "Komisyon",
            "Özkaynak",
            "Gerçekleşen",
          ]}
          sayisal={[3, 4, 5, 6, 7, 8]}
        >
          {[...filller]
            .sort((a, b) => b.id - a.id)
            .map((f) => (
              <tr key={f.id}>
                <Hucre sag>{f.id}</Hucre>
                <Hucre>{`${f.zaman_utc.slice(5, 16)} UTC`}</Hucre>
                <Hucre className="text-primary">{f.yon}</Hucre>
                <Hucre sag>{miktar(f.miktar, 8)}</Hucre>
                <Hucre sag>{para(f.fiyat, 2)}</Hucre>
                <Hucre sag>{para(f.referans_fiyat, 2)}</Hucre>
                <Hucre sag>{para(f.komisyon, 4)}</Hucre>
                <Hucre sag>{para(f.ozkaynak_sonra)}</Hucre>
                <Hucre sag>
                  {f.gerceklesen_pnl == null ? "—" : para(f.gerceklesen_pnl)}
                </Hucre>
              </tr>
            ))}
        </Tablo>
      )}
    </Kart>
  );
}

/* -------------------------------------------------------------------- olaylar */

function Olaylar({ veri }: { veri: KosuDetayi }) {
  const olaylar = veri.olaylar ?? [];
  return (
    <Kart baslik="Olaylar" aciklama="Koşunun kendi kaydı: başlangıç, durdurma, toparlanma, kopma">
      {olaylar.length === 0 ? (
        <Bos baslik="Kayıtlı olay yok." />
      ) : (
        <Tablo basliklar={["Zaman", "Olay", "Ayrıntı"]}>
          {[...olaylar]
            .sort((a, b) => b.zaman_ms - a.zaman_ms)
            .map((o, i) => (
              <tr key={`${o.zaman_ms}-${o.tur}-${i}`}>
                <Hucre>{`${o.zaman_utc.slice(5, 16)} UTC`}</Hucre>
                <Hucre className="text-primary">{o.tur}</Hucre>
                {/* Kırpmak yerine sarıyoruz: `title` yalnızca fareyle okunur, yani
                    kırpılan metin klavye ve ekran okuyucu için kaybolurdu. */}
                <Hucre className="max-w-[48ch] whitespace-normal break-words">
                  {JSON.stringify(o.ayrinti)}
                </Hucre>
              </tr>
            ))}
        </Tablo>
      )}
    </Kart>
  );
}

/* ------------------------------------------------------- üretim durumu ortak */

function UretimRozeti({ uretim }: { uretim: Uretim | null }) {
  if (!uretim || uretim.durum === "yok") return <Rozet ton="sessiz">Hazırlanıyor</Rozet>;
  if (uretim.durum === "hesaplaniyor")
    return (
      <Rozet ton="etkilesim" title="Koşu kaydından yeniden üretiliyor">
        Hesaplanıyor
      </Rozet>
    );
  if (uretim.durum === "hata") return <Rozet ton="risk">Üretilemedi</Rozet>;
  return (
    <Rozet ton="notr" title={`Adım ${uretim.adim} · ${uretim.sure_s ?? "—"} sn`}>
      {uretim.olculdu_ms ? yas(uretim.olculdu_ms) : "hazır"}
    </Rozet>
  );
}

function UretimGovdesi({
  uretim,
  bosBaslik,
  varMi,
  children,
}: {
  uretim: Uretim | null;
  bosBaslik: string;
  varMi: (u: Uretim) => boolean;
  children: (u: Uretim) => React.ReactNode;
}) {
  if (!uretim || uretim.durum === "yok" || uretim.durum === "hesaplaniyor") {
    return (
      <Yukleniyor etiket="Koşu kaydından yeniden üretiliyor (birkaç saniye)" />
    );
  }
  if (uretim.durum === "hata") {
    return (
      <Hata
        mesaj={
          uretim.hata ??
          "Yeniden üretim başarısız. Bu ekranda pozisyon göstermek yerine hatayı gösteriyoruz."
        }
      />
    );
  }
  if (!varMi(uretim)) return <Bos baslik={bosBaslik} />;
  return (
    <div className="flex flex-col gap-md">
      {children(uretim)}
      <p className="text-label text-tertiary">
        Yeniden üretim: adım {uretim.adim} · {kisaZaman(uretim.olculdu_ms)} ·{" "}
        {uretim.sure_s ?? "—"} sn
      </p>
    </div>
  );
}
