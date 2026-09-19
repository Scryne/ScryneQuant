"""Jev karar katmanı: **gölgede ölçülen** bir araştırma çıktısı, bir sinyal kaynağı değil. (K-074)

Bu paket alım-satım yolunun (`strategy → risk → execution`) **yanında** yaşar, içinde değil:

- `strategy`, `backtest`, `features`, `risk`, `execution`, `live` bu paketi ve `typesafe`i
  import etmez (`tests/unit/test_gizli_tekrar.py::test_islem_katmani_dedektoru_import_etmez`).
- Bu paket `risk`, `execution`, `oms`u import etmez (`tests/unit/test_jev_izolasyon.py`).
- Jev çıktısından `Sinyal` üreten bir fonksiyon **yoktur** (K-067 aynen yürürlükte).

Bağımlılık yönü tek: `data → features → live/pencere → jev`. Tersi bir import, K-074/2'nin
ihlalidir ve testle yakalanır.
"""
