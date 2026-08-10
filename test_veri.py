"""veri (SQLite deposu) için testler.

Korudukları üç şey:

1. Deponun verdiği tablo, Excel dönemindekiyle aynı biçimde olmalı — aksi
   hâlde `portfoy_core`'un para hesapları sessizce bozulur.
2. Geçiş bir kez çalışmalı. İkinci kez aktarmak, geçişten sonra girilen
   işlemleri silip eski Excel'in üstüne yazmak demektir.
3. Toplu yazma ya tamamen olmalı ya hiç — yarıda kesilen bir yazma defteri
   yarısı yeni yarısı eski bırakmamalı.
"""

import os

import pandas as pd
import pytest

import portfoy_core as pc
import veri


@pytest.fixture
def db(tmp_path):
    return str(tmp_path / "test.db")


def kayit(**alanlar):
    varsayilan = {
        "Tarih": "2026-01-01 10:00", "Hisse": "AAPL", "Kazan": "", "Tip": "AL 🟢",
        "Fiyat": 100.0, "Adet": 2.0, "Toplam": 200.0, "Para_Birimi": "USD",
        "Islem_Kuru": 34.0, "Islem_USDTRY": 34.0, "Borsa_PB": "USD", "Borsa": "NASDAQ",
    }
    varsayilan.update(alanlar)
    return varsayilan


# --- Şema ve okuma ----------------------------------------------------------

def test_veritabani_yokken_bos_defter_doner(db):
    cerceve = veri.defter_oku("hisse", db)
    assert cerceve.empty
    assert list(cerceve.columns) == pc.ZORUNLU_SUTUNLAR


def test_okunan_tablo_excel_donemiyle_ayni_sutunlari_tasir(db):
    """portfoy_core'un beklediği şema korunmalı; id fazladan gelir."""
    veri.islem_ekle("hisse", kayit(), db)
    cerceve = veri.defter_oku("hisse", db)
    assert set(pc.ZORUNLU_SUTUNLAR) <= set(cerceve.columns)
    assert "id" in cerceve.columns


def test_sayisal_sutunlar_sayi_olarak_doner(db):
    veri.islem_ekle("hisse", kayit(Fiyat=123.45, Adet=3.0), db)
    satir = veri.defter_oku("hisse", db).iloc[0]
    assert satir["Fiyat"] == pytest.approx(123.45)
    assert satir["Adet"] == pytest.approx(3.0)


def test_iki_defter_birbirine_karismaz(db):
    veri.islem_ekle("hisse", kayit(Hisse="AAPL"), db)
    veri.islem_ekle("kripto", kayit(Hisse="BTC"), db)
    assert list(veri.defter_oku("hisse", db)["Hisse"]) == ["AAPL"]
    assert list(veri.defter_oku("kripto", db)["Hisse"]) == ["BTC"]


def test_gecersiz_defter_adi_reddedilir(db):
    with pytest.raises(ValueError):
        veri.defter_oku("tahvil", db)
    with pytest.raises(ValueError):
        veri.islem_ekle("tahvil", kayit(), db)


def test_sayim_defter_basina_verir(db):
    veri.islem_ekle("hisse", kayit(), db)
    veri.islem_ekle("hisse", kayit(), db)
    veri.islem_ekle("kripto", kayit(Hisse="BTC"), db)
    assert veri.sayim(db) == {"hisse": 2, "kripto": 1}


def test_sayim_veritabani_yokken_sifir(db):
    assert veri.sayim(db) == {"hisse": 0, "kripto": 0}


# --- Ekleme, güncelleme, silme ---------------------------------------------

def test_eklenen_kaydin_kimligi_doner(db):
    kimlik = veri.islem_ekle("hisse", kayit(), db)
    assert isinstance(kimlik, int) and kimlik > 0
    assert veri.kayit_getir(kimlik, db)["Hisse"] == "AAPL"


def test_eksik_alanlar_bos_gecer(db):
    """Excel'de olmayan sütun NaN oluyordu; burada None olmalı, sıfır değil."""
    kimlik = veri.islem_ekle("hisse", {"Hisse": "AAPL", "Tip": "AL 🟢"}, db)
    alinan = veri.kayit_getir(kimlik, db)
    assert alinan["Fiyat"] is None and alinan["Islem_USDTRY"] is None


def test_kayit_guncellenir(db):
    kimlik = veri.islem_ekle("hisse", kayit(Fiyat=100.0), db)
    assert veri.islem_guncelle(kimlik, {"Fiyat": 150.0}, db) == 1
    assert veri.kayit_getir(kimlik, db)["Fiyat"] == pytest.approx(150.0)


def test_olmayan_kaydi_guncellemek_sifir_doner(db):
    veri.islem_ekle("hisse", kayit(), db)
    assert veri.islem_guncelle(9999, {"Fiyat": 1.0}, db) == 0


def test_semada_olmayan_sutun_hata_verir(db):
    """Sessizce yok saymak, güncellenmediğini fark etmemek demektir."""
    kimlik = veri.islem_ekle("hisse", kayit(), db)
    with pytest.raises(ValueError, match="Şemada olmayan"):
        veri.islem_guncelle(kimlik, {"Fiyatt": 1.0}, db)


def test_bos_guncelleme_hicbir_sey_yapmaz(db):
    kimlik = veri.islem_ekle("hisse", kayit(), db)
    assert veri.islem_guncelle(kimlik, {}, db) == 0


def test_kayit_silinir(db):
    kimlik = veri.islem_ekle("hisse", kayit(), db)
    assert veri.islem_sil(kimlik, db) == 1
    assert veri.kayit_getir(kimlik, db) is None
    assert veri.defter_oku("hisse", db).empty


def test_olmayan_kaydi_silmek_cokmez(db):
    assert veri.islem_sil(9999, db) == 0


# --- Toplu yazma ------------------------------------------------------------

def test_defter_yaz_eskisini_degistirir(db):
    veri.islem_ekle("hisse", kayit(Hisse="ESKI"), db)
    yeni = pd.DataFrame([kayit(Hisse="YENI1"), kayit(Hisse="YENI2")])
    assert veri.defter_yaz(yeni, "hisse", db) == 2
    assert sorted(veri.defter_oku("hisse", db)["Hisse"]) == ["YENI1", "YENI2"]


def test_defter_yaz_diger_deftere_dokunmaz(db):
    veri.islem_ekle("kripto", kayit(Hisse="BTC"), db)
    veri.defter_yaz(pd.DataFrame([kayit(Hisse="AAPL")]), "hisse", db)
    assert list(veri.defter_oku("kripto", db)["Hisse"]) == ["BTC"]


def test_bos_cerceve_defteri_temizler(db):
    veri.islem_ekle("hisse", kayit(), db)
    assert veri.defter_yaz(pc.bos_defter(), "hisse", db) == 0
    assert veri.defter_oku("hisse", db).empty


# --- Excel ile gidiş-geliş --------------------------------------------------

def test_excelden_aktarim(db, tmp_path):
    excel = str(tmp_path / "defter.xlsx")
    pc.sema_uygula(pd.DataFrame([kayit(Hisse="AAPL"), kayit(Hisse="MSFT")])).to_excel(
        excel, index=False)
    assert veri.excelden_aktar(excel, "hisse", db) == 2
    assert sorted(veri.defter_oku("hisse", db)["Hisse"]) == ["AAPL", "MSFT"]


def test_olmayan_excel_sifir_doner(db, tmp_path):
    assert veri.excelden_aktar(str(tmp_path / "yok.xlsx"), "hisse", db) == 0


def test_excele_geri_aktarim(db, tmp_path):
    """Geri dönüş yolu çalışmalı; beğenilmezse eski biçime dönülebilmeli."""
    veri.islem_ekle("hisse", kayit(Hisse="AAPL"), db)
    hedef = str(tmp_path / "cikti.xlsx")
    assert veri.excele_aktar("hisse", hedef, db) == 1
    geri = pc.defter_oku(hedef)
    assert list(geri["Hisse"]) == ["AAPL"]
    assert "id" not in geri.columns


def test_gidis_donus_veriyi_korur(db, tmp_path):
    kaynak = pc.sema_uygula(pd.DataFrame([
        kayit(Hisse="AAPL", Fiyat=123.45, Adet=2.5),
        kayit(Hisse="THYAO", Para_Birimi="TRY", Fiyat=300.0, Islem_Kuru=1.0),
    ]))
    excel = str(tmp_path / "kaynak.xlsx")
    kaynak.to_excel(excel, index=False)

    veri.excelden_aktar(excel, "hisse", db)
    hedef = str(tmp_path / "hedef.xlsx")
    veri.excele_aktar("hisse", hedef, db)
    donen = pc.defter_oku(hedef)

    for sutun in pc.ZORUNLU_SUTUNLAR:
        beklenen = kaynak[sutun].reset_index(drop=True)
        alinan = donen[sutun].reset_index(drop=True)
        if sutun in pc.SAYISAL_SUTUNLAR:
            assert list(alinan) == pytest.approx(list(beklenen))
        else:
            assert list(alinan) == list(beklenen)


# --- Otomatik geçiş ---------------------------------------------------------

@pytest.fixture
def excel_defterleri(tmp_path):
    yollar = {"hisse": str(tmp_path / "h.xlsx"), "kripto": str(tmp_path / "k.xlsx")}
    pc.sema_uygula(pd.DataFrame([kayit(Hisse="AAPL")])).to_excel(yollar["hisse"], index=False)
    pc.sema_uygula(pd.DataFrame([kayit(Hisse="BTC"), kayit(Hisse="ETH")])).to_excel(
        yollar["kripto"], index=False)
    return yollar


def test_gecis_excel_varken_gerekli(db, excel_defterleri):
    assert veri.gecis_gerekli_mi(db, excel_defterleri) is True


def test_gecis_excel_yokken_gereksiz(db, tmp_path):
    yollar = {"hisse": str(tmp_path / "yok1.xlsx"), "kripto": str(tmp_path / "yok2.xlsx")}
    assert veri.gecis_gerekli_mi(db, yollar) is False


def test_gecis_iki_defteri_de_aktarir(db, excel_defterleri):
    sonuc = veri.otomatik_gecis(db, excel_defterleri)
    assert sonuc["hisse"] == 1 and sonuc["kripto"] == 2
    assert list(veri.defter_oku("hisse", db)["Hisse"]) == ["AAPL"]
    assert sorted(veri.defter_oku("kripto", db)["Hisse"]) == ["BTC", "ETH"]


def test_gecis_excel_dosyalarini_silmez(db, excel_defterleri):
    veri.otomatik_gecis(db, excel_defterleri)
    for yol in excel_defterleri.values():
        assert os.path.exists(yol)


def test_gecis_zaman_damgali_yedek_birakir(db, excel_defterleri):
    sonuc = veri.otomatik_gecis(db, excel_defterleri)
    assert len(sonuc["yedek"]) == 2
    for yedek in sonuc["yedek"]:
        assert os.path.exists(yedek) and ".gecis_" in yedek


def test_gecis_ikinci_kez_calismaz(db, excel_defterleri):
    """En kritik koruma: ikinci geçiş, sonradan girilen işlemleri silerdi."""
    veri.otomatik_gecis(db, excel_defterleri)
    veri.islem_ekle("hisse", kayit(Hisse="GECISTEN_SONRA"), db)

    assert veri.gecis_gerekli_mi(db, excel_defterleri) is False
    sonuc = veri.otomatik_gecis(db, excel_defterleri)
    assert sonuc["hisse"] == 0 and sonuc["kripto"] == 0
    assert "GECISTEN_SONRA" in list(veri.defter_oku("hisse", db)["Hisse"])


def test_gecis_sonrasi_para_hesabi_ayni_calisir(db, excel_defterleri):
    """Depo değişti, muhasebe değişmedi: portfoy_core aynı sonucu vermeli."""
    veri.otomatik_gecis(db, excel_defterleri)
    defter = veri.defter_oku("hisse", db)
    ozet = pc.pozisyon_ozeti(defter, {"USD": 34.0, "TRY": 1.0})

    assert ozet["hesaplanamayan_satir"] == 0
    assert "AAPL" in ozet["pozisyonlar"]
    assert ozet["pozisyonlar"]["AAPL"]["adet"] == pytest.approx(2.0)
    # 2 adet × 100 USD; tarihsel kur kayıtlı olduğu için tahmin yok.
    assert ozet["pozisyonlar"]["AAPL"]["maliyet_usd"] == pytest.approx(200.0)
    assert ozet["tahmini_kur_satir"] == 0


# --- Eşzamanlılık -----------------------------------------------------------

def test_iki_baglanti_ayni_anda_yazabilir(db):
    """Panel açıkken görev zamanlayıcının da yazabilmesi buna bağlı."""
    veri.islem_ekle("hisse", kayit(Hisse="ILK"), db)
    with veri.baglan(db) as birinci:
        adet = birinci.execute("SELECT COUNT(*) FROM islemler").fetchone()[0]
        assert adet == 1
        # Birinci bağlantı açıkken ikincisi yazabilmeli.
        veri.islem_ekle("kripto", kayit(Hisse="BTC"), db)
    assert veri.sayim(db) == {"hisse": 1, "kripto": 1}
