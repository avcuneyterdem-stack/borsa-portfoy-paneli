#!/usr/bin/env python3
"""Gün sonu portföy değeri kaydedici.

Portföyün toplam dolar değerini hesaplayıp `portfoy_gecmisi.xlsx` dosyasına
günlük bir satır olarak yazar. Tüm para hesapları portfoy_core üzerinden
yapılır; bu betiğin kendi kur matematiği yoktur.

Kullanım:
    python otomatik_takip.py                    # bir kez çalışır ve çıkar
    python otomatik_takip.py --surekli          # her gün 23:30'da tekrarlar
    python otomatik_takip.py --log takip.log    # çıktıyı dosyaya da yazar

Windows'ta her gün kendiliğinden çalışması için `kur_gunluk_gorev.ps1`
betiğini kullan; Görev Zamanlayıcı'ya kaydeder. `--surekli` modu bilgisayarın
sürekli açık kalmasını gerektirdiği için ev bilgisayarında iyi bir çözüm
değildir.

Çıkış kodları: 0 kaydedildi · 1 kaydedilemedi · 2 defter bulunamadı
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
import veri

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
kayitci = logging.getLogger("otomatik_takip")

EXCEL_GECMIS = "portfoy_gecmisi.xlsx"
TSI = ZoneInfo("Europe/Istanbul")

def dosya_gunlugu_ekle(dosya):
    """Kök günlükçüye bir dosya tutamağı ekler ve onu döndürür.

    Görev Zamanlayıcı ile çalışırken ekran yoktur; hata olduğunda geriye
    bakılacak tek şey bu dosyadır. Aynı dosya için ikinci kez çağrılırsa
    yeni tutamak eklenmez, yoksa her satır iki kez yazılır.
    """
    tam_yol = os.path.abspath(dosya)
    kok = logging.getLogger()
    for mevcut in kok.handlers:
        if isinstance(mevcut, logging.FileHandler) and \
                os.path.abspath(getattr(mevcut, "baseFilename", "")) == tam_yol:
            return mevcut

    tutamak = logging.FileHandler(tam_yol, encoding="utf-8")
    tutamak.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    kok.addHandler(tutamak)
    return tutamak


GECMIS_SUTUNLARI = [
    "Tarih", "Toplam_Maliyet_USD", "Toplam_Deger_USD", "Acik_KZ_USD",
    "Gerceklesen_KZ_USD", "Gelir_USD", "USDTRY", "Fiyatsiz_Varlik", "Not",
]


def defteri_oku(defter):
    """Defteri veritabanından okur. Okunamıyorsa None döner.

    None ile boş defterin ayrı olması önemli: okunamayan bir defterle
    hesaplanan gün sonu değeri, sessizce eksik bir geçmiş yazar.
    """
    try:
        return veri.defter_oku(defter)
    except Exception as hata:
        kayitci.error("%s defteri okunamadı: %s", defter, hata)
        return None


def gun_sonu_kaydet():
    """Bugünün kapanış değerini hesaplayıp geçmişe yazar."""
    defter_hisse = defteri_oku("hisse")
    defter_kripto = defteri_oku("kripto")

    if defter_hisse is None or defter_kripto is None:
        kayitci.error("Defter okunamadığı için kayıt yapılmadı (veri bozulmasın diye).")
        return 1
    if defter_hisse.empty and defter_kripto.empty:
        kayitci.warning("Defterler boş; kaydedilecek pozisyon yok.")
        return 2

    deger = piyasa.portfoy_degerle(defter_hisse, defter_kripto)

    # Kur olmadan dolar bazlı bir rakam üretmek, sabit bir kur varsaymak
    # demektir; bu sessizce yanlış geçmiş üretir. Kaydetmemek yeğdir.
    if deger["kur_eksik"]:
        kayitci.error("USD/TRY kuru çekilemedi; yanlış değer kaydetmemek için atlanıyor.")
        return 1

    notlar = list(deger["uyarilar"])
    if deger["fiyatsiz"]:
        notlar.append(f"fiyatsız: {', '.join(sorted(deger['fiyatsiz']))}")

    bugun = dt.datetime.now(TSI).strftime("%Y-%m-%d")
    satir = {
        "Tarih": bugun,
        "Toplam_Maliyet_USD": round(deger["maliyet_usd"], 2),
        "Toplam_Deger_USD": round(deger["deger_usd"], 2),
        "Acik_KZ_USD": round(deger["deger_usd"] - deger["maliyet_usd"], 2),
        "Gerceklesen_KZ_USD": round(deger["gerceklesen_kz_usd"], 2),
        "Gelir_USD": round(deger["gelir_usd"], 2),
        "USDTRY": round(deger["kurlar"]["USD"], 4),
        "Fiyatsiz_Varlik": len(deger["fiyatsiz"]),
        "Not": "; ".join(notlar),
    }

    if os.path.exists(EXCEL_GECMIS):
        try:
            gecmis = pd.read_excel(EXCEL_GECMIS)
        except Exception as hata:
            kayitci.error("%s okunamadı, üzerine yazılmıyor: %s", EXCEL_GECMIS, hata)
            return 1
    else:
        gecmis = pd.DataFrame(columns=GECMIS_SUTUNLARI)

    for sutun in GECMIS_SUTUNLARI:
        if sutun not in gecmis.columns:
            gecmis[sutun] = ""
    # Aynı gün yeniden çalışırsa satır güncellenir, çoğalmaz.
    gecmis = gecmis[gecmis["Tarih"].astype(str) != bugun]
    gecmis = pd.concat([gecmis, pd.DataFrame([satir])], ignore_index=True)

    try:
        pc.atomik_yaz(gecmis[GECMIS_SUTUNLARI], EXCEL_GECMIS)
    except Exception as hata:
        kayitci.error("Geçmiş yazılamadı: %s", hata)
        return 1

    kayitci.info(
        "%s kaydedildi — değer $%s | maliyet $%s | açık K/Z $%s%s",
        bugun, f"{satir['Toplam_Deger_USD']:,.2f}", f"{satir['Toplam_Maliyet_USD']:,.2f}",
        f"{satir['Acik_KZ_USD']:,.2f}",
        f" | not: {satir['Not']}" if satir["Not"] else "",
    )
    return 0


def main():
    ayristirici = argparse.ArgumentParser(description=__doc__)
    ayristirici.add_argument(
        "--surekli", action="store_true",
        help="Her gün 23:30'da tekrarla (yerel kullanım için; CI'da kullanmayın).",
    )
    ayristirici.add_argument("--saat", default="23:30", help="--surekli ile çalışma saati (TSİ).")
    ayristirici.add_argument(
        "--log", metavar="DOSYA",
        help="Çıktıyı bu dosyaya da yaz (Görev Zamanlayıcı için).",
    )
    secenekler = ayristirici.parse_args()

    if secenekler.log:
        dosya_gunlugu_ekle(secenekler.log)

    if not secenekler.surekli:
        return gun_sonu_kaydet()

    hedef_saat, hedef_dakika = (int(parca) for parca in secenekler.saat.split(":"))
    kayitci.info("Sürekli mod: her gün %s (TSİ). Çıkmak için Ctrl+C.", secenekler.saat)
    while True:
        simdi = dt.datetime.now(TSI)
        hedef = simdi.replace(hour=hedef_saat, minute=hedef_dakika, second=0, microsecond=0)
        if hedef <= simdi:
            hedef += dt.timedelta(days=1)
        beklenecek = (hedef - simdi).total_seconds()
        kayitci.info("Sonraki kayıt: %s (%.0f dakika sonra)", hedef.strftime("%Y-%m-%d %H:%M"), beklenecek / 60)
        try:
            time.sleep(beklenecek)
        except KeyboardInterrupt:
            kayitci.info("Durduruldu.")
            return 0
        gun_sonu_kaydet()


if __name__ == "__main__":
    sys.exit(main())
