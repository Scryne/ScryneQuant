import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { useCallback, useEffect, useRef, useState } from "react";

export function cn(...girdi: ClassValue[]) {
  return twMerge(clsx(girdi));
}

/* ------------------------------------------------------------------ biçim */

/** Sayı biçimleri tek yerde. Dağıtılmış `toFixed` çağrıları, aynı büyüklüğün iki yerde
 *  farklı basamakla görünmesiyle biter — ve o fark okuyana "veri değişti" der. */
const TR = "tr-TR";

export function para(deger: number | null | undefined, basamak = 2): string {
  if (deger == null || !Number.isFinite(deger)) return "—";
  return deger.toLocaleString(TR, {
    minimumFractionDigits: basamak,
    maximumFractionDigits: basamak,
  });
}

export function miktar(deger: number | null | undefined, basamak = 8): string {
  if (deger == null || !Number.isFinite(deger)) return "—";
  return deger.toLocaleString(TR, {
    minimumFractionDigits: basamak,
    maximumFractionDigits: basamak,
  });
}

export function yuzde(oran: number | null | undefined, basamak = 2): string {
  if (oran == null || !Number.isFinite(oran)) return "—";
  return `${(oran * 100).toLocaleString(TR, {
    minimumFractionDigits: basamak,
    maximumFractionDigits: basamak,
  })}%`;
}

/** İşaretli yüzde. **İşaret her zaman yazılır** — renk tek başına anlam taşıyamaz
 *  (DESIGN.md "Do's": her risk/yön durumunu metinle de yaz). */
export function isaretliYuzde(oran: number | null | undefined, basamak = 2): string {
  if (oran == null || !Number.isFinite(oran)) return "—";
  const isaret = oran > 0 ? "+" : oran < 0 ? "−" : "±";
  return `${isaret}${yuzde(Math.abs(oran), basamak)}`;
}

export function yon(deger: number | null | undefined): "up" | "down" | "flat" {
  if (deger == null || !Number.isFinite(deger) || deger === 0) return "flat";
  return deger > 0 ? "up" : "down";
}

/* -------------------------------------------------------------------- zaman */

/** Depolama UTC, gösterim yerel — ama **saat dilimi etiketi her zaman yanında** (K-005).
 *  Etiketsiz bir zaman damgası, iki saat diliminin arasında kaybolan bir bardır. */
export function yerelZaman(ms: number | null | undefined): string {
  if (ms == null) return "—";
  const d = new Date(ms);
  const dilim = Intl.DateTimeFormat().resolvedOptions().timeZone;
  return `${d.toLocaleString(TR, { dateStyle: "short", timeStyle: "medium" })} ${dilim}`;
}

export function kisaZaman(ms: number | null | undefined): string {
  if (ms == null) return "—";
  return new Date(ms).toLocaleString(TR, { dateStyle: "short", timeStyle: "short" });
}

/** Bir değerin **yaşı**. Fiyat ve pozisyon gibi bayatlayabilen her şeyin yanında durur. */
export function yas(ms: number | null | undefined, simdi = Date.now()): string {
  if (ms == null) return "—";
  const s = Math.max(0, Math.round((simdi - ms) / 1000));
  if (s < 60) return `${s} sn önce`;
  const dk = Math.round(s / 60);
  if (dk < 60) return `${dk} dk önce`;
  const sa = Math.round(dk / 60);
  if (sa < 48) return `${sa} sa önce`;
  return `${Math.round(sa / 24)} gün önce`;
}

export function sureMs(ms: number | null | undefined): string {
  if (ms == null) return "—";
  const s = Math.round(ms / 1000);
  return s < 90 ? `${s} sn` : `${Math.round(s / 60)} dk`;
}

/* ---------------------------------------------------------------------- API */

export class ApiHatasi extends Error {
  constructor(
    message: string,
    readonly durum: number,
  ) {
    super(message);
  }
}

async function getir<T>(yol: string, isaret?: AbortSignal): Promise<T> {
  const yanit = await fetch(yol, { signal: isaret, headers: { Accept: "application/json" } });
  if (!yanit.ok) throw new ApiHatasi(`${yol} → ${yanit.status}`, yanit.status);
  return (await yanit.json()) as T;
}

export interface Durum<T> {
  veri: T | null;
  hata: string | null;
  yukleniyor: boolean;
  tazele: () => void;
}

/** Tek bir ucu okur. Hata **yutulmaz**: ekranda bir sayı yerine bir hata görünür.
 *
 *  Boş bir tabloyla "her şey yolunda" izlenimi vermek, bu üründe en pahalı arayüz
 *  hatası olurdu — kullanıcı risk uyarısı yok sanır, oysa veri hiç gelmemiştir. */
export function useApi<T>(yol: string, aralikMs = 0): Durum<T> {
  const [veri, setVeri] = useState<T | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [sayac, setSayac] = useState(0);

  const tazele = useCallback(() => setSayac((n) => n + 1), []);

  useEffect(() => {
    const kontrol = new AbortController();
    let iptal = false;
    setYukleniyor(true);
    getir<T>(yol, kontrol.signal)
      .then((g) => {
        if (iptal) return;
        setVeri(g);
        setHata(null);
      })
      .catch((e: unknown) => {
        if (iptal || kontrol.signal.aborted) return;
        setHata(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!iptal) setYukleniyor(false);
      });
    return () => {
      iptal = true;
      kontrol.abort();
    };
  }, [yol, sayac]);

  useEffect(() => {
    if (aralikMs <= 0) return;
    const id = window.setInterval(tazele, aralikMs);
    return () => window.clearInterval(id);
  }, [aralikMs, tazele]);

  return { veri, hata, yukleniyor, tazele };
}

/** SSE aboneliği. Sunucu her işlenmiş barda bir olay yolluyor (`live/api.py`).
 *
 *  Yeniden bağlanma tarayıcıda hazır geliyor — WebSocket yerine SSE seçilmesinin
 *  sebeplerinden biri buydu (K-036). `bagli` bayrağı ekranda gösteriliyor: canlı
 *  olduğunu sanıp ölü bir sayfaya bakmak, bu arayüzde kabul edilebilir değil. */
export function useCanliAkis(yol = "/api/akis") {
  const [bagli, setBagli] = useState(false);
  const [sonOlay, setSonOlay] = useState<{ tur: string; govde: unknown } | null>(null);
  const sayacRef = useRef(0);

  useEffect(() => {
    const kaynak = new EventSource(yol);
    kaynak.onopen = () => setBagli(true);
    kaynak.onerror = () => setBagli(false);
    kaynak.onmessage = (olay) => {
      try {
        sayacRef.current += 1;
        setSonOlay(JSON.parse(olay.data) as { tur: string; govde: unknown });
      } catch {
        /* Bozuk bir kare akışı düşürmemeli; bir sonraki kare doğru gelir. */
      }
    };
    return () => kaynak.close();
  }, [yol]);

  return { bagli, sonOlay };
}
