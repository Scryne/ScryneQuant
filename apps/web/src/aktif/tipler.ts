/** `/api/aktif` yanıtı (`src/scryne_quant/trader/aktif_panosu.py`). Alan adları oradaki sözlükle aynı. */

export interface EgriNoktasi {
  t: number;
  v: number;
}

export interface Islem {
  t: number;
  sembol: string;
  adet: number;
  fiyat: number;
  notional: number;
  ucret: number;
  neden: "giris" | "cikis" | "donus" | "fren" | string;
}

export interface Pozisyon {
  sembol: string;
  adet: number;
  yon: "long" | "short";
  giris_fiyat: number | null;
  giris_ms: number | null;
}

export interface Hafta {
  hafta: string;
  bas: number;
  son: number;
  getiri: number;
  suruyor: boolean;
}

export interface Olay {
  t: number;
  tur: string;
  ayrinti: string;
}

export interface Fren {
  gun_getiri: number | null;
  hafta_getiri: number | null;
  son_fren_ms: number | null;
  son_fren_sebep: string | null;
}

export interface HesapOzeti {
  ad: string;
  araci: string;
  strateji: string;
  timeframe: string;
  semboller: string[];
  sermaye: number | null;
  para_birimi: string;
  yalniz_long: boolean;
  kapali: boolean;
  var: boolean;
  calisiyor: boolean;
  ozkaynak: number | null;
  son_tur_ms: number | null;
  egri: EgriNoktasi[];
  islemler: Islem[];
  pozisyonlar: Pozisyon[];
  karne: Hafta[];
  olaylar: Olay[];
  fren: Fren | null;
  hafta_islem: number;
  toplam_islem: number;
  toplam_ucret: number;
  swap_toplam: number | null;
}

export interface AktifYaniti {
  zaman_ms: number;
  hesaplar: HesapOzeti[];
  risk: Record<string, number>;
  hata?: string;
}
