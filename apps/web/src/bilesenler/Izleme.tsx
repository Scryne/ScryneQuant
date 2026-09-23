import { cn, isaretliYuzde, kisaZaman, para, useApi, yas } from "../lib";
import type { Alarm, Boyut, Izleme as IzlemeTipi, IzlenenKosu } from "../tipler";
import { Bos, Hata, Hucre, Kart, Nokta, Rozet, Tablo, Yukleniyor } from "./Ilkel";

const BOYUTLAR: { ad: Boyut; etiket: string; ne: string }[] = [
  { ad: "sistem", etiket: "Sistem", ne: "Süreçler, disk, bellek" },
  { ad: "veri", etiket: "Veri", ne: "Bar gecikmesi, eksik adım, kopma, evren tablosu" },
  { ad: "trading", etiket: "Trading", ne: "SAFE_MODE, düşüş, maruziyet, koşu hatası" },
  { ad: "model", etiket: "Model", ne: "Canlı-backtest sapması" },
];

/** `sq izle kontrol` 15 dakikada bir yazıyor; bundan eski durum **bayat** sayılır ve
 *  "alarm yok" diye okunamaz — kontrolün kendisi durmuş olabilir. */
const BAYAT_MS = 35 * 60_000;
/** Gözlem koşularının başlangıç sermayesi (`sq paper evren-baslat --sermaye`). */
const SERMAYE = 10_000;

export function IzlemeBolumu() {
  const { veri, hata, yukleniyor, tazele } = useApi<IzlemeTipi>("/api/izleme", 60_000);

  if (hata && !veri) return <Hata mesaj={hata} tazele={tazele} />;
  if (yukleniyor && !veri) return <Yukleniyor etiket="İzleme durumu alınıyor" />;
  if (!veri) return null;
  if (!veri.var) {
    return (
      <Kart baslik="İzleme" aciklama="Dört gözlem boyutu">
        <Bos
          baslik="İzleme kontrolü henüz hiç çalışmadı."
          komut="sq izle kontrol --evren evren-kiyas --tek host-1"
        />
      </Kart>
    );
  }

  const alarmlar = veri.alarmlar ?? [];
  const bayat = veri.yazildi_ms == null || veri.simdi_ms - veri.yazildi_ms > BAYAT_MS;

  return (
    <Kart
      baslik="İzleme"
      aciklama={`Son kontrol ${kisaZaman(veri.yazildi_ms)} (${yas(veri.yazildi_ms, veri.simdi_ms)}) · gözlem koşuları, gerçek emir yok`}
      eylem={
        bayat ? (
          <Rozet ton="risk" title="Kontrol 35 dakikadan eski: alarm yokluğu güvenilir değil">
            İzleme bayat
          </Rozet>
        ) : alarmlar.length ? (
          <Rozet ton="risk">{alarmlar.length} etkin alarm</Rozet>
        ) : (
          <Rozet ton="notr">Alarm yok</Rozet>
        )
      }
    >
      <div className="flex flex-col gap-lg">
        <ul className="grid gap-md sm:grid-cols-2 xl:grid-cols-4">
          {BOYUTLAR.map((b) => (
            <BoyutKutusu
              key={b.ad}
              etiket={b.etiket}
              ne={b.ne}
              alarmlar={alarmlar.filter((a) => a.boyut === b.ad)}
              bayat={bayat}
            />
          ))}
        </ul>

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

        <KosuTablosu kosular={veri.kosular ?? []} simdi={veri.simdi_ms} />

        {veri.sistem && (
          <p className="rakam text-numeric-sm text-tertiary">
            Host: boş disk {veri.sistem.disk_bos_gb.toFixed(1)} GB
            {veri.sistem.bellek_bos_gb != null &&
              ` · boş bellek ${veri.sistem.bellek_bos_gb.toFixed(1)} GB`}
          </p>
        )}
      </div>
    </Kart>
  );
}

function BoyutKutusu({
  etiket,
  ne,
  alarmlar,
  bayat,
}: {
  etiket: string;
  ne: string;
  alarmlar: Alarm[];
  bayat: boolean;
}) {
  const kritik = alarmlar.some((a) => a.seviye === "kritik");
  const ton = bayat || kritik ? "risk" : alarmlar.length ? "sessiz" : "iyi";
  return (
    <li
      className={cn(
        "rounded-lg border bg-surface-raised p-md",
        alarmlar.length ? "border-risk-border" : "border-border",
      )}
    >
      <div className="flex items-center gap-sm">
        <Nokta ton={ton} />
        <span className="text-label font-medium uppercase tracking-label text-tertiary">
          {etiket}
        </span>
      </div>
      <p
        className={cn(
          "mt-sm text-body font-medium",
          alarmlar.length ? "text-risk" : "text-primary",
        )}
      >
        {bayat ? "Bilinmiyor" : alarmlar.length ? `${alarmlar.length} alarm` : "Sorun yok"}
      </p>
      <p className="mt-xs text-label text-pretty text-tertiary">{ne}</p>
    </li>
  );
}

function KosuTablosu({ kosular, simdi }: { kosular: IzlenenKosu[]; simdi: number }) {
  if (!kosular.length) return null;
  return (
    <Tablo
      basliklar={["Koşu", "Süreç", "Son bar", "Adım", "Özkaynak", "Getiri", "Brüt", "Sapma"]}
      sayisal={[3, 4, 5, 6]}
    >
      {kosular.map((k) => {
        const getiri = k.ozkaynak == null ? null : k.ozkaynak / SERMAYE - 1;
        return (
          <tr key={k.kosu}>
            <Hucre className="text-primary">{k.kosu}</Hucre>
            <Hucre>
              <span className="inline-flex items-center gap-xs">
                <Nokta ton={k.surec_yasiyor ? "iyi" : "risk"} />
                {k.surec_yasiyor ? "Çalışıyor" : "DURMUŞ"}
              </span>
            </Hucre>
            <Hucre>
              {k.son_bar_ms == null
                ? "—"
                : `${kisaZaman(k.son_bar_ms)} · kapanış ${yas(k.son_bar_ms + 3_600_000, simdi)}`}
            </Hucre>
            <Hucre sag>{k.adim ?? "—"}</Hucre>
            <Hucre sag>{para(k.ozkaynak)}</Hucre>
            <Hucre sag>{isaretliYuzde(getiri)}</Hucre>
            <Hucre sag>{k.brut == null ? "—" : k.brut.toFixed(3)}</Hucre>
            <Hucre>{sapmaMetni(k)}</Hucre>
          </tr>
        );
      })}
    </Tablo>
  );
}

/** Canlı koşu ile aynı girdileri baştan bilen referansın farkı (`sq paper evren-sapma`).
 *  "Yok" bit düzeyinde aynı demek; varsa son fark ve ilk ayrışma zamanı. */
function sapmaMetni(k: IzlenenKosu): string {
  if (k.adim == null) return "—";
  if (!k.sapma) return "Henüz ölçülmedi";
  if (k.sapma.ilk_ayrisan_adim == null) return `Yok (ölçüm ${k.sapma.olculdu.slice(5, 16)} UTC)`;
  return `${k.sapma.son_ozkaynak_farki_bps.toFixed(1)} bps · ilk ${k.sapma.ilk_ayrisan_utc}`;
}
