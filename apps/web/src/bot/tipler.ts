/** `/api/bot` yanıtı (`src/scryne_quant/trader/bot_panosu.py`). Alanlar oradaki sözlükle aynı adda. */

export interface KosuOzeti {
  ad: string;
  mod: string | null;
  strateji: string | null;
  sembol: string | null;
  canli: boolean;
  kapatildi: boolean;
  halt: string;
  safe_mode: boolean;
  son_bar_utc: string | null;
  veri_yasi_ms: number | null;
  bar: number | null;
  hata: number;
  ozkaynak: number | null;
  durum_ms: number | null;
}

export interface Hesap {
  sembol?: string;
  nakit?: number;
  miktar?: number;
  fiyat?: number;
  pozisyon_degeri?: number;
  ozkaynak?: number;
  maruziyet?: number;
  komisyon_toplam?: number;
  drawdown?: number;
  gunluk_getiri?: number;
  pnl?: number;
}

export interface EgriNoktasi {
  bar_ms: number;
  ozkaynak: number;
  maruziyet: number;
  fiyat: number;
}

export interface Emir {
  istemci_kimligi: string;
  yon: string;
  miktar: number;
  dolan_miktar: number | null;
  ortalama_fiyat: number | null;
  durum: string;
  olusturuldu_ms: number;
  guncellendi_ms: number | null;
  komisyon: number | null;
  tur: string | null;
  hata: string | null;
}

export interface Denge {
  hedef: number;
  bant: number;
  maruziyet: number;
  alis_tetigi: number | null;
  satis_tetigi: number | null;
  fiyat: number | null;
}

export interface Secili {
  ad: string;
  mod: string | null;
  kosu: {
    kosu_adi?: string;
    mod?: string;
    risk_modu?: string;
    strateji?: string;
    parametreler?: Record<string, unknown>;
    sembol?: string;
    timeframe?: string;
    sermaye_usdt?: number;
  };
  hesap: Hesap;
  limitler: {
    sermaye_usdt?: number;
    azami_maruziyet?: number;
    azami_brut_maruziyet?: number;
    gunluk_zarar_limiti?: number;
    drawdown_limiti?: number;
  };
  risk: {
    zirve_ozkaynak?: number;
    son_ozkaynak?: number;
    gun_basi_ozkaynak?: number;
    ardisik_kayip?: number;
    cooldown_bitis_ms?: number | null;
    safe_mode?: boolean;
    safe_mode_sebep?: string;
    drawdown?: number;
    gunluk_getiri?: number;
    kapanan_islem?: number;
  };
  risk_modu: string | null;
  sayac: Record<string, number>;
  veri_tazeligi: { son_bar_ms?: number; son_bar_utc?: string; kapanistan_beri_ms?: number };
  son_hata: string;
  halt: string;
  safe_mode: boolean;
  baglanti: { ok?: boolean; saat_sapmasi_ms?: number };
  baslangic_ms: number | null;
  egri: EgriNoktasi[];
  emirler: Emir[];
  denge: Denge | null;
  durum_ms: number | null;
}

export interface Kontrol {
  ad: string;
  gecti: boolean | null;
  ayrinti: string;
  engel?: string;
}

export interface Hazirlik {
  hata?: string;
  pilot_hazir?: boolean;
  sistem_hazir?: boolean;
  strateji_hazir?: boolean;
  pilot?: Kontrol[];
  sistem?: Kontrol[];
  pilot_gosterim_gun?: number;
  gosterim_gun?: number;
}

export interface BotYaniti {
  zaman_ms: number;
  zaman_utc: string;
  kosular: KosuOzeti[];
  secili: Secili | null;
  pilot: {
    kademe: number;
    strateji: string;
    sembol: string;
    sermaye_usdt: number;
    azami_kayip_usdt: number;
  } | null;
  hazirlik: Hazirlik | null;
  sistem: {
    mod: string;
    commit: string | null;
    dirty: boolean | null;
    testler: { commit?: string; dirty?: boolean; gecen?: number; kalan?: number; zaman_utc?: string } | null;
  };
}
