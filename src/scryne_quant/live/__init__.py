"""Canlı çalışma katmanı: akış, bayat-veri guard'ı, paper/gözlem döngüsü. (Faz 6)

Bu paket Faz 3'ün `backtest/` motoruna karşılık gelen **canlı** taraftır ve K-001'in
"backtest = paper = live, tek kod yolu" kuralı burada somutlaşır: fill modeli
(`backtest/fill.py`), portföy (`portfolio/durum.py`), risk motoru (`risk/motor.py`) ve
strateji sözleşmesi (`strategy/`) olduğu gibi kullanılır. Bu paketin eklediği tek şey
**zaman**: barlar bir dosyadan değil bir akıştan gelir, ve akış kesilebilir.

`strategy/` bu paketi göremez (K-003, `tests/unit/test_izolasyon.py`); bu paket
`execution/`in arkasına geçemez (K-032, `tests/unit/test_risk_bypass.py`).
"""
