"""Trader: strateji → risk → execution hattı döngüsü (paper/shadow/testnet/live). (K-114, R9)

`live/` (Faz 6/14 paper-gözlem motorları, R8'in koştuğu yol) **değişmeden** durur; bu paket
onun yanında, execution hattını (`execution/hat.py`) gerçek emir yoluyla süren ayrı bir
koşucudur. R8 koşusu bu paketi import etmez.
"""
