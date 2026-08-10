"""ajan için testler — ağ erişimi ve API çağrısı olmadan.

İki şeyi koruyorlar: araçların modele verdiği verinin doğru şekillenmesi,
ve araç yüzeyinin salt-okunur kalması. İkincisi bir tasarım sınırı, kozmetik
bir tercih değil: yazma yetkisi olan bir araç eklendiği gün, dil modeli
finansal kaydı değiştirebilir hale gelir.
"""

import pandas as pd
import pytest

import ajan
import portfoy_core as pc


@pytest.fixture
def calisma_dizini(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def satir(**alanlar):
    varsayilan = {
        "Tarih": "2026-01-01 10:00", "Hisse": "AAPL", "Kazan": "", "Tip": "AL 🟢",
        "Fiyat": 100.0, "Adet": 2.0, "Toplam": 200.0, "Para_Birimi": "USD",
        "Islem_Kuru": 34.0, "Islem_USDTRY": 34.0, "Borsa_PB": "USD", "Borsa": "NASDAQ",
    }
    varsayilan.update(alanlar)
    return varsayilan


def defter_yaz(dosya, *satirlar):
    pc.sema_uygula(pd.DataFrame(list(satirlar))).to_excel(dosya, index=False)


# --- Araç yüzeyi ------------------------------------------------------------

def test_araclar_salt_okunur():
    """Yazma/silme çağrıştıran bir araç adı eklenirse test düşer."""
    araclar = ajan._araclari_kur()
    adlar = {a.name for a in araclar}
    assert adlar == {"portfoy_ozeti", "varlik_detayi", "islem_gecmisi", "kurlar"}
    yasakli = ("kaydet", "sil", "yaz", "guncelle", "ekle", "islem_gir")
    assert not [ad for ad in adlar if any(k in ad for k in yasakli)]


def test_her_aracin_aciklamasi_var():
    """Docstring modelin okuduğu sözleşmedir; boş olamaz."""
    for arac in ajan._araclari_kur():
        assert arac.description and len(arac.description) > 40


# --- portfoy_ozeti ----------------------------------------------------------

def test_bos_portfoyde_deger_hesabi_denenmez(calisma_dizini, monkeypatch):
    """Defter yokken piyasaya gidip boşuna istek atmamalı."""
    def patlayici(*a, **k):
        raise AssertionError("boş portföyde piyasa çağrılmamalı")

    monkeypatch.setattr(ajan.piyasa, "portfoy_degerle", patlayici)
    assert "boş" in ajan.portfoy_verisi()["durum"].lower()


def test_portfoy_ozeti_degerlemeyi_dondurur(calisma_dizini, monkeypatch):
    defter_yaz(ajan.EXCEL_HISSE, satir())
    monkeypatch.setattr(ajan.piyasa, "portfoy_degerle",
                        lambda *a: {"maliyet_usd": 200.0, "deger_usd": 260.0,
                                    "fiyatsiz": [], "kur_eksik": False})
    veri = ajan.portfoy_verisi()
    assert veri["deger_usd"] == pytest.approx(260.0)


def test_fiyatsiz_varliklar_modele_gorunur(calisma_dizini, monkeypatch):
    """Eksik fiyat bilgisi araç çıktısından silinmemeli."""
    defter_yaz(ajan.EXCEL_HISSE, satir())
    monkeypatch.setattr(ajan.piyasa, "portfoy_degerle",
                        lambda *a: {"deger_usd": 0.0, "fiyatsiz": ["THYAO"],
                                    "kur_eksik": True})
    veri = ajan.portfoy_verisi()
    assert veri["fiyatsiz"] == ["THYAO"]
    assert veri["kur_eksik"] is True


# --- varlik_detayi ----------------------------------------------------------

def test_hisse_detayi_yahoo_yolundan_gelir(calisma_dizini, monkeypatch):
    defter_yaz(ajan.EXCEL_HISSE, satir())
    monkeypatch.setattr(ajan.piyasa, "hisse_fiyatlari",
                        lambda s: {"AAPL": {"fiyat": 130.0, "degisim": 1.2, "rsi": 55.0}})
    monkeypatch.setattr(ajan.piyasa, "sembol_meta", lambda k: {"borsa_pb": "USD"})
    veri = ajan.varlik_verisi("aapl")
    assert veri["sembol"] == "AAPL"
    assert veri["fiyat"] == pytest.approx(130.0)
    assert veri["para_birimi"] == "USD"


def test_kripto_detayi_binance_yolundan_gelir(calisma_dizini, monkeypatch):
    defter_yaz(ajan.EXCEL_KRIPTO, satir(Hisse="BTC", Borsa="BINANCE"))
    monkeypatch.setattr(ajan.piyasa, "kripto_fiyatlari",
                        lambda s: {"BTC": {"fiyat": 65000.0, "degisim": -2.5}})
    monkeypatch.setattr(ajan.piyasa, "kripto_rsi", lambda s: 48.0)
    veri = ajan.varlik_verisi("btc")
    assert veri["para_birimi"] == "USDT"
    assert veri["rsi_14"] == pytest.approx(48.0)


def test_fiyat_yoksa_uydurulmaz(calisma_dizini, monkeypatch):
    monkeypatch.setattr(ajan.piyasa, "hisse_fiyatlari", lambda s: {})
    veri = ajan.varlik_verisi("YOKBOYLESEY")
    assert "hata" in veri
    assert "fiyat" not in veri


# --- islem_gecmisi ----------------------------------------------------------

def test_gecmis_en_yeniden_eskiye_siralanir(calisma_dizini):
    defter_yaz(
        ajan.EXCEL_HISSE,
        satir(Tarih="2026-01-01 10:00", Fiyat=100.0),
        satir(Tarih="2026-03-01 10:00", Fiyat=300.0),
        satir(Tarih="2026-02-01 10:00", Fiyat=200.0),
    )
    kayitlar = ajan.gecmis_verisi()["kayitlar"]
    assert [k["Fiyat"] for k in kayitlar] == [300.0, 200.0, 100.0]


def test_gecmis_sembol_ve_tip_ile_suzulur(calisma_dizini):
    defter_yaz(
        ajan.EXCEL_HISSE,
        satir(Hisse="AAPL"),
        satir(Hisse="MSFT", Tarih="2026-01-02 10:00"),
        satir(Hisse="AAPL", Tip="SAT 🔴", Tarih="2026-01-03 10:00"),
    )
    assert ajan.gecmis_verisi(sembol="AAPL")["kayit_sayisi"] == 2
    assert ajan.gecmis_verisi(tip="SAT")["kayit_sayisi"] == 1
    assert ajan.gecmis_verisi(sembol="AAPL", tip="AL")["kayit_sayisi"] == 1


def test_gecmis_iki_defteri_birlestirir(calisma_dizini):
    defter_yaz(ajan.EXCEL_HISSE, satir(Hisse="AAPL"))
    defter_yaz(ajan.EXCEL_KRIPTO, satir(Hisse="BTC"))
    assert ajan.gecmis_verisi()["kayit_sayisi"] == 2


def test_bos_defterde_gecmis_cokmez(calisma_dizini):
    assert ajan.gecmis_verisi() == {"kayit_sayisi": 0, "kayitlar": []}


# --- sor() hata yolları -----------------------------------------------------

def test_anthropic_yoksa_panel_cokmez(monkeypatch):
    """Paket kurulu değilse istisna değil, açıklayıcı mesaj dönmeli."""
    import builtins
    gercek_import = builtins.__import__

    def sahte_import(ad, *a, **k):
        if ad == "anthropic":
            raise ImportError("yok")
        return gercek_import(ad, *a, **k)

    monkeypatch.setattr(builtins, "__import__", sahte_import)
    sonuc = ajan.sor("merhaba")
    assert sonuc["hata"] and "pip install anthropic" in sonuc["hata"]
    assert sonuc["cevap"] == ""
