import { kisaZaman, miktar, para, useApi, yerelZaman, yuzde } from "../lib";
import type { PozisyonGorunumu } from "../tipler";
import { Bos, Hata, Hucre, Kart, Liste, Satir, Tablo, Yukleniyor, Yon } from "../bilesenler/Ilkel";

/** Positions (K-012). Fill defteri append-only; burada yalnızca okunuyor. */
export function Pozisyon() {
  const { veri, hata, yukleniyor, tazele } = useApi<PozisyonGorunumu>(
    "/api/pozisyon?limit=200",
    15_000,
  );

  if (hata) return <Hata mesaj={hata} tazele={tazele} />;
  if (yukleniyor && !veri) return <Yukleniyor />;
  if (!veri) return null;

  const giris = veri.portfoy.giris_ms;

  return (
    <div className="flex flex-col gap-lg">
      <div className="grid gap-lg xl:grid-cols-2">
        <Kart baslik="Açık pozisyon">
          {veri.acik ? (
            <Liste>
              <Satir etiket="Miktar">{miktar(veri.portfoy.miktar)}</Satir>
              <Satir etiket="Ortalama maliyet" ipucu="Komisyon dahil">
                {para(veri.portfoy.ortalama_maliyet)}
              </Satir>
              <Satir etiket="Son fiyat">{para(veri.fiyat)}</Satir>
              <Satir etiket="Piyasa değeri">{para(veri.deger)}</Satir>
              <Satir etiket="Maruziyet">{yuzde(veri.maruziyet)}</Satir>
              <Satir etiket="Gerçekleşmemiş">
                <Yon
                  oran={
                    veri.fiyat && veri.portfoy.ortalama_maliyet
                      ? veri.fiyat / veri.portfoy.ortalama_maliyet - 1
                      : null
                  }
                />
              </Satir>
              <Satir etiket="Giriş">{giris == null ? "—" : yerelZaman(giris)}</Satir>
            </Liste>
          ) : (
            <Bos baslik="Pozisyon yok. Nakit tamamen boşta." />
          )}
        </Kart>

        <Kart
          baslik="Bekleyen niyet"
          aciklama="Bu barda onaylandı; bir sonraki barın açılışında dolar (K-004)"
        >
          {veri.bekleyen ? (
            <Liste>
              <Satir etiket="Yön">{veri.bekleyen.sinyal.side}</Satir>
              <Satir etiket="Stratejinin istediği">
                {yuzde(veri.bekleyen.sinyal.target_exposure)}
              </Satir>
              <Satir
                etiket="Riskin onayladığı"
                ipucu="Risk motoru hedefi aşağı çekebilir, yukarı asla"
              >
                {yuzde(veri.bekleyen.hedef_maruziyet)}
              </Satir>
              <Satir etiket="Kısıtlayan limit">
                {veri.bekleyen.kisitlayan.join(" · ") || "yok"}
              </Satir>
              <Satir etiket="Gerekçe">{veri.bekleyen.sinyal.reason}</Satir>
              <Satir etiket="Karar zamanı">{yerelZaman(veri.bekleyen.karar_ms)}</Satir>
            </Liste>
          ) : (
            <Bos baslik="Bekleyen niyet yok." />
          )}
        </Kart>
      </div>

      <Kart
        baslik="Fill defteri"
        aciklama={`${veri.fill_sayisi} fill · append-only · fiyat slippage uygulanmış (K-007)`}
      >
        {veri.filller.length === 0 ? (
          <Bos
            baslik="Henüz fill yok. Koşu başladığından beri hiçbir niyet dolmadı."
            komut="sq paper olaylar <kosu>"
          />
        ) : (
          <Tablo
            basliklar={[
              "Zaman",
              "Yön",
              "Miktar",
              "Fiyat",
              "Kayma",
              "Komisyon",
              "Özkaynak",
              "Gerç. P&L",
            ]}
            sayisal={[2, 3, 4, 5, 6, 7]}
          >
            {veri.filller.map((f) => {
              const kayma = Math.abs(f.fiyat - f.referans_fiyat) * f.miktar;
              return (
                <tr
                  key={f.id}
                  className="transition-colors duration-150 hover:bg-surface-raised"
                >
                  <Hucre>
                    <span className="rakam text-numeric-sm" title={yerelZaman(f.zaman_ms)}>
                      {kisaZaman(f.zaman_ms)}
                    </span>
                  </Hucre>
                  <Hucre className="rakam text-primary">{f.yon}</Hucre>
                  <Hucre sag>{miktar(f.miktar, 6)}</Hucre>
                  <Hucre sag>{para(f.fiyat)}</Hucre>
                  <Hucre sag className="text-tertiary">
                    {para(kayma)}
                  </Hucre>
                  <Hucre sag className="text-tertiary">
                    {para(f.komisyon)}
                  </Hucre>
                  <Hucre sag>{para(f.ozkaynak_sonra)}</Hucre>
                  <Hucre sag>
                    {f.gerceklesen_pnl == null ? (
                      <span className="text-tertiary">—</span>
                    ) : (
                      <span
                        className={
                          f.gerceklesen_pnl > 0
                            ? "text-direction-up"
                            : f.gerceklesen_pnl < 0
                              ? "text-direction-down"
                              : "text-direction-flat"
                        }
                      >
                        {f.gerceklesen_pnl > 0 ? "+" : f.gerceklesen_pnl < 0 ? "−" : "±"}
                        {para(Math.abs(f.gerceklesen_pnl))}
                      </span>
                    )}
                  </Hucre>
                </tr>
              );
            })}
          </Tablo>
        )}
      </Kart>
    </div>
  );
}
