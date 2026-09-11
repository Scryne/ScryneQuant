import { Navigate, Route, Routes } from "react-router-dom";
import { useApi, useCanliAkis } from "./lib";
import type { Ozet } from "./tipler";
import { Kabuk } from "./bilesenler/Kabuk";
import { RiskSeridi } from "./bilesenler/RiskSeridi";
import { Hata, Yukleniyor } from "./bilesenler/Ilkel";
import { Genel } from "./sayfalar/Genel";
import { Strateji } from "./sayfalar/Strateji";
import { Pozisyon } from "./sayfalar/Pozisyon";
import { Gunluk } from "./sayfalar/Gunluk";

export function App() {
  const { bagli, sonOlay } = useCanliAkis();
  /* SSE canlı güncellemeyi getiriyor; yoklama onun **yedeği**. 20 saniye, 1h
     timeframe'de fazlasıyla sık — ama ölçtüğü şey bar değil, sürecin ayakta olduğu.
     SSE düştüğünde ekranın sessizce eskimemesi buna bağlı. */
  const { veri, hata, yukleniyor, tazele } = useApi<Ozet>("/api/ozet", 20_000);

  /* Canlı olaydaki gövde yoklamayla aynı şekle sahip; hangisi daha yeniyse o gösterilir. */
  const canli = (sonOlay?.govde as Ozet | undefined) ?? null;
  const ozet =
    canli && veri
      ? (canli.son_bar_ms ?? 0) >= (veri.son_bar_ms ?? 0)
        ? canli
        : veri
      : (canli ?? veri);

  return (
    <Kabuk ozet={ozet} bagli={bagli}>
      <div className="flex flex-col gap-lg">
        <RiskSeridi ozet={ozet} />
        {hata && !ozet ? (
          <Hata mesaj={hata} tazele={tazele} />
        ) : yukleniyor && !ozet ? (
          <Yukleniyor etiket="Koşu durumu alınıyor" />
        ) : ozet ? (
          <Routes>
            <Route path="/" element={<Genel ozet={ozet} />} />
            <Route path="/strateji" element={<Strateji />} />
            <Route path="/pozisyon" element={<Pozisyon />} />
            <Route path="/gunluk" element={<Gunluk />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        ) : null}
      </div>
    </Kabuk>
  );
}
