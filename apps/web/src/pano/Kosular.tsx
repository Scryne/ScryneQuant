import { Link } from "react-router-dom";
import { cn, kisaZaman, para, useApi, yas } from "../lib";
import { Bos, Hata, Hucre, Kart, Nokta, Rozet, Tablo, Yon, Yukleniyor } from "../bilesenler/Ilkel";
import type { KosuListesi, KosuSatiri } from "./tipler";
import { ServisSeridi } from "./Servisler";
import { JevOzet } from "./JevOzet";

/** `sq izle kontrol` 15 dakikada bir yazıyor; bundan eskisi **bayat**. */
const BAYAT_MS = 35 * 60_000;

export function Kosular() {
  const { veri, hata, yukleniyor, tazele } = useApi<KosuListesi>("/api/kosular", 20_000);

  if (hata && !veri) return <Hata mesaj={hata} tazele={tazele} />;
  if (yukleniyor && !veri) return <Yukleniyor etiket="Koşular alınıyor" />;
  if (!veri) return null;

  const kosular = veri.kosular ?? [];
  const alarmlar = veri.izleme.alarmlar ?? [];
  const bayat =
    veri.izleme.yazildi_ms == null || veri.zaman_ms - veri.izleme.yazildi_ms > BAYAT_MS;
  const duran = kosular.filter((k) => k.surec_yasiyor === false);

  return (
    <div className="flex flex-col gap-lg">
      {/* Sayfanın kendi h1'i: başlık hiyerarşisi h2'den başlarsa ekran okuyucuda sayfa
          adsız kalır (kabuktaki ürün adı bir başlık değil, bir marka etiketi). */}
      <h1 className="text-display font-semibold tracking-tight text-primary">
        Koşular
      </h1>
      <ServisSeridi />
      <DurumSeridi
        bayat={bayat}
        alarmSayisi={alarmlar.length}
        duran={duran.map((k) => k.ad)}
        yazildiMs={veri.izleme.yazildi_ms}
        simdi={veri.zaman_ms}
      />

      {alarmlar.length > 0 && (
        <ul className="flex flex-col gap-sm">
          {alarmlar.map((a) => (
            <li
              key={`${a.kod}-${a.kosu}`}
              className="rounded-md border border-risk-border bg-risk-surface px-md py-sm text-pretty"
            >
              <span className="text-label font-semibold text-risk">
                {a.seviye === "kritik" ? "KRİTİK" : "UYARI"} · {a.kod}
              </span>
              <span className="text-label text-secondary">
                {" "}
                · {a.kosu ?? "host"}: {a.mesaj}
              </span>
              <span className="block text-label text-tertiary">
                Ne yapılacağı: docs/arsiv/Runbook.md
              </span>
            </li>
          ))}
        </ul>
      )}

      <Kart
        baslik="Koşular"
        aciklama={`${kosular.length} koşu · gözlem modu, gerçek emir yok · promotion geçmiş strateji yok · ${kisaZaman(veri.zaman_ms)}`}
      >
        {kosular.length === 0 ? (
          <Bos baslik="Bu dizinde koşu dosyası yok." komut="sq paper pano --kok runs/paper" />
        ) : (
          <Tablo
            basliklar={[
              "Koşu",
              "Strateji",
              "Süreç",
              "Adım",
              "Özkaynak",
              "Getiri",
              "Brüt",
              "Pozisyon",
              "İşlem",
              "Son bar",
            ]}
            sayisal={[3, 4, 5, 6, 7, 8]}
          >
            {kosular.map((k) => (
              <Satir key={k.ad} k={k} />
            ))}
          </Tablo>
        )}
      </Kart>

      <JevOzet />

      {veri.izleme.sistem && (
        <p className="rakam text-numeric-sm text-tertiary">
          Host: boş disk {veri.izleme.sistem.disk_bos_gb.toFixed(1)} GB
          {veri.izleme.sistem.bellek_bos_gb != null &&
            ` · boş bellek ${veri.izleme.sistem.bellek_bos_gb.toFixed(1)} GB`}
        </p>
      )}
    </div>
  );
}

function Satir({ k }: { k: KosuSatiri }) {
  return (
    <tr>
      <Hucre className="text-primary">
        {/* Alt çizgi **sürekli**: bağlantıyı yalnızca renkle ayırmak, rengi ayırt
            edemeyen için bağlantıyı görünmez yapar (WCAG 1.4.1). */}
        <Link
          to={`/kosu/${encodeURIComponent(k.ad)}`}
          className="cursor-pointer rounded-sm text-interactive underline decoration-border underline-offset-2 hover:decoration-interactive"
        >
          {k.ad}
        </Link>
        {k.safe_mode && (
          <>
            {" "}
            <Rozet ton="risk" title="Risk motoru güvenli moda geçti">
              SAFE
            </Rozet>
          </>
        )}
      </Hucre>
      <Hucre>
        <span className="text-secondary">{k.strateji ?? "—"}</span>
        <span className="block text-label text-tertiary">
          {k.tur === "evren" ? "evren (çok enstrüman)" : k.sembol ? `tek · ${k.sembol}` : "—"}
        </span>
      </Hucre>
      <Hucre>
        <span className="inline-flex items-center gap-xs">
          <Nokta ton={k.surec_yasiyor === false ? "risk" : k.surec_yasiyor ? "iyi" : "sessiz"} />
          {k.surec_yasiyor === false
            ? "DURMUŞ"
            : k.surec_yasiyor
              ? "Çalışıyor"
              : "Bilinmiyor"}
        </span>
      </Hucre>
      <Hucre sag>{k.adim ?? "—"}</Hucre>
      <Hucre sag>
        {para(k.ozkaynak)}
        {k.ozkaynak_kaynagi === "son_fill" && (
          <span
            className="block text-label text-tertiary"
            title="Tek sembollü koşuda özkaynak yalnızca fill anlarında kaydediliyor"
          >
            son fill
          </span>
        )}
      </Hucre>
      <Hucre sag>
        <Yon oran={k.getiri} />
      </Hucre>
      <Hucre sag>{k.brut == null ? "—" : k.brut.toFixed(3)}</Hucre>
      <Hucre sag>{k.pozisyon_sayisi ?? "—"}</Hucre>
      <Hucre sag>{k.islem ?? "—"}</Hucre>
      <Hucre>{k.son_bar_utc ? `${k.son_bar_utc.slice(5, 16)} UTC` : "—"}</Hucre>
    </tr>
  );
}

/** Ekranın ilk satırı bir soruya cevap verir: "şu an bakmam gereken bir şey var mı?" */
function DurumSeridi({
  bayat,
  alarmSayisi,
  duran,
  yazildiMs,
  simdi,
}: {
  bayat: boolean;
  alarmSayisi: number;
  duran: string[];
  yazildiMs: number | null;
  simdi: number;
}) {
  const kotu = bayat || alarmSayisi > 0 || duran.length > 0;
  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-md rounded-lg border px-lg py-md",
        kotu ? "border-risk-border bg-risk-surface" : "border-border bg-surface",
      )}
    >
      <p className={cn("text-body font-medium", kotu ? "text-risk" : "text-primary")}>
        {duran.length > 0
          ? `${duran.length} koşu durmuş: ${duran.join(", ")}`
          : bayat
            ? "İzleme kontrolü bayat — alarm yokluğu güvenilir değil"
            : alarmSayisi > 0
              ? `${alarmSayisi} etkin alarm`
              : "Etkin alarm yok, koşuların hepsi çalışıyor"}
      </p>
      <p className="text-label text-tertiary">
        Son izleme kontrolü: {kisaZaman(yazildiMs)} ({yas(yazildiMs, simdi)})
      </p>
    </div>
  );
}
