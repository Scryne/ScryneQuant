import { useApi, yuzde } from "../lib";
import type { StratejiGorunumu } from "../tipler";
import { Bos, Hata, Hucre, Kart, Liste, Rozet, Satir, Tablo, Yukleniyor } from "../bilesenler/Ilkel";

const RED_ACIKLAMASI: Record<string, string> = {
  safe_mode: "Kill switch açık; yeni giriş yok (K-008/1)",
  promotion_yok: "Strateji bu mod için promotion zincirini geçmemiş (K-010)",
  gunluk_zarar: "Bu UTC gününün zararı limiti aştı",
  drawdown: "Zirveden düşüş limiti aştı; kill switch tetiklendi",
  cooldown: "Ardışık kayıp penceresi açık",
  volatilite: "ATR/fiyat eşiğin üstünde",
  volatilite_olculemedi: "ATR yok; ölçülemeyen guard geçilmiş sayılmaz",
  sifir_boyut: "Limitler hedefi ölçülemeyecek kadar küçülttü",
  gecersiz_olcum: "Fiyat veya özkaynak geçersiz",
};

/** Strategies (K-012). Ölçülen şey stratejinin kârı değil, **kararlarının nereye
 *  takıldığı**: hangi limit kaç kez reddetti, hangi aşamada duruyor. */
export function Strateji() {
  const { veri, hata, yukleniyor, tazele } = useApi<StratejiGorunumu>("/api/strateji", 15_000);

  if (hata) return <Hata mesaj={hata} tazele={tazele} />;
  if (yukleniyor && !veri) return <Yukleniyor />;
  if (!veri) return null;

  const { sayimlar } = veri;
  const toplamRed = Object.values(sayimlar.red).reduce((a, b) => a + b, 0);
  const redSatirlari = Object.entries(sayimlar.red)
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1]);

  return (
    <div className="flex flex-col gap-lg">
      {/* Ekranda "30 gün kesintisiz" yazan bir kutunun yanında o koşunun kapıya
          sayılmadığı yazmıyorsa, ekran yanıltır (K-035). */}
      {!veri.kanit_uretir && (
        <div className="rounded-md border border-border bg-surface-sunken p-lg">
          <p className="text-h2 font-semibold text-primary">
            Bu koşu promotion kanıtı üretmiyor
          </p>
          <p className="mt-sm text-body text-secondary">
            Mod <code className="rakam text-numeric">{veri.mod}</code>. Gözlem koşusunun
            günleri promotion zincirinin <code className="rakam text-numeric">paper</code>{" "}
            aşamasına sayılmaz (K-035). Altyapıyı ölçer, stratejiyi canlıya yaklaştırmaz.
          </p>
        </div>
      )}

      <div className="grid gap-lg xl:grid-cols-2">
        <Kart baslik="Strateji" aciklama="Koşunun değişmez kimliğinin parçası (K-009)">
          <Liste>
            <Satir etiket="Ad">{veri.strateji.ad}</Satir>
            <Satir etiket="Sınıf">{veri.strateji.sinif}</Satir>
            {Object.entries(veri.strateji.parametreler).map(([ad, deger]) => (
              <Satir key={ad} etiket={ad}>
                {String(deger)}
              </Satir>
            ))}
            <Satir etiket="Risk limitleri">{veri.limit_kimligi.slice(0, 16)}</Satir>
          </Liste>
        </Kart>

        <Kart
          baslik="Promotion zinciri"
          aciklama="Aşama makine kontrolüyle geçilir; elle toggle yok (K-010, K-018)"
        >
          {Object.keys(veri.promotion).length === 0 ? (
            <Bos
              baslik="Hiçbir strateji promotion kaydı taşımıyor."
              komut="sq promotion degerlendir <strateji>"
            />
          ) : (
            <Liste>
              {Object.entries(veri.promotion).map(([ad, asama]) => (
                <Satir key={ad} etiket={ad}>
                  <Rozet ton={asama === "live" ? "risk" : "notr"}>{asama}</Rozet>
                </Satir>
              ))}
            </Liste>
          )}
        </Kart>
      </div>

      <Kart
        baslik="Karar sayımı"
        aciklama={`${sayimlar.degerlendirilen} sinyal değerlendirildi · ${sayimlar.onay} onay · ${toplamRed} red`}
      >
        {redSatirlari.length === 0 ? (
          <Bos baslik="Henüz reddedilmiş sinyal yok." />
        ) : (
          <Tablo basliklar={["Red sebebi", "Sayı", "Pay", "Ne demek"]} sayisal={[1, 2]}>
            {redSatirlari.map(([sebep, n]) => (
              <tr key={sebep} className="transition-colors duration-150 hover:bg-surface-raised">
                <Hucre className="rakam text-primary">{sebep}</Hucre>
                <Hucre sag>{n}</Hucre>
                <Hucre sag>{yuzde(n / Math.max(toplamRed, 1), 1)}</Hucre>
                <Hucre>{RED_ACIKLAMASI[sebep] ?? "—"}</Hucre>
              </tr>
            ))}
          </Tablo>
        )}
      </Kart>

      {Object.values(sayimlar.kisit).some((n) => n > 0) && (
        <Kart
          baslik="Boyut kısıtları"
          aciklama="Onaylanan ama aşağı çekilen hedefler. Risk yukarı asla, aşağı her zaman."
        >
          <Liste>
            {Object.entries(sayimlar.kisit).map(([ad, n]) => (
              <Satir key={ad} etiket={ad}>
                {n}
              </Satir>
            ))}
          </Liste>
        </Kart>
      )}
    </div>
  );
}
