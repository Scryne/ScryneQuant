/** Gözlem panosunun API sözleşmesi (`live/evren_pano.py`).
 *
 *  Ölçülemeyen her alan `null` — ve arayüz onu "—" olarak çizer. Sıfırla karıştırılmaz:
 *  "pozisyon yok" ile "pozisyon bilinmiyor" aynı ekranda aynı şekilde görünemez.
 */

export type UretimDurumu = "yok" | "hesaplaniyor" | "hazir" | "hata";

export interface KosuSatiri {
  ad: string;
  tur: "evren" | "tek" | "bilinmiyor";
  strateji: string | null;
  parametreler: Record<string, unknown>;
  mod: string;
  sembol: string | null;
  baslangic_sermaye: number | null;
  surec_yasiyor: boolean | null;
  adim: number | null;
  son_bar_utc: string | null;
  ozkaynak: number | null;
  getiri: number | null;
  brut: number | null;
  islem: number | null;
  pozisyon_sayisi: number | null;
  pozisyonlar: string[] | null;
  safe_mode: boolean | null;
  ozkaynak_kaynagi: string | null;
  yazildi_utc: string | null;
  uretim_durumu: UretimDurumu;
}

export interface Alarm {
  kod: string;
  seviye: "uyari" | "kritik";
  boyut: string;
  kosu: string | null;
  mesaj: string;
}

export interface KosuListesi {
  zaman_ms: number;
  kosular: KosuSatiri[];
  izleme: {
    var: boolean;
    yazildi_ms: number | null;
    alarm_sayisi: number;
    alarmlar: Alarm[];
    sistem: { disk_bos_gb: number; bellek_bos_gb: number | null } | null;
  };
}

export interface SeriNoktasi {
  adim?: number;
  ms: number;
  ozkaynak: number;
  brut?: number;
  islem?: number;
  eksik?: number;
}

export interface Olay {
  tur: string;
  zaman_ms: number;
  zaman_utc: string;
  bar_ms: number | null;
  ayrinti: Record<string, unknown>;
}

export interface Fill {
  id: number;
  zaman_ms: number;
  zaman_utc: string;
  yon: string;
  miktar: number;
  fiyat: number;
  referans_fiyat: number;
  komisyon: number;
  ozkaynak_sonra: number;
  gerceklesen_pnl: number | null;
}

export interface Pozisyon {
  sembol: string;
  miktar: number;
  ortalama_maliyet: number;
  son_fiyat: number | null;
  deger: number | null;
  maliyet: number;
  agirlik: number | null;
  gerceklesmemis_pnl: number | null;
  getiri: number | null;
  giris_ms: number | null;
  giris_utc: string | null;
}

export interface Islem {
  sembol: string;
  acilis_ms: number;
  kapanis_ms: number | null;
  acilis_utc: string;
  kapanis_utc: string | null;
  giris_notional: number;
  cikis_notional: number;
  miktar: number;
  komisyon: number;
  slippage: number;
  brut_pnl: number;
  net_pnl: number;
  getiri: number;
  sure_ms: number;
  fill_sayisi: number;
  acik: boolean;
}

export interface Uretim {
  durum: UretimDurumu;
  adim: number | null;
  olculdu_ms: number | null;
  olculdu_utc: string | null;
  sure_s: number | null;
  ozkaynak: number | null;
  pozisyonlar: Pozisyon[];
  islemler: Islem[];
  hata: string | null;
}

export interface KosuDetayi {
  ad: string;
  tur: "evren" | "tek" | "bilinmiyor";
  kimlik: Record<string, unknown> & { strateji_adi?: string; timeframe?: string };
  ozet: KosuSatiri;
  uretim: Uretim;
  seri: SeriNoktasi[];
  seri_nokta?: number;
  olaylar?: Olay[];
  uyelik?: { ay: string; sembol_sayisi: number }[];
  filller?: Fill[];
  isinma_adim?: number;
  hata?: string;
}
