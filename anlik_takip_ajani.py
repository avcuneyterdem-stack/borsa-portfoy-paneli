#!/usr/bin/env python3
"""Terminal tabanlı anlık portföy takibi.

Her iki defterdeki varlıkları okur, canlı fiyatlarını çeker ve tabloyu
terminale basar. Sembol sınıflandırması `portfoy_core` ile ortaktır;
kripto varlıklar kripto defterinden gelir, sabit bir liste yoktur.

Kullanım:
    python anlik_takip_ajani.py            # bir kez yazdırır ve çıkar
    python anlik_takip_ajani.py --surekli  # varsayılan 60 sn'de bir yeniler
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import sys
import time
from zoneinfo import ZoneInfo

import pandas as pd

import piyasa
import portfoy_core as pc

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

EXCEL_HISSE = "portfoy_defteri_hisse.xlsx"
EXCEL_KRIPTO = "portfoy_defteri_kripto.xlsx"
TSI = ZoneInfo("Europe/Istanbul")

# Portföyden bağımsız, her zaman izlenen göstergeler.
SABIT_GOSTERGELER = {
    "GC=F": "Altın (ons, USD)",
    "USDTRY=X": "Dolar / TL",
    "EURTRY=X": "Euro / TL",
}
ONS_GRAM = 31.1035


def defteri_oku(dosya):
    if not os.path.exists(dosya):
        return pc.bos_defter()
    try:
        return pc.sema_uygula(pd.read_excel(dosya))
    except Exception as hata:
        print(f"⚠️  {dosya} okunamadı: {hata}")
        return pc.bos_defter()


def acik_semboller(defter):
    """Yalnızca elde pozisyonu kalan sembolleri döndürür."""
    if defter.empty:
        return []
    return sorted({
        sembol for sembol in set(defter["Hisse"]) - {""}
        if pc.satilabilir_adet(defter, sembol) > 1e-9
    })


def tabloyu_kur(hisse_semboller, kripto_semboller):
    satirlar = []

    fiyatlar = piyasa.hisse_fiyatlari(list(hisse_semboller) + list(SABIT_GOSTERGELER))
    kripto = piyasa.kripto_fiyatlari(kripto_semboller)

    # Gram altın, ons ve dolar kurundan türetilir; ikisi de yoksa gösterilmez.
    ons = fiyatlar.get("GC=F", {}).get("fiyat")
    usdtry = fiyatlar.get("USDTRY=X", {}).get("fiyat")
    if ons and usdtry:
        satirlar.append({
            "Varlık": "Gram Altın (TL)", "Sembol": "hesaplanan",
            "Son Fiyat": f"{ons * usdtry / ONS_GRAM:,.2f}", "Birim": "TRY",
            "Günlük": "—", "RSI": "—",
        })

    for sembol, etiket in SABIT_GOSTERGELER.items():
        veri = fiyatlar.get(sembol, {})
        satirlar.append({
            "Varlık": etiket, "Sembol": sembol,
            "Son Fiyat": f"{veri['fiyat']:,.2f}" if veri.get("fiyat") else "N/A",
            "Birim": "TRY" if sembol.endswith("TRY=X") else "USD",
            "Günlük": f"%{veri['degisim']:+.2f}" if veri.get("degisim") is not None else "N/A",
            "RSI": veri.get("rsi") if veri.get("rsi") is not None else "—",
        })

    for sembol in hisse_semboller:
        kod = pc.sembol_normalize(sembol)
        veri = fiyatlar.get(kod, {})
        satirlar.append({
            "Varlık": sembol, "Sembol": kod,
            "Son Fiyat": f"{veri['fiyat']:,.2f}" if veri.get("fiyat") else "N/A",
            "Birim": pc.varsayilan_borsa_pb(kod),
            "Günlük": f"%{veri['degisim']:+.2f}" if veri.get("degisim") is not None else "N/A",
            "RSI": veri.get("rsi") if veri.get("rsi") is not None else "—",
        })

    for sembol in kripto_semboller:
        veri = kripto.get(str(sembol).upper(), {})
        satirlar.append({
            "Varlık": sembol, "Sembol": f"{sembol}USDT",
            "Son Fiyat": f"{veri['fiyat']:,.4f}" if veri.get("fiyat") else "N/A",
            "Birim": "USDT",
            "Günlük": f"%{veri['degisim']:+.2f}" if veri.get("degisim") is not None else "N/A",
            "RSI": "—",
        })

    return pd.DataFrame(satirlar)


def bir_tur():
    hisse_semboller = acik_semboller(defteri_oku(EXCEL_HISSE))
    kripto_semboller = acik_semboller(defteri_oku(EXCEL_KRIPTO))
    tablo = tabloyu_kur(hisse_semboller, kripto_semboller)

    zaman = dt.datetime.now(TSI).strftime("%Y-%m-%d %H:%M:%S")
    print("=" * 78)
    print(f"⏱️  {zaman} (TSİ)  |  {len(hisse_semboller)} hisse · {len(kripto_semboller)} kripto")
    print("-" * 78)
    print(tablo.to_string(index=False) if not tablo.empty else "Takip edilecek varlık yok.")

    fiyatsiz = int((tablo["Son Fiyat"] == "N/A").sum()) if not tablo.empty else 0
    if fiyatsiz:
        print(f"\n⚠️  {fiyatsiz} varlığın fiyatı çekilemedi (N/A). Değerler eksiktir.")
    print("=" * 78)


def main():
    ayristirici = argparse.ArgumentParser(description=__doc__)
    ayristirici.add_argument("--surekli", action="store_true", help="Belirli aralıkla yenile.")
    ayristirici.add_argument(
        "--aralik", type=int, default=60,
        help="--surekli ile yenileme aralığı (saniye, en az 15). Varsayılan 60.",
    )
    secenekler = ayristirici.parse_args()

    if not secenekler.surekli:
        bir_tur()
        return 0

    # Çok sık sorgulamak sağlayıcıların hız sınırına takılır ve tüm
    # fiyatların N/A dönmesine yol açar.
    aralik = max(15, secenekler.aralik)
    print(f"🚀 Anlık takip başladı ({aralik} sn'de bir). Çıkmak için Ctrl+C.")
    try:
        while True:
            bir_tur()
            time.sleep(aralik)
    except KeyboardInterrupt:
        print("\nDurduruldu.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
