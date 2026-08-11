#!/usr/bin/env python3
"""Terminal tabanlı anlık portföy takibi.

Her iki defterdeki varlıkları okur, canlı fiyatlarını çeker ve tabloyu
terminale basar. Sembol sınıflandırması `portfoy_core` ile ortaktır;
kripto varlıklar kripto defterinden gelir, sabit bir liste yoktur.

Alarmlar da burada çalışır: panel kapalıyken tek uyarı yolu budur.
Göstergeler günlük mumla hesaplandığı için 15 dakikada bir tazelenir —
her 60 saniyede 1 yıllık geçmiş indirmenin anlamı yok.

Kullanım:
    python anlik_takip_ajani.py              # bir kez yazdırır ve çıkar
    python anlik_takip_ajani.py --surekli    # varsayılan 60 sn'de bir yeniler
    python anlik_takip_ajani.py --alarmsiz   # alarm denetimini kapatır
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time
from zoneinfo import ZoneInfo

import pandas as pd

import izleme
import piyasa
import portfoy_core as pc
import veri

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

TSI = ZoneInfo("Europe/Istanbul")

# Portföyden bağımsız, her zaman izlenen göstergeler.
SABIT_GOSTERGELER = {
    "GC=F": "Altın (ons, USD)",
    "USDTRY=X": "Dolar / TL",
    "EURTRY=X": "Euro / TL",
}
ONS_GRAM = 31.1035


def defteri_oku(defter):
    try:
        return veri.defter_oku(defter)
    except Exception as hata:
        print(f"⚠️  {defter} defteri okunamadı: {hata}")
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


# Gösterge paketi pahalıdır (sembol başına 1 yıllık geçmiş). Günlük mumla
# çalıştığı için sık tazelemenin faydası yok; sürekli modda 15 dakikada bir.
_gosterge_onbellek = {"zaman": 0.0, "paket": {}}
GOSTERGE_OMRU = 900


def gosterge_paketi_onbellekli(hisseler, kriptolar):
    simdi = time.time()
    taze = simdi - _gosterge_onbellek["zaman"] < GOSTERGE_OMRU
    if taze and _gosterge_onbellek["paket"]:
        return _gosterge_onbellek["paket"]
    paket = piyasa.gosterge_paketi(hisseler, kriptolar)
    _gosterge_onbellek.update(zaman=simdi, paket=paket)
    return paket


def alarmlari_denetle(hisse_semboller, kripto_semboller):
    """Tanımlı alarmları değerlendirir ve tetiklenenleri terminale basar."""
    alarmlar = [a for a in izleme.alarm_oku() if a.get("aktif", True)]
    if not alarmlar:
        return

    # Yalnızca alarmı olan sembollerin geçmişini indir; gerisi boşuna trafik.
    alarmli = {a["sembol"] for a in alarmlar}
    hisseler = tuple(s for s in hisse_semboller if s in alarmli)
    kriptolar = tuple(s for s in kripto_semboller if s in alarmli)
    izleme_hisse, izleme_kripto = izleme.turlere_ayir(izleme.liste_oku())
    hisseler += tuple(s for s in izleme_hisse if s in alarmli and s not in hisseler)
    kriptolar += tuple(s for s in izleme_kripto if s in alarmli and s not in kriptolar)
    if not hisseler and not kriptolar:
        return

    tetiklenen = izleme.alarmlari_degerlendir(
        gosterge_paketi_onbellekli(list(hisseler), list(kriptolar))
    )
    if not tetiklenen:
        return

    print("\n" + "🔔" * 26)
    for olay in tetiklenen:
        deger = olay["deger"]
        deger_metni = deger if isinstance(deger, str) else f"{deger:,.2f}"
        simge = "🟢" if olay["yon"] == "AL" else "🔴"
        print(f"{simge} ALARM — {olay['sembol']}: {olay['kural_adi']} (değer: {deger_metni})")
    print("🔔" * 26)


def bir_tur(alarm_denetle=True):
    hisse_semboller = acik_semboller(defteri_oku("hisse"))
    kripto_semboller = acik_semboller(defteri_oku("kripto"))
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

    if alarm_denetle:
        alarmlari_denetle(hisse_semboller, kripto_semboller)


def main():
    ayristirici = argparse.ArgumentParser(description=__doc__)
    ayristirici.add_argument("--surekli", action="store_true", help="Belirli aralıkla yenile.")
    ayristirici.add_argument(
        "--alarmsiz", action="store_true",
        help="Alarm denetimini kapatır (yalnızca fiyat tablosu gösterilir).",
    )
    ayristirici.add_argument(
        "--aralik", type=int, default=60,
        help="--surekli ile yenileme aralığı (saniye, en az 15). Varsayılan 60.",
    )
    secenekler = ayristirici.parse_args()

    alarm_denetle = not secenekler.alarmsiz
    if not secenekler.surekli:
        bir_tur(alarm_denetle)
        return 0

    # Çok sık sorgulamak sağlayıcıların hız sınırına takılır ve tüm
    # fiyatların N/A dönmesine yol açar.
    aralik = max(15, secenekler.aralik)
    print(f"🚀 Anlık takip başladı ({aralik} sn'de bir). Çıkmak için Ctrl+C.")
    try:
        while True:
            bir_tur(alarm_denetle)
            time.sleep(aralik)
    except KeyboardInterrupt:
        print("\nDurduruldu.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
