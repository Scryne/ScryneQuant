-- ScryneQuant — Faz 5 operasyonel şema (PostgreSQL). (K-011, K-032)
--
-- Bu dosya **henüz hiçbir veritabanına uygulanmadı** ve bu bilinçli. K-011 PostgreSQL'i
-- "eşzamanlı yazma, transaction ve dayanıklı state gerektiğinde (paper/live) anlamlı"
-- diye gerekçelendiriyor; Faz 5'te o ihtiyacın hiçbiri yok — tek süreç, tek yazıcı,
-- canlı emir yok. Ayakta bir veritabanı gerektiren bir test takımı, Faz 5'in bitti
-- kriterine hiçbir şey katmadan her koşuya bir bağımlılık eklerdi.
--
-- Ama yazım **yeri** Faz 6'da değişecekse yazım **biçimi** şimdi sabitlenmeli. Buradaki
-- `audit` tablosu `risk/audit.py`'deki `SqliteDefter` ile **aynı kolonları aynı adla**
-- taşıyor ve `tests/unit/test_audit.py` ikisinin ayrışmadığını kontrol ediyor. Faz 6 bir
-- şema tasarımıyla değil, bir bağlantı dizgisiyle başlıyor.
--
-- Uygulama: psql -f migrations/001_faz5.sql

BEGIN;

-- ---------------------------------------------------------------- audit log
--
-- K-008/5: "Tetikleyen sebep, o andaki tüm pozisyon ve emir durumuyla birlikte audit
-- log'a yazılır." Tablo append-only ve bu kural yorumda değil veritabanında: aşağıdaki
-- iki kural (RULE) UPDATE ve DELETE'i sessizce değil, **hatayla** reddediyor.
--
-- `satir_hash` zincir hash'i: her satır kendinden öncekinin hash'ini içeriyor. Tek bir
-- satırı değiştirmek sonraki tüm satırların hash'ini bozar — kurcalamayı engellemez ama
-- **sessiz** kurcalamayı imkânsız kılar.

CREATE TABLE IF NOT EXISTS audit (
    id          BIGSERIAL PRIMARY KEY,
    tur         TEXT        NOT NULL,
    zaman_ms    BIGINT      NOT NULL,  -- olayın ait olduğu BAR zamanı (K-005)
    yazim_ms    BIGINT      NOT NULL,  -- duvar saati; bar zamanından ayrı tutuluyor
    sembol      TEXT        NOT NULL,
    govde       JSONB       NOT NULL,  -- OnayliNiyet.sozluk() / Red.sozluk()
    durum       JSONB       NOT NULL,  -- RiskDurumu.sozluk() (K-008/5)
    onceki_hash TEXT        NOT NULL,
    satir_hash  TEXT        NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS audit_zaman ON audit (zaman_ms);
CREATE INDEX IF NOT EXISTS audit_tur   ON audit (tur, zaman_ms);

-- Trigger, RULE değil. `DO INSTEAD NOTHING` kuralı yazmayı **sessizce yutardı** — yani
-- bir DELETE başarılı görünür, hiçbir şey silinmez ve kimse yanlış bir şey yapıldığını
-- öğrenmez. SQLite tarafındaki `RAISE(ABORT, ...)` ile aynı davranış isteniyor: işlem
-- hatayla düşsün.
CREATE OR REPLACE FUNCTION audit_append_only() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit append-only: % yasak (K-032)', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_guncelleme_yok ON audit;
CREATE TRIGGER audit_guncelleme_yok
    BEFORE UPDATE ON audit FOR EACH ROW EXECUTE FUNCTION audit_append_only();

DROP TRIGGER IF EXISTS audit_silme_yok ON audit;
CREATE TRIGGER audit_silme_yok
    BEFORE DELETE ON audit FOR EACH ROW EXECUTE FUNCTION audit_append_only();

-- ------------------------------------------------------------- risk durumu
--
-- Tek satırlık tablo (`id = 1`): motorun kalıcı hafızası. Faz 6'nın bitti kriteri
-- "süreç öldürülüp yeniden başlatıldığında state doğru toparlanıyor" diyor; risk durumu
-- toparlanmazsa yeniden başlayan süreç günlük zarar limitini sıfırlar — yani süreç her
-- çöküşte kendini affeder.
--
-- `safe_mode` burada kalıcı olmak zorunda: bir çöküşle sıfırlanan kill switch, kill
-- switch değildir.

CREATE TABLE IF NOT EXISTS risk_durumu (
    id                 SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    zirve_ozkaynak     DOUBLE PRECISION NOT NULL DEFAULT 0,
    son_ozkaynak       DOUBLE PRECISION NOT NULL DEFAULT 0,
    gun_basi_ozkaynak  DOUBLE PRECISION NOT NULL DEFAULT 0,
    gun                BIGINT   NOT NULL DEFAULT -1,
    ardisik_kayip      INTEGER  NOT NULL DEFAULT 0,
    cooldown_bitis_ms  BIGINT,
    safe_mode          BOOLEAN  NOT NULL DEFAULT FALSE,
    safe_mode_sebep    TEXT     NOT NULL DEFAULT '',
    safe_mode_ms       BIGINT,
    bar_sayisi         BIGINT   NOT NULL DEFAULT 0,
    gun_sayisi         BIGINT   NOT NULL DEFAULT 0,
    kapanan_islem      BIGINT   NOT NULL DEFAULT 0,
    guncelleme_ms      BIGINT   NOT NULL DEFAULT 0
);

-- -------------------------------------------------------------- promotion
--
-- K-010: "Bir strateji live'a elle bir toggle ile alınamaz." `asama` bir enum değil TEXT:
-- zincire yeni bir aşama eklemek (K-018/3'ün beşinci eşiği, paper/backtest drift) bir
-- migration gerektirmemeli.
--
-- `gecmis` append-only bir JSONB dizisi değil, ayrı bir tablo: bir aşama geçişinin
-- kaydı silinmemeli ve dizinin içine yazmak o garantiyi vermez.

CREATE TABLE IF NOT EXISTS promotion (
    strateji      TEXT PRIMARY KEY,
    asama         TEXT   NOT NULL DEFAULT 'yok',
    guncelleme_ms BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS promotion_gecmis (
    id            BIGSERIAL PRIMARY KEY,
    strateji      TEXT   NOT NULL REFERENCES promotion (strateji),
    zaman_ms      BIGINT NOT NULL,
    onceki_asama  TEXT   NOT NULL,
    asama         TEXT   NOT NULL,
    gecti         BOOLEAN,            -- NULL = ölçülemedi (K-019: geçilmiş sayılmaz)
    gerekce       TEXT   NOT NULL,
    kanit         JSONB  NOT NULL
);

CREATE INDEX IF NOT EXISTS promotion_gecmis_strateji
    ON promotion_gecmis (strateji, zaman_ms);

DROP TRIGGER IF EXISTS promotion_gecmis_silme_yok ON promotion_gecmis;
CREATE TRIGGER promotion_gecmis_silme_yok
    BEFORE DELETE ON promotion_gecmis FOR EACH ROW EXECUTE FUNCTION audit_append_only();

COMMIT;
