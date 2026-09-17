import { isaretliYuzde, miktar, para, yas, yerelZaman, yuzde } from "../lib";
import type { Ozet } from "../tipler";
import { Kart, Liste, Olcum, Satir, Yon } from "../bilesenler/Ilkel";
import { IzlemeBolumu } from "../bilesenler/Izleme";

/** Overview (K-012). Ana bilgi hiyerarşisi §29'dan: Signal → Decision → Risk → Execution
 *  → Outcome. Ekran yukarıdan aşağı bu sırayı izliyor. */
export function Genel({ ozet }: { ozet: Ozet }) {
  const getiri =
    ozet.ozkaynak == null
      ? null
      : ozet.ozkaynak / ozet.kosu.baslangic_sermaye - 1;
  const risk = ozet.risk.durum;

  return (
    <div className="flex flex-col gap-lg">
      {/* Faz 14: host koşularının dört gözlem boyutu. Beşinci sayfa değil (K-012):
          Overview "sürekli çalışan şeyi izlemek" sayfası ve izleme tam olarak o. */}
      <IzlemeBolumu />
      <div className="grid gap-md sm:grid-cols-2 xl:grid-cols-4">
        <Olcum
          etiket="Portföy değeri"
          deger={para(ozet.ozkaynak)}
          alt={
            <>
              başlangıç {para(ozet.kosu.baslangic_sermaye)} · <Yon oran={getiri} />
            </>
          }
        />
        <Olcum
          etiket="Günlük getiri"
          deger={isaretliYuzde(risk.gunluk_getiri)}
          vurgu={risk.gunluk_getiri > 0 ? "up" : risk.gunluk_getiri < 0 ? "down" : "flat"}
          alt="gün dönümünde sıfırlanır (UTC)"
        />
        <Olcum
          etiket="Düşüş (drawdown)"
          deger={yuzde(risk.drawdown)}
          vurgu={risk.safe_mode ? "risk" : "flat"}
          alt={`zirve ${para(risk.zirve_ozkaynak)}`}
        />
        <Olcum
          etiket="Maruziyet"
          deger={yuzde(ozet.maruziyet)}
          alt={
            ozet.fiyat == null
              ? "fiyat yok"
              : `${miktar(ozet.portfoy.miktar)} @ ${para(ozet.fiyat)}`
          }
        />
      </div>

      <div className="grid gap-lg xl:grid-cols-2">
        <Kart baslik="Pozisyon" aciklama="Açık pozisyon ve bekleyen niyet">
          <Liste>
            <Satir etiket="Durum">
              {ozet.portfoy.miktar > 0 ? "Açık" : "Pozisyon yok"}
            </Satir>
            <Satir etiket="Miktar">{miktar(ozet.portfoy.miktar)}</Satir>
            <Satir
              etiket="Ortalama maliyet"
              ipucu="Komisyon dahil — 'kaça mal oldu' sorusunun dürüst cevabı"
            >
              {para(ozet.portfoy.ortalama_maliyet)}
            </Satir>
            <Satir etiket="Nakit">{para(ozet.portfoy.nakit)}</Satir>
            <Satir
              etiket="Bekleyen niyet"
              ipucu="Bu barda onaylandı; bir sonraki barın açılışında dolar (K-004)"
            >
              {ozet.bekleyen
                ? `${ozet.bekleyen.sinyal.side} → ${yuzde(ozet.bekleyen.hedef_maruziyet)}`
                : "yok"}
            </Satir>
          </Liste>
        </Kart>

        <Kart baslik="Risk motoru" aciklama="Kararların sayımı ve limit durumu">
          <Liste>
            <Satir etiket="Değerlendirilen sinyal">{ozet.risk.degerlendirilen}</Satir>
            <Satir etiket="Onaylanan">{ozet.risk.onay}</Satir>
            <Satir etiket="Reddedilen">
              {Object.values(ozet.risk.red).reduce((a, b) => a + b, 0)}
            </Satir>
            <Satir etiket="Kapanan işlem">{risk.kapanan_islem}</Satir>
            <Satir etiket="Ardışık kayıp">{risk.ardisik_kayip}</Satir>
            <Satir etiket="Cooldown">
              {risk.cooldown_bitis_ms == null
                ? "yok"
                : `${yerelZaman(risk.cooldown_bitis_ms)}'e kadar`}
            </Satir>
          </Liste>
        </Kart>

        <Kart baslik="Veri sağlığı" aciklama="Akış, pencere ve kalite bayrakları">
          <Liste>
            <Satir etiket="Son bar">
              {ozet.son_bar_ms == null
                ? "—"
                : `${yerelZaman(ozet.son_bar_ms)} · ${yas(ozet.son_bar_ms)}`}
            </Satir>
            <Satir etiket="Veri yaşı" ipucu="Akıştan gelen son mesajın üzerinden geçen süre">
              {ozet.tazelik.yas_ms == null
                ? "hiç mesaj alınmadı"
                : `${(ozet.tazelik.yas_ms / 1000).toFixed(1)} sn / eşik ${(
                    ozet.tazelik.azami_yas_ms / 1000
                  ).toFixed(0)} sn`}
            </Satir>
            <Satir etiket="Pencere">
              {ozet.pencere.bar_sayisi} / {ozet.pencere.kapasite} bar
            </Satir>
            <Satir etiket="Boşluk">{ozet.pencere.bosluk_sayisi}</Satir>
            <Satir etiket="Kalite bayrakları">
              {Object.entries(ozet.pencere.bayraklar)
                .map(([ad, n]) => `${ad} ${n}`)
                .join(" · ") || "—"}
            </Satir>
            <Satir etiket="Bayat girişi">{ozet.tazelik.bayat_giris}</Satir>
          </Liste>
        </Kart>

        <Kart baslik="Sistem" aciklama="Koşunun kimliği ve kesintisizliği">
          <Liste>
            <Satir etiket="Çalışma süresi">
              {ozet.saglik.calisma_gun.toFixed(2)} gün / 30
            </Satir>
            <Satir
              etiket="Kesinti"
              ipucu="Bayat veri kesinti sayılmaz: koşuyu bölmez, yalnızca yeni girişi durdurur"
            >
              {ozet.saglik.kesinti_sayisi}
            </Satir>
            <Satir etiket="Mod">{ozet.kosu.mod}</Satir>
            <Satir etiket="Commit">
              {ozet.kosu.commit.slice(0, 12)}
              {ozet.kosu.dirty ? " (DIRTY)" : ""}
            </Satir>
            <Satir etiket="Risk limitleri">{ozet.kosu.limit_kimligi.slice(0, 12)}</Satir>
            <Satir etiket="Başlangıç">{ozet.kosu.olusturuldu_utc}</Satir>
          </Liste>
        </Kart>
      </div>
    </div>
  );
}
