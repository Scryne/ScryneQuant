import { Link } from "react-router-dom";
import { cn, useApi, yuzde } from "../lib";
import { Bos, Hucre, Kart, Nokta, Rozet, Tablo } from "../bilesenler/Ilkel";
import type { JevKosuSatiri, JevListesi } from "./tipler";

/** Jev gölge koşuları: **ölçüm**, sinyal değil. Bu tablo Jev'in ne yaptığını gösterir;
 *  isabetli olup olmadığını göstermez — o ayrı bir rapordur ve henüz yok (K-074/7).
 *  Yön dağılımını "kâr" gibi okutacak hiçbir renk kullanılmıyor. */
export function JevOzet() {
  const { veri, hata } = useApi<JevListesi>("/api/jev", 20_000);
  if (hata && !veri) return null;
  if (!veri) return null;
  const kosular = veri.kosular ?? [];
  return (
    <Kart
      baslik="Jev gölge"
      aciklama={veri.not}
      eylem={
        <Rozet ton="sessiz" title="Kanıt sınıfı: ölçüm. Sinyal, risk kararı ve emir üretmez.">
          KANIT DEĞİL
        </Rozet>
      }
    >
      {kosular.length === 0 ? (
        <Bos baslik="Gölge koşusu yok." komut="sq jev golge --kosu golge-1" />
      ) : (
        <Tablo
          basliklar={[
            "Koşu",
            "Süreç",
            "Model",
            "Karar",
            "Hata",
            "Çekimser",
            "Yön dağılımı",
            "Son karar",
            "Gecikme p50",
            "Zincir",
          ]}
          sayisal={[3, 4, 5, 8]}
        >
          {kosular.map((k) => (
            <JevSatir key={k.ad} k={k} />
          ))}
        </Tablo>
      )}
    </Kart>
  );
}

function JevSatir({ k }: { k: JevKosuSatiri }) {
  const son = k.son_karar;
  const p = son?.yon_olasiliklari ?? null;
  return (
    <tr>
      <Hucre className="text-primary">
        <Link
          to={`/jev/${encodeURIComponent(k.ad)}`}
          className="cursor-pointer rounded-sm text-interactive underline decoration-border underline-offset-2 hover:decoration-interactive"
        >
          {k.ad}
        </Link>
        <span className="block text-label text-tertiary">
          {k.mod ?? "—"} · {k.sembol ?? "—"}
        </span>
      </Hucre>
      <Hucre>
        <span className="inline-flex items-center gap-xs">
          <Nokta ton={k.surec_yasiyor === false ? "risk" : k.surec_yasiyor ? "iyi" : "sessiz"} />
          {k.surec_yasiyor === false ? "DURMUŞ" : k.surec_yasiyor ? "Çalışıyor" : "Bilinmiyor"}
        </span>
      </Hucre>
      <Hucre>
        <span className="rakam text-numeric-sm text-secondary">{k.model ?? "—"}</span>
      </Hucre>
      <Hucre sag>
        {k.gecerli ?? "—"}
        <span className="block text-label text-tertiary">/ {k.toplam ?? "—"}</span>
      </Hucre>
      <Hucre sag>
        <span className={cn(k.hata ? "text-risk" : undefined)}>{k.hata ?? "—"}</span>
      </Hucre>
      <Hucre sag>{k.cekimserlik_orani == null ? "—" : yuzde(k.cekimserlik_orani, 0)}</Hucre>
      <Hucre>
        <span className="rakam text-numeric-sm text-secondary">
          {Object.entries(k.yon_dagilimi ?? {})
            .map(([y, n]) => `${y} ${n}`)
            .join(" · ") || "—"}
        </span>
      </Hucre>
      <Hucre>
        {son ? (
          <>
            <span className="text-secondary">
              {son.durum === "gecerli" ? (son.yon ?? "—") : son.durum}
            </span>
            {p && (
              <span className="rakam block text-numeric-sm text-tertiary">
                L {p.long?.toFixed(2)} · F {p.flat?.toFixed(2)} · S {p.short?.toFixed(2)}
              </span>
            )}
            {son.karar_utc && (
              <span className="block text-label text-tertiary">
                {son.karar_utc.slice(5, 16)} UTC · {son.rejim ?? "—"}
              </span>
            )}
          </>
        ) : (
          "—"
        )}
      </Hucre>
      <Hucre sag>{k.gecikme_ms?.p50 == null ? "—" : `${k.gecikme_ms.p50} ms`}</Hucre>
      <Hucre>
        {k.zincir_gecerli == null ? (
          "—"
        ) : k.zincir_gecerli ? (
          <Rozet ton="notr" title="Defter zincir hash'i doğrulandı">
            geçerli
          </Rozet>
        ) : (
          <Rozet ton="risk" title="Defter kurcalanmış olabilir; koşuyu durdur">
            BOZUK
          </Rozet>
        )}
      </Hucre>
    </tr>
  );
}
