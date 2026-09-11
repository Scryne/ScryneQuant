import { cn, sureMs } from "../lib";
import type { Ozet } from "../tipler";
import { Nokta } from "./Ilkel";

/** Risk durumu **her sayfada aynı yerde** durur ve boşken de görünür: "sorun yok" da bir
 *  bilgidir ve yokluğuyla değil varlığıyla söylenir (DESIGN.md "Components").
 *
 *  Şiddet hue ile değil **doluluk** ile anlatılıyor: sakin hâlde nötr kenarlık, uyarıda
 *  dolu zemin. Üç tonlu bir uyarı paleti (sarı/turuncu/kırmızı) ilk iki tonu birkaç
 *  haftada görünmez yapardı. */
export function RiskSeridi({ ozet }: { ozet: Ozet | null }) {
  if (!ozet) return null;
  const { saglik, risk } = ozet;

  const uyarilar: { baslik: string; ayrinti: string }[] = [];
  if (saglik.safe_mode) {
    uyarilar.push({
      baslik: "SAFE_MODE",
      ayrinti: `${saglik.safe_mode_sebep || "sebep kayıtlı değil"} · yeni giriş yok, mevcut çıkışlar çalışıyor · çıkış yalnızca elle: sq risk serbest`,
    });
  }
  if (saglik.durdu) {
    uyarilar.push({
      baslik: "KOŞU DURDU",
      ayrinti: "toparlanma ayrışması veya hata · bar işlenmiyor · koşu günlüğüne bakın",
    });
  }
  if (saglik.bayat) {
    uyarilar.push({
      baslik: "VERİ BAYAT",
      ayrinti: `son mesaj ${sureMs(saglik.veri_yasi_ms)} önce · yeni giriş kararı verilmiyor, çıkışlar geçiyor`,
    });
  }
  if (saglik.kesinti_sayisi > 0) {
    uyarilar.push({
      baslik: `${saglik.kesinti_sayisi} KESİNTİ`,
      ayrinti: "sebebi koşu günlüğünde · 30 günlük kesintisiz koşu kriteri sağlanmıyor",
    });
  }

  const sakin = uyarilar.length === 0;

  return (
    <div
      // Sakinken `status` (nazik), uyarıda `alert` (araya girer). Tek bir rol seçmek
      // ya her sakin güncellemede ekran okuyucuyu böler ya da SAFE_MODE'u sıraya koyar;
      // ikisi de yanlış.
      role={sakin ? "status" : "alert"}
      aria-live={sakin ? "polite" : "assertive"}
      className={cn(
        "rounded-md border px-lg py-md",
        sakin
          ? "border-border bg-surface"
          : "border-risk-border bg-risk-surface",
      )}
    >
      {sakin ? (
        <div className="flex flex-wrap items-center gap-md text-label">
          <span className="flex items-center gap-sm text-secondary">
            <Nokta ton="iyi" />
            Risk durumu sakin
          </span>
          <span className="text-tertiary">
            drawdown {(risk.durum.drawdown * 100).toFixed(2)}% · günlük{" "}
            {(risk.durum.gunluk_getiri * 100).toFixed(2)}% · ardışık kayıp{" "}
            {risk.durum.ardisik_kayip}
          </span>
        </div>
      ) : (
        <ul className="flex flex-col gap-sm">
          {uyarilar.map((u) => (
            <li key={u.baslik} className="flex flex-wrap items-baseline gap-sm">
              <span
                className={cn(
                  "rakam text-label font-semibold tracking-label text-risk",
                  u.baslik === "SAFE_MODE" && "nabiz",
                )}
              >
                {u.baslik}
              </span>
              <span className="text-label text-secondary">{u.ayrinti}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
