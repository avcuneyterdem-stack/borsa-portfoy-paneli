"""otomatik_takip için testler — ağ erişimi olmadan.

Botun en önemli davranışı, eksik veriyle rakam uydurmamasıdır: eski sürüm
kur çekilemediğinde sabit 34.0 varsayıp yanlış bir geçmiş yazıyordu.
"""

import logging
import os

import pandas as pd
import pytest

import otomatik_takip as ot
import portfoy_core as pc


@pytest.fixture
def calisma_dizini(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def defter_yaz(dosya, **alanlar):
    satir = {
        "Tarih": "2026-01-01 10:00", "Hisse": "AAPL", "Kazan": "", "Tip": "AL 🟢",
        "Fiyat": 100.0, "Adet": 2.0, "Toplam": 200.0, "Para_Birimi": "USD",
        "Islem_Kuru": 34.0, "Islem_USDTRY": 34.0, "Borsa_PB": "USD", "Borsa": "NASDAQ",
    }
    satir.update(alanlar)
    pc.sema_uygula(pd.DataFrame([satir])).to_excel(dosya, index=False)


def degerleme(**degisiklikler):
    varsayilan = {
        "kurlar": {"TRY": 1.0, "USD": 40.0},
        "maliyet_usd": 200.0, "deger_usd": 260.0,
        "gerceklesen_kz_usd": 0.0, "gelir_usd": 0.0,
        "fiyatsiz": [], "kur_eksik": False, "uyarilar": [],
    }
    varsayilan.update(degisiklikler)
    return varsayilan


def test_gun_sonu_kaydi_yazilir(calisma_dizini, monkeypatch):
    defter_yaz(ot.EXCEL_HISSE)
    monkeypatch.setattr(ot.piyasa, "portfoy_degerle", lambda *a: degerleme())

    assert ot.gun_sonu_kaydet() == 0

    gecmis = pd.read_excel(ot.EXCEL_GECMIS)
    assert len(gecmis) == 1
    assert gecmis.loc[0, "Toplam_Deger_USD"] == pytest.approx(260.0)
    assert gecmis.loc[0, "Acik_KZ_USD"] == pytest.approx(60.0)
    assert gecmis.loc[0, "USDTRY"] == pytest.approx(40.0)


def test_kur_yoksa_hicbir_sey_kaydedilmez(calisma_dizini, monkeypatch):
    """Eski sürüm burada sabit 34.0 varsayıp yanlış geçmiş yazıyordu."""
    defter_yaz(ot.EXCEL_HISSE)
    monkeypatch.setattr(ot.piyasa, "portfoy_degerle", lambda *a: degerleme(kur_eksik=True))

    assert ot.gun_sonu_kaydet() == 1
    assert not (calisma_dizini / ot.EXCEL_GECMIS).exists()


def test_ayni_gun_tekrar_calisirsa_satir_cogalmaz(calisma_dizini, monkeypatch):
    defter_yaz(ot.EXCEL_HISSE)
    monkeypatch.setattr(ot.piyasa, "portfoy_degerle", lambda *a: degerleme())
    ot.gun_sonu_kaydet()

    monkeypatch.setattr(ot.piyasa, "portfoy_degerle", lambda *a: degerleme(deger_usd=300.0))
    ot.gun_sonu_kaydet()

    gecmis = pd.read_excel(ot.EXCEL_GECMIS)
    assert len(gecmis) == 1
    assert gecmis.loc[0, "Toplam_Deger_USD"] == pytest.approx(300.0)


def test_fiyatsiz_varliklar_nota_yazilir(calisma_dizini, monkeypatch):
    defter_yaz(ot.EXCEL_HISSE)
    monkeypatch.setattr(
        ot.piyasa, "portfoy_degerle",
        lambda *a: degerleme(fiyatsiz=["THYAO"], uyarilar=["1 eşleşmeyen satış"]),
    )
    ot.gun_sonu_kaydet()

    gecmis = pd.read_excel(ot.EXCEL_GECMIS)
    assert gecmis.loc[0, "Fiyatsiz_Varlik"] == 1
    assert "THYAO" in gecmis.loc[0, "Not"]
    assert "eşleşmeyen satış" in gecmis.loc[0, "Not"]


def test_bozuk_defter_gecmisi_bozmaz(calisma_dizini, monkeypatch):
    """Defter okunamıyorsa kayıt yapılmaz; mevcut geçmiş korunur."""
    defter_yaz(ot.EXCEL_HISSE)
    monkeypatch.setattr(ot.piyasa, "portfoy_degerle", lambda *a: degerleme())
    ot.gun_sonu_kaydet()
    onceki = (calisma_dizini / ot.EXCEL_GECMIS).read_bytes()

    (calisma_dizini / ot.EXCEL_HISSE).write_text("bu bir excel dosyası değil")
    assert ot.gun_sonu_kaydet() == 1
    assert (calisma_dizini / ot.EXCEL_GECMIS).read_bytes() == onceki


def test_bos_defterde_kayit_yapilmaz(calisma_dizini):
    assert ot.gun_sonu_kaydet() == 2
    assert not (calisma_dizini / ot.EXCEL_GECMIS).exists()


# --- Dosya günlüğü (Görev Zamanlayıcı için) ---------------------------------

def test_log_dosyasi_olusturulur_ve_yazilir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    kok = logging.getLogger()
    onceki = list(kok.handlers)
    try:
        ot.dosya_gunlugu_ekle("takip.log")
        logging.getLogger("otomatik_takip").error("deneme satırı")
        for tutamak in kok.handlers:
            tutamak.flush()
        icerik = (tmp_path / "takip.log").read_text(encoding="utf-8")
        assert "deneme satırı" in icerik
    finally:
        for tutamak in list(kok.handlers):
            if tutamak not in onceki:
                tutamak.close()
                kok.removeHandler(tutamak)


def test_ayni_log_iki_kez_eklenmez(tmp_path, monkeypatch):
    """İki tutamak, her satırın dosyaya iki kez yazılması demektir."""
    monkeypatch.chdir(tmp_path)
    kok = logging.getLogger()
    onceki = list(kok.handlers)
    try:
        ilk = ot.dosya_gunlugu_ekle("takip.log")
        ikinci = ot.dosya_gunlugu_ekle("takip.log")
        assert ilk is ikinci
        eklenen = [h for h in kok.handlers if h not in onceki]
        assert len(eklenen) == 1
    finally:
        for tutamak in list(kok.handlers):
            if tutamak not in onceki:
                tutamak.close()
                kok.removeHandler(tutamak)


# --- Görev betiğinin kodlaması ---------------------------------------------

def test_ps1_dosyasi_bom_ile_kaydedilmis():
    """Windows PowerShell 5.1, BOM yoksa .ps1'i ANSI sanır ve Türkçe
    harfleri bozar ("Başarılı" → "BaÅŸarÄ±lÄ±"). Bir düzenleme sırasında
    BOM kaybolursa bu test yakalar."""
    yol = os.path.join(os.path.dirname(__file__), "kur_gunluk_gorev.ps1")
    if not os.path.exists(yol):
        pytest.skip("Betik bu kurulumda yok.")
    with open(yol, "rb") as akis:
        assert akis.read(3) == b"\xef\xbb\xbf", "kur_gunluk_gorev.ps1 UTF-8 BOM taşımıyor"


def test_ps1_turkce_karakterleri_okunabilir():
    """BOM'lu UTF-8 olarak açıldığında metin bozulmamış olmalı."""
    yol = os.path.join(os.path.dirname(__file__), "kur_gunluk_gorev.ps1")
    if not os.path.exists(yol):
        pytest.skip("Betik bu kurulumda yok.")
    with open(yol, encoding="utf-8-sig") as akis:
        icerik = akis.read()
    assert "Başarılı" in icerik and "Ön kontroller" in icerik
    assert "Ã" not in icerik, "metin çift kodlanmış görünüyor"
