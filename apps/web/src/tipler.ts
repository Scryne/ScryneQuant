/** API sözleşmesi. `src/scryne_quant/live/api.py` ile elle hizalı tutuluyor.
 *
 *  Üretilmiyor, yazılıyor — ve bu bilinçli: OpenAPI'den tip üretmek bir adım daha ekler
 *  ve o adımın atlandığı gün tipler sessizce eskir. Elle yazılan tip, sunucu değişince
 *  derlenmez; sessiz kalmaz. */

export type Mod = "gozlem" | "paper" | "live";

export interface Portfoy {
  nakit: number;
  miktar: number;
  ortalama_maliyet: number;
  giris_ms: number | null;
}

export interface Saglik {
  baslangic_ms: number | null;
  baslangic_utc: string | null;
  calisma_gun: number;
  kesinti_sayisi: number;
  kesintisiz: boolean;
  durdu: boolean;
  safe_mode: boolean;
  safe_mode_sebep: string;
  bayat: boolean;
  veri_yasi_ms: number | null;
}

export interface Tazelik {
  son_nabiz_ms: number | null;
  yas_ms: number | null;
  azami_yas_ms: number;
  bayat: boolean;
  bayat_giris: number;
  bayat_cikis: number;
}

export interface RiskOzeti {
  mod: string;
  limit_kimligi: string;
  degerlendirilen: number;
  onay: number;
  red: Record<string, number>;
  kisit?: Record<string, number>;
  durum: {
    safe_mode: boolean;
    safe_mode_sebep: string;
    drawdown: number;
    gunluk_getiri: number;
    zirve_ozkaynak: number;
    son_ozkaynak: number;
    ardisik_kayip: number;
    cooldown_bitis_ms: number | null;
    kapanan_islem: number;
    bar_sayisi: number;
    gun_sayisi: number;
  };
  [k: string]: unknown;
}

export interface PencereOzeti {
  sembol: string;
  timeframe: string;
  kapasite: number;
  bar_sayisi: number;
  ilk_ms: number | null;
  son_ms: number | null;
  bayraklar: Record<string, number>;
  bosluk_sayisi: number;
}

export interface KosuKimligi {
  kosu_adi: string;
  mod: Mod;
  sembol: string;
  timeframe: string;
  strateji: { ad: string; parametreler: Record<string, unknown>; [k: string]: unknown };
  limit_kimligi: string;
  baslangic_sermaye: number;
  commit: string;
  dirty: boolean;
  olusturuldu_utc: string;
  [k: string]: unknown;
}

export interface Bekleyen {
  sinyal: { side: string; target_exposure: number; reason: string; timestamp: number };
  hedef_maruziyet: number;
  karar_ms: number;
  kisitlayan: string[];
}

export interface Ozet {
  kosu: KosuKimligi;
  son_bar_ms: number | null;
  fiyat: number | null;
  portfoy: Portfoy;
  ozkaynak: number | null;
  maruziyet: number | null;
  risk: RiskOzeti;
  tazelik: Tazelik;
  pencere: PencereOzeti;
  bekleyen: Bekleyen | null;
  acik_islem: Record<string, number | null> | null;
  kapanan_islem: number;
  durdu: boolean;
  saglik: Saglik;
}

export interface StratejiGorunumu {
  strateji: { ad: string; sinif: string; parametreler: Record<string, unknown> };
  mod: Mod;
  limit_kimligi: string;
  limitler: Record<string, unknown>;
  promotion: Record<string, string>;
  kanit_uretir: boolean;
  sayimlar: {
    degerlendirilen: number;
    onay: number;
    red: Record<string, number>;
    kisit: Record<string, number>;
  };
}

export interface Fill {
  id: number;
  zaman_ms: number;
  zaman_utc: string;
  sinyal_ms: number;
  yon: "AL" | "SAT";
  miktar: number;
  fiyat: number;
  referans_fiyat: number;
  komisyon: number;
  onayli_maruziyet: number;
  kisitlayan: string[];
  nakit_sonra: number;
  miktar_sonra: number;
  ozkaynak_sonra: number;
  gerceklesen_pnl: number | null;
}

export interface PozisyonGorunumu {
  fiyat: number | null;
  portfoy: Portfoy;
  acik: boolean;
  deger: number | null;
  maruziyet: number | null;
  acik_islem: Record<string, number | null> | null;
  bekleyen: Bekleyen | null;
  filller: Fill[];
  fill_sayisi: number;
}

export interface Olay {
  id: number;
  tur: string;
  zaman_ms: number;
  zaman_utc: string;
  bar_ms: number | null;
  ayrinti: Record<string, unknown>;
}

export interface OlayGorunumu {
  olaylar: Olay[];
  kesinti_sayisi: number;
  kesinti_turleri: string[];
}

export interface AuditKaydi {
  id: number;
  tur: string;
  zaman_ms: number;
  zaman_utc: string;
  sembol: string;
  govde: Record<string, unknown>;
  durum: Record<string, unknown>;
  satir_hash: string;
}

export interface AuditGorunumu {
  kayitlar: AuditKaydi[];
  zincir_gecerli: boolean;
}

/* ------------------------------------------------------------ İzleme (Faz 14) */

export type Boyut = "sistem" | "veri" | "trading" | "model";

export interface Alarm {
  kod: string;
  boyut: Boyut;
  seviye: "uyari" | "kritik";
  kosu: string | null;
  mesaj: string;
}

export interface Sapma {
  olculdu: string;
  canli_adim: number;
  ilk_ayrisan_adim: number | null;
  ilk_ayrisan_utc: string | null;
  son_ozkaynak_farki_bps: number;
  canli_islem: number;
  referans_islem: number;
}

export interface IzlenenKosu {
  kosu: string;
  surec_yasiyor: boolean;
  adim?: number;
  son_bar_ms?: number;
  ozkaynak?: number;
  brut?: number;
  safe_mode?: boolean;
  sapma?: Sapma;
}

export interface Izleme {
  var: boolean;
  simdi_ms: number;
  yazildi_ms?: number;
  zaman?: string;
  sistem?: { disk_bos_gb: number; bellek_bos_gb: number | null };
  alarmlar?: Alarm[];
  kosular?: IzlenenKosu[];
}
