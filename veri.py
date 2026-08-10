"""Defterlerin SQLite deposu.

Excel yerine tek dosyalık bir veritabanı. Üç sebep:

1. **Eşzamanlı yazma.** Panel açıkken görev zamanlayıcı da yazabiliyor.
   Excel'de bu, dosyanın kilitlenmesi veya son yazanın diğerini ezmesi
   demekti; SQLite'ta işlem (transaction) düzeyinde çözülür.
2. **Senkron çakışması.** Defterler OneDrive klasöründeyken iki cihazdan
   açılınca OneDrive "çakışan kopya" üretiyor ve hangisinin doğru olduğunu
   kimse bilmiyordu.
3. **Satır kimliği.** Excel satırının kimliği yoktu; "şu kaydı düzelt" veya
   "şu kaydı sil" demek mümkün değildi. Artık her işlemin `id`'si var.

Tasarım kararı: bu modül DataFrame alır, DataFrame verir. `portfoy_core`
hiç değişmez — para hesaplarının tamamı ve testleri olduğu gibi kalır.
Depo değişti, muhasebe değişmedi.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import logging
import os
import shutil
import sqlite3

import pandas as pd

import portfoy_core as pc

kayitci = logging.getLogger(__name__)

VERITABANI = "portfoy.db"
DEFTERLER = ("hisse", "kripto")
SEMA_SURUMU = 1

# Excel defterlerinin eski yolları — otomatik geçiş bunları arar.
ESKI_EXCEL = {"hisse": "portfoy_defteri_hisse.xlsx", "kripto": "portfoy_defteri_kripto.xlsx"}


def _sutun_tanimlari():
    """Şema sütunları: metinler TEXT, sayılar REAL."""
    parcalar = []
    for sutun in pc.ZORUNLU_SUTUNLAR:
        tur = "REAL" if sutun in pc.SAYISAL_SUTUNLAR else "TEXT"
        parcalar.append(f'"{sutun}" {tur}')
    return ",\n    ".join(parcalar)


@contextlib.contextmanager
def baglan(dosya=VERITABANI):
    """Şemayı hazır bir bağlantı verir; çıkışta commit veya rollback yapar.

    WAL kipi: okuyucular yazarı, yazar okuyucuları bloke etmez. Panel açıkken
    görev zamanlayıcının yazabilmesi buna bağlı.

    timeout: kilit varsa hemen hata vermek yerine 10 saniye bekler — iki
    süreç aynı anda yazmaya kalkarsa biri sırasını bekler, veri kaybolmaz.
    """
    baglanti = sqlite3.connect(dosya, timeout=10.0)
    baglanti.row_factory = sqlite3.Row
    try:
        baglanti.execute("PRAGMA journal_mode=WAL")
        baglanti.execute("PRAGMA foreign_keys=ON")
        sema_kur(baglanti)
        yield baglanti
        baglanti.commit()
    except Exception:
        baglanti.rollback()
        raise
    finally:
        baglanti.close()


def sema_kur(baglanti):
    """Tabloları yoksa oluşturur. Var olan veriye dokunmaz."""
    baglanti.execute(f"""
        CREATE TABLE IF NOT EXISTS islemler (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            defter TEXT NOT NULL CHECK (defter IN ('hisse', 'kripto')),
            {_sutun_tanimlari()},
            olusturma TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    baglanti.execute("CREATE INDEX IF NOT EXISTS ix_islemler_defter ON islemler(defter)")
    baglanti.execute("CREATE INDEX IF NOT EXISTS ix_islemler_hisse ON islemler(defter, \"Hisse\")")
    baglanti.execute("CREATE TABLE IF NOT EXISTS sema (surum INTEGER NOT NULL)")
    if baglanti.execute("SELECT COUNT(*) FROM sema").fetchone()[0] == 0:
        baglanti.execute("INSERT INTO sema (surum) VALUES (?)", (SEMA_SURUMU,))


def _defter_dogrula(defter):
    if defter not in DEFTERLER:
        raise ValueError(f"Defter 'hisse' veya 'kripto' olmalı, '{defter}' değil.")


# ===========================================================================
# OKUMA
# ===========================================================================

def defter_oku(defter, dosya=VERITABANI):
    """Bir defteri DataFrame olarak verir; `id` sütunu dahil.

    Şema `portfoy_core.sema_uygula` ile uygulanır, yani panelin ve hesap
    katmanının gördüğü tablo Excel dönemindekiyle birebir aynı biçimdedir.
    """
    _defter_dogrula(defter)
    if not os.path.exists(dosya):
        return pc.bos_defter()

    with baglan(dosya) as baglanti:
        satirlar = baglanti.execute(
            'SELECT id, * FROM islemler WHERE defter = ? ORDER BY id', (defter,)
        ).fetchall()

    if not satirlar:
        return pc.bos_defter()

    cerceve = pd.DataFrame([dict(satir) for satir in satirlar])
    cerceve = cerceve.drop(columns=["defter"], errors="ignore")
    return pc.sema_uygula(cerceve)


def kayit_getir(kayit_id, dosya=VERITABANI):
    """Tek bir işlemi sözlük olarak verir; yoksa None."""
    if not os.path.exists(dosya):
        return None
    with baglan(dosya) as baglanti:
        satir = baglanti.execute("SELECT * FROM islemler WHERE id = ?", (kayit_id,)).fetchone()
    return dict(satir) if satir else None


def sayim(dosya=VERITABANI):
    """Defter başına kayıt sayısı: {"hisse": n, "kripto": n}"""
    if not os.path.exists(dosya):
        return {defter: 0 for defter in DEFTERLER}
    with baglan(dosya) as baglanti:
        satirlar = baglanti.execute(
            "SELECT defter, COUNT(*) AS adet FROM islemler GROUP BY defter").fetchall()
    sonuc = {defter: 0 for defter in DEFTERLER}
    for satir in satirlar:
        sonuc[satir["defter"]] = satir["adet"]
    return sonuc


# ===========================================================================
# YAZMA
# ===========================================================================

def _kayit_degerleri(kayit):
    """Sözlüğü şema sırasına dizer; eksik alanlar None olur."""
    degerler = []
    for sutun in pc.ZORUNLU_SUTUNLAR:
        deger = kayit.get(sutun)
        if deger is None or (isinstance(deger, float) and pd.isna(deger)):
            degerler.append(None)
        elif sutun in pc.SAYISAL_SUTUNLAR:
            degerler.append(float(deger))
        else:
            degerler.append(str(deger))
    return degerler


def islem_ekle(defter, kayit, dosya=VERITABANI):
    """Tek işlem ekler ve yeni kaydın id'sini döndürür."""
    _defter_dogrula(defter)
    sutunlar = ", ".join(f'"{s}"' for s in pc.ZORUNLU_SUTUNLAR)
    yer_tutucu = ", ".join("?" for _ in pc.ZORUNLU_SUTUNLAR)
    with baglan(dosya) as baglanti:
        imlec = baglanti.execute(
            f"INSERT INTO islemler (defter, {sutunlar}) VALUES (?, {yer_tutucu})",
            [defter] + _kayit_degerleri(kayit),
        )
        return imlec.lastrowid


def islem_guncelle(kayit_id, alanlar, dosya=VERITABANI):
    """Var olan bir işlemin alanlarını değiştirir.

    Döner: değişen satır sayısı (0 = böyle bir kayıt yok).
    Yalnızca şemadaki sütunlar kabul edilir; bilinmeyen alan sessizce
    yok sayılmaz, hata verir — yazım hatası yüzünden güncellenmemiş bir
    kayıt en kötü sonuçtur.
    """
    bilinmeyen = set(alanlar) - set(pc.ZORUNLU_SUTUNLAR)
    if bilinmeyen:
        raise ValueError(f"Şemada olmayan sütun(lar): {', '.join(sorted(bilinmeyen))}")
    if not alanlar:
        return 0

    atamalar = ", ".join(f'"{s}" = ?' for s in alanlar)
    degerler = []
    for sutun in alanlar:
        deger = alanlar[sutun]
        if deger is None or (isinstance(deger, float) and pd.isna(deger)):
            degerler.append(None)
        elif sutun in pc.SAYISAL_SUTUNLAR:
            degerler.append(float(deger))
        else:
            degerler.append(str(deger))

    with baglan(dosya) as baglanti:
        imlec = baglanti.execute(
            f"UPDATE islemler SET {atamalar} WHERE id = ?", degerler + [kayit_id])
        return imlec.rowcount


def islem_sil(kayit_id, dosya=VERITABANI):
    """İşlemi siler. Döner: silinen satır sayısı."""
    with baglan(dosya) as baglanti:
        return baglanti.execute("DELETE FROM islemler WHERE id = ?", (kayit_id,)).rowcount


def defter_yaz(cerceve, defter, dosya=VERITABANI):
    """Bir defterin tamamını verilen tabloyla değiştirir.

    Tek işlem içinde silip yazar: yarıda kesilirse defter eski hâlinde
    kalır, yarısı yeni yarısı eski bir tabloya dönüşmez.
    """
    _defter_dogrula(defter)
    duzgun = pc.sema_uygula(cerceve)
    sutunlar = ", ".join(f'"{s}"' for s in pc.ZORUNLU_SUTUNLAR)
    yer_tutucu = ", ".join("?" for _ in pc.ZORUNLU_SUTUNLAR)

    with baglan(dosya) as baglanti:
        baglanti.execute("DELETE FROM islemler WHERE defter = ?", (defter,))
        baglanti.executemany(
            f"INSERT INTO islemler (defter, {sutunlar}) VALUES (?, {yer_tutucu})",
            [[defter] + _kayit_degerleri(satir) for _, satir in duzgun.iterrows()],
        )
    return len(duzgun)


# ===========================================================================
# EXCEL İLE GİDİŞ-GELİŞ
# ===========================================================================

def excelden_aktar(excel_dosya, defter, dosya=VERITABANI):
    """Excel defterini veritabanına aktarır. Döner: aktarılan satır sayısı.

    Excel dosyasına dokunulmaz — geçişten sonra yedek olarak kalır.
    """
    _defter_dogrula(defter)
    if not os.path.exists(excel_dosya):
        return 0
    return defter_yaz(pc.defter_oku(excel_dosya), defter, dosya)


def excele_aktar(defter, hedef, dosya=VERITABANI):
    """Defteri Excel'e yazar. Döner: yazılan satır sayısı.

    Geri dönüş yolu budur: veritabanından memnun kalmazsan defterini
    eski biçiminde geri alırsın.
    """
    cerceve = defter_oku(defter, dosya).drop(columns=["id"], errors="ignore")
    pc.atomik_yaz(cerceve, hedef)
    return len(cerceve)


# ===========================================================================
# OTOMATİK GEÇİŞ
# ===========================================================================

def gecis_gerekli_mi(dosya=VERITABANI, excel_yollari=None):
    """Excel defteri var ama veritabanı boşsa True.

    Veritabanında kayıt varsa geçiş yapılmaz: ikinci kez aktarmak, geçişten
    sonra girilen işlemleri silip eski Excel'in üstüne yazmak olurdu.
    """
    excel_yollari = excel_yollari or ESKI_EXCEL
    if any(v > 0 for v in sayim(dosya).values()):
        return False
    return any(os.path.exists(yol) for yol in excel_yollari.values())


def otomatik_gecis(dosya=VERITABANI, excel_yollari=None):
    """Excel defterlerini bir kez veritabanına aktarır.

    Döner: {"hisse": n, "kripto": n, "yedek": [...]}. Geçiş gerekmiyorsa
    sayılar sıfırdır.

    Excel dosyaları silinmez; ayrıca zaman damgalı bir kopyası alınır.
    Geçişin bozuk çıkması ihtimaline karşı elde iki kopya kalır.
    """
    excel_yollari = excel_yollari or ESKI_EXCEL
    sonuc = {defter: 0 for defter in DEFTERLER}
    sonuc["yedek"] = []

    if not gecis_gerekli_mi(dosya, excel_yollari):
        return sonuc

    damga = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    for defter, excel_yolu in excel_yollari.items():
        if not os.path.exists(excel_yolu):
            continue
        sonuc[defter] = excelden_aktar(excel_yolu, defter, dosya)
        kok, uzanti = os.path.splitext(excel_yolu)
        yedek = f"{kok}.gecis_{damga}{uzanti}"
        with contextlib.suppress(OSError):
            shutil.copy2(excel_yolu, yedek)
            sonuc["yedek"].append(yedek)
        kayitci.info("%s → veritabanı: %d kayıt", excel_yolu, sonuc[defter])

    return sonuc
