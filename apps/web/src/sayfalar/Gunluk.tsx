import { useState } from "react";
import { cn, kisaZaman, useApi, yerelZaman } from "../lib";
import type { AuditGorunumu, OlayGorunumu } from "../tipler";
import { Bos, Hata, Hucre, Kart, Nokta, Rozet, Tablo, Yukleniyor } from "../bilesenler/Ilkel";

const OLAY_ACIKLAMASI: Record<string, string> = {
  basladi: "Süreç başladı",
  toparlandi: "Kayıtlı durumdan toparlandı; yeniden üretilen karar kayıtlıyla uyuştu",
  toparlanma_ayrismasi: "Yeniden üretilen durum kayıtlıyla uyuşmadı — koşu durdu",
  bayat_giris: "Veri bayatladı; yeni giriş durdu",
  bayat_cikis: "Veri tazelendi",
  kopma: "Akış bağlantısı koptu",
  yeniden_baglandi: "Akış geri geldi; eksik barlar tamamlandı",
  kod_degisti: "Koşu farklı bir commit/kütüphane kümesiyle devam etti",
  hata: "Beklenmeyen hata",
  durdu: "Süreç kapandı",
};

/** Logs (K-012). İki defter yan yana: koşunun operasyon günlüğü ve risk audit'i.
 *
 *  Ayrı durmalarının sebebi ikisinin farklı soruları cevaplaması — "sistem ayakta mıydı"
 *  ile "neden bu kararı verdi" aynı tabloya sığmaz. */
export function Gunluk() {
  const [sekme, setSekme] = useState<"kosu" | "audit">("kosu");

  return (
    <div className="flex flex-col gap-lg">
      {/* `role="tablist"` **bilerek kullanılmadı**: o kalıp `aria-controls`, `tabpanel`
          ve ok tuşu gezinmesi ister; üçü olmadan rol vermek, ekran okuyucuya tutmayacağı
          bir söz vermektir. İki durumlu bir seçim için doğru ilkel `aria-pressed`. */}
      <div className="flex gap-xs">
        {(
          [
            ["kosu", "Koşu günlüğü"],
            ["audit", "Risk audit"],
          ] as const
        ).map(([deger, etiket]) => (
          <button
            key={deger}
            type="button"
            aria-pressed={sekme === deger}
            onClick={() => setSekme(deger)}
            className={cn(
              "cursor-pointer rounded-md border px-md py-sm text-label font-medium transition-colors duration-150",
              sekme === deger
                ? "border-interactive-strong/40 bg-interactive-surface text-interactive"
                : "border-border text-secondary hover:bg-surface-raised hover:text-primary",
            )}
          >
            {etiket}
          </button>
        ))}
      </div>

      {sekme === "kosu" ? <KosuGunlugu /> : <AuditGunlugu />}
    </div>
  );
}

function KosuGunlugu() {
  const { veri, hata, yukleniyor, tazele } = useApi<OlayGorunumu>("/api/olay?limit=300", 15_000);

  if (hata) return <Hata mesaj={hata} tazele={tazele} />;
  if (yukleniyor && !veri) return <Yukleniyor />;
  if (!veri) return null;

  return (
    <Kart
      baslik="Koşu günlüğü"
      aciklama={
        veri.kesinti_sayisi === 0
          ? "Kesinti yok. Bayat veri kesinti sayılmaz: koşuyu bölmez, yeni girişi durdurur."
          : `${veri.kesinti_sayisi} kesinti — 30 günlük kesintisiz koşu kriteri sağlanmıyor.`
      }
      eylem={
        <Rozet ton={veri.kesinti_sayisi === 0 ? "notr" : "risk"}>
          {veri.kesinti_sayisi} kesinti
        </Rozet>
      }
    >
      {veri.olaylar.length === 0 ? (
        <Bos baslik="Günlük boş." komut="sq paper baslat <kosu>" />
      ) : (
        <Tablo basliklar={["Zaman", "Olay", "Ne demek", "Ayrıntı"]}>
          {veri.olaylar.map((o) => {
            const kesinti = veri.kesinti_turleri.includes(o.tur);
            return (
              <tr key={o.id} className="transition-colors duration-150 hover:bg-surface-raised">
                <Hucre>
                  <span className="rakam text-numeric-sm" title={yerelZaman(o.zaman_ms)}>
                    {kisaZaman(o.zaman_ms)}
                  </span>
                </Hucre>
                <Hucre>
                  <span className="flex items-center gap-sm">
                    <Nokta ton={kesinti ? "risk" : "sessiz"} />
                    <span className={cn("rakam", kesinti ? "text-risk" : "text-primary")}>
                      {o.tur}
                    </span>
                  </span>
                </Hucre>
                <Hucre>{OLAY_ACIKLAMASI[o.tur] ?? "—"}</Hucre>
                <Hucre>
                  <code className="rakam text-numeric-sm text-tertiary">
                    {JSON.stringify(o.ayrinti)}
                  </code>
                </Hucre>
              </tr>
            );
          })}
        </Tablo>
      )}
    </Kart>
  );
}

function AuditGunlugu() {
  const { veri, hata, yukleniyor, tazele } = useApi<AuditGorunumu>("/api/audit?limit=300", 30_000);

  if (hata) return <Hata mesaj={hata} tazele={tazele} />;
  if (yukleniyor && !veri) return <Yukleniyor />;
  if (!veri) return null;

  return (
    <Kart
      baslik="Risk audit defteri"
      aciklama="Append-only, zincir hash'li. Bir kararın sonradan düzeltilebildiği tablo, kayıt değil not defteridir (K-032)."
      eylem={
        /* "Kurcalanmadı" bilgisi, ancak gösterildiğinde bir güvence. */
        <Rozet ton={veri.zincir_gecerli ? "notr" : "risk"}>
          {veri.zincir_gecerli ? "zincir geçerli" : "ZİNCİR BOZUK"}
        </Rozet>
      }
    >
      {veri.kayitlar.length === 0 ? (
        <Bos baslik="Henüz risk kararı kaydedilmedi." />
      ) : (
        <Tablo basliklar={["Zaman", "Tür", "Karar", "Sebep / hedef", "Hash"]}>
          {veri.kayitlar.map((k) => {
            const govde = k.govde as Record<string, unknown>;
            const red = govde.karar === "red";
            return (
              <tr key={k.id} className="transition-colors duration-150 hover:bg-surface-raised">
                <Hucre>
                  <span className="rakam text-numeric-sm" title={yerelZaman(k.zaman_ms)}>
                    {kisaZaman(k.zaman_ms)}
                  </span>
                </Hucre>
                <Hucre className="rakam text-primary">{k.tur}</Hucre>
                <Hucre>
                  <span className={cn("rakam", k.tur === "kill" && "text-risk")}>
                    {String(govde.karar ?? k.tur)}
                  </span>
                </Hucre>
                <Hucre>
                  {red
                    ? String(govde.sebep ?? "—")
                    : govde.onayli_maruziyet != null
                      ? `${((govde.onayli_maruziyet as number) * 100).toFixed(2)}% (istenen ${(
                          (govde.istenen_maruziyet as number) * 100
                        ).toFixed(2)}%)`
                      : String(govde.sebep ?? "—")}
                </Hucre>
                <Hucre>
                  <code className="rakam text-numeric-sm text-tertiary">
                    {k.satir_hash.slice(0, 10)}
                  </code>
                </Hucre>
              </tr>
            );
          })}
        </Tablo>
      )}
    </Kart>
  );
}
