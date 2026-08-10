"""portfoy_core için birim testleri (54 Test)."""

import math
import os
import time

import pandas as pd
import pytest

import portfoy_core as pc


BUGUN = {"TRY": 1.0, "USD": 40.0, "EUR": 44.0, "GBP": 50.0}
ALIM_GUNU_USDTRY = 34.0


def satir(**alanlar):
    varsayilan = {
        "Tarih": "2026-01-01 10:00", "Hisse": "AAPL", "Kazan": "", "Tip": "AL 🟢",
        "Fiyat": 100.0, "Adet": 1.0, "Toplam": 100.0, "Para_Birimi": "USD",
        "Islem_Kuru": ALIM_GUNU_USDTRY, "Islem_USDTRY": ALIM_GUNU_USDTRY,
        "Borsa_PB": "USD", "Borsa": "NASDAQ",
    }
    varsayilan.update(alanlar)
    return varsayilan


def defter(*satirlar):
    return pc.sema_uygula(pd.DataFrame(list(satirlar)))


@pytest.mark.parametrize("metin, beklenen", [
    ("AL 🟢", pc.AL),
    ("SAT 🔴", pc.SAT),
    ("TEMETTÜ 💰", pc.GELIR),
    ("STAKING 💰", pc.GELIR),
    ("satış", pc.SAT),
    ("", None),
])
def test_islem_tipi_ayristirma(metin, beklenen):
    assert pc.islem_tipi(metin) is beklenen


def test_staking_al_olarak_okunmaz():
    assert pc.islem_tipi("STAKING 💰") is pc.GELIR


def test_dolar_islemi_kur_degisince_sabit_kalir():
    tutar, tahmini = pc.usd_maliyet(100.0, 1.0, "USD", ALIM_GUNU_USDTRY, ALIM_GUNU_USDTRY, BUGUN)
    assert tutar == pytest.approx(100.0)
    assert tahmini is False

    tutar_2, _ = pc.usd_maliyet(100.0, 1.0, "USD", ALIM_GUNU_USDTRY, ALIM_GUNU_USDTRY, {"USD": 90.0, "TRY": 1.0})
    assert tutar_2 == pytest.approx(100.0)


def test_lira_islemi_alim_gunu_kuruna_sabitlenir():
    tutar, tahmini = pc.usd_maliyet(3400.0, 1.0, "TRY", 1.0, ALIM_GUNU_USDTRY, BUGUN)
    assert tutar == pytest.approx(100.0)
    assert tahmini is False


def test_euro_islemi_capraz_kurla_cevrilir():
    tutar, _ = pc.usd_maliyet(44.0, 1.0, "EUR", 37.0, 34.0, BUGUN)
    assert tutar == pytest.approx(44.0 * 37.0 / 34.0)


def test_tarihsel_kuru_olmayan_eski_dolar_kaydi_kesin_kalir():
    tutar, tahmini = pc.usd_maliyet(100.0, 2.0, "USD", None, None, BUGUN)
    assert tutar == pytest.approx(200.0)
    assert tahmini is False


def test_tarihsel_kuru_olmayan_eski_lira_kaydi_tahmini_isaretlenir():
    tutar, tahmini = pc.usd_maliyet(4000.0, 1.0, "TRY", None, None, BUGUN)
    assert tutar == pytest.approx(100.0)
    assert tahmini is True


def test_kur_yoksa_hesap_yapilmaz():
    tutar, _ = pc.usd_maliyet(4000.0, 1.0, "TRY", None, None, {"TRY": 1.0})
    assert tutar is None


def test_lira_fiyat_dolara_cevrilir():
    assert pc.fiyati_usd_yap(400.0, "TRY", BUGUN) == pytest.approx(10.0)


def test_euro_fiyat_dogru_cevrilir():
    assert pc.fiyati_usd_yap(100.0, "EUR", BUGUN) == pytest.approx(100.0 * 44.0 / 40.0)


def test_londra_pens_fiyati_yuz_kat_sismez():
    assert pc.fiyati_usd_yap(500.0, "GBp", BUGUN) == pytest.approx(5.0 * 50.0 / 40.0)


def test_bilinmeyen_para_birimi_dolar_sayilmaz():
    assert pc.fiyati_usd_yap(100.0, "JPY", BUGUN) is None


def test_ortalama_maliyet_ve_gerceklesen_kar():
    d = defter(
        satir(Fiyat=100.0, Adet=1.0, Tarih="2026-01-01 10:00"),
        satir(Fiyat=200.0, Adet=1.0, Tarih="2026-01-02 10:00"),
        satir(Fiyat=300.0, Adet=1.0, Tip="SAT 🔴", Tarih="2026-01-03 10:00"),
    )
    ozet = pc.pozisyon_ozeti(d, BUGUN)
    acik = pc.acik_pozisyonlar(ozet)
    assert acik["AAPL"]["adet"] == pytest.approx(1.0)
    assert acik["AAPL"]["maliyet_usd"] == pytest.approx(150.0)
    assert ozet["gerceklesen_kz_usd"] == pytest.approx(150.0)
    assert ozet["eslesmeyen_satis"] == 0


def test_kayitlar_tarihe_gore_islenir():
    ters = defter(
        satir(Fiyat=300.0, Adet=1.0, Tip="SAT 🔴", Tarih="2026-01-03 10:00"),
        satir(Fiyat=200.0, Adet=1.0, Tarih="2026-01-02 10:00"),
        satir(Fiyat=100.0, Adet=1.0, Tarih="2026-01-01 10:00"),
    )
    ozet = pc.pozisyon_ozeti(ters, BUGUN)
    assert ozet["gerceklesen_kz_usd"] == pytest.approx(150.0)


def test_fazla_satis_sessizce_yutulmaz():
    d = defter(
        satir(Fiyat=100.0, Adet=1.0, Tarih="2026-01-01 10:00"),
        satir(Fiyat=100.0, Adet=5.0, Tip="SAT 🔴", Tarih="2026-01-02 10:00"),
    )
    ozet = pc.pozisyon_ozeti(d, BUGUN)
    assert ozet["eslesmeyen_satis"] == 1
    assert pc.acik_pozisyonlar(ozet) == {}
    assert ozet["gerceklesen_kz_usd"] == pytest.approx(0.0)


def test_pozisyonu_olmayan_satis_sayaca_yazilir():
    d = defter(satir(Tip="SAT 🔴", Adet=2.0))
    ozet = pc.pozisyon_ozeti(d, BUGUN)
    assert ozet["eslesmeyen_satis"] == 1
    assert ozet["gerceklesen_kz_usd"] == pytest.approx(0.0)


def test_temettu_pozisyona_degil_gelire_yazilir():
    d = defter(
        satir(Fiyat=100.0, Adet=1.0),
        satir(Fiyat=5.0, Adet=1.0, Tip="TEMETTÜ 💰", Tarih="2026-02-01 10:00"),
    )
    ozet = pc.pozisyon_ozeti(d, BUGUN)
    assert ozet["gelir_usd"] == pytest.approx(5.0)
    assert pc.acik_pozisyonlar(ozet)["AAPL"]["adet"] == pytest.approx(1.0)


def test_tahmini_kur_satirlari_raporlanir():
    d = defter(satir(Para_Birimi="TRY", Fiyat=4000.0, Islem_Kuru=None, Islem_USDTRY=None))
    ozet = pc.pozisyon_ozeti(d, BUGUN)
    assert ozet["tahmini_kur_satir"] == 1


def test_bos_defter_cokmez():
    ozet = pc.pozisyon_ozeti(pc.bos_defter(), BUGUN)
    assert ozet["pozisyonlar"] == {}
    assert ozet["gerceklesen_kz_usd"] == 0.0


def test_satilabilir_adet():
    d = defter(
        satir(Adet=3.0),
        satir(Adet=1.0, Tip="SAT 🔴", Tarih="2026-01-02 10:00"),
        satir(Adet=9.0, Tip="TEMETTÜ 💰", Tarih="2026-01-03 10:00"),
    )
    assert pc.satilabilir_adet(d, "AAPL") == pytest.approx(2.0)
    assert pc.satilabilir_adet(d, "MSFT") == pytest.approx(0.0)


def test_satilabilir_adet_bos_tip_ile_cokmez():
    d = defter(satir(Adet=3.0), satir(Adet=1.0, Tip=""))
    assert pc.satilabilir_adet(d, "AAPL") == pytest.approx(3.0)


def test_sema_eksik_sutunlari_tamamlar():
    ham = pd.DataFrame([{"Tarih": "2026-01-01", "Hisse": "aapl", "Tip": "AL", "Fiyat": 10, "Adet": 2}])
    d = pc.sema_uygula(ham)
    assert set(pc.ZORUNLU_SUTUNLAR).issubset(d.columns)
    assert d.loc[0, "Hisse"] == "AAPL"
    assert d.loc[0, "Para_Birimi"] == "USD"
    assert d.loc[0, "Toplam"] == pytest.approx(20.0)


def test_sema_kullanicinin_ekstra_sutununu_korur():
    ham = pd.DataFrame([{"Hisse": "AAPL", "Notlarim": "uzun vade"}])
    d = pc.sema_uygula(ham)
    assert "Notlarim" in d.columns
    assert d.loc[0, "Notlarim"] == "uzun vade"


def test_tarihsiz_satirlar_raporlanir():
    d = defter(satir(Tarih=""), satir(Tarih="2026-01-02 10:00"))
    _, tarihsiz = pc.tarihe_gore_sirala(d)
    assert tarihsiz == 1


def test_temettu_verimi_fiyattan_hesaplanir():
    oran, kaynak = pc.temettu_verimi(yillik_temettu=2.0, fiyat=100.0)
    assert oran == pytest.approx(0.02)
    assert kaynak == "hesaplandi"


def test_ham_yield_olcegi_tahmin_edilmez():
    oran, kaynak = pc.temettu_verimi(yillik_temettu=None, fiyat=None, ham_yield=0.8)
    assert oran is None
    assert kaynak == "belirsiz"


def test_temettu_yoksa_kaynak_yok():
    assert pc.temettu_verimi(None, None, None) == (None, "yok")


@pytest.mark.parametrize("giris, beklenen", [
    ("thyao", "THYAO.IS"),
    ("THYAO.IS", "THYAO.IS"),
    ("AAPL", "AAPL"),
    ("BRK-B", "BRK-B"),
])
def test_sembol_normalize(giris, beklenen):
    assert pc.sembol_normalize(giris) == beklenen


@pytest.mark.parametrize("sembol, beklenen", [
    ("THYAO.IS", "TRY"),
    ("VOD.L", "GBp"),
    ("BMW.DE", "EUR"),
    ("AAPL", "USD"),
])
def test_varsayilan_borsa_pb(sembol, beklenen):
    assert pc.varsayilan_borsa_pb(sembol) == beklenen


def test_borsa_pb_canli_veriyi_tercih_eder():
    assert pc.varsayilan_borsa_pb("AAPL", canli_pb="EUR") == "EUR"


def test_tv_sembol_nyse_hissesini_nasdaq_yapmaz():
    assert pc.tv_sembol("JPM", borsa="NYSE") == "NYSE:JPM"
    assert pc.tv_sembol("KO", borsa="") == "KO"
    assert pc.tv_sembol("THYAO.IS") == "BIST:THYAO"
    assert pc.tv_sembol("BTC", kripto=True) == "BINANCE:BTCUSDT"


def test_tv_sembol_script_kacisini_temizler():
    kirli = '"});alert(1)//'
    assert pc.tv_sembol(kirli) == "ALERT1"


def test_wilder_rsi_surekli_yukselen_seride_yuze_yaklasir():
    seri = pd.Series(range(1, 60), dtype="float64")
    assert pc.wilder_rsi(seri).iloc[-1] == pytest.approx(100.0)


def test_wilder_rsi_sabit_seride_tanimsiz():
    seri = pd.Series([10.0] * 40)
    assert math.isnan(pc.wilder_rsi(seri).iloc[-1])


def test_rsi_durum_sifiri_veri_yok_saymaz():
    assert pc.rsi_durum(0.0) == "Aşırı satım"
    assert pc.rsi_durum(None) == "Veri yok"
    assert pc.rsi_durum(float("nan")) == "Veri yok"
    assert pc.rsi_durum(50.0) == "Nötr"


def test_kazan_sinifi():
    assert pc.kazan_sinifi(piyasa_degeri=3e12) == pc.A_KAZANI
    assert pc.kazan_sinifi(piyasa_degeri=12e9, beta=0.7) == pc.A_KAZANI
    assert pc.kazan_sinifi(piyasa_degeri=5e9) == pc.B_KAZANI
    assert pc.kazan_sinifi(piyasa_degeri=5e8) == pc.C_KAZANI
    assert pc.kazan_sinifi(kripto_mu=True, sembol="BTC") == pc.A_KAZANI
    assert pc.kazan_sinifi(kripto_mu=True, sembol="DOGE") == pc.C_KAZANI
    assert pc.kazan_sinifi(piyasa_degeri=None) == ""


def test_atomik_yaz_ve_geri_oku(tmp_path):
    hedef = tmp_path / "defter.xlsx"
    pc.atomik_yaz(defter(satir(), satir(Hisse="MSFT")), str(hedef))
    assert pc.sema_uygula(pd.read_excel(hedef)).shape[0] == 2
    assert not (tmp_path / "defter.tmp.xlsx").exists()


def test_yedekler_birikir_ve_budanir(tmp_path):
    hedef = str(tmp_path / "defter.xlsx")
    for sayi in range(1, 6):
        pc.atomik_yaz(defter(*[satir()] * sayi), hedef, saklanacak_yedek=2)
    assert len(list(tmp_path.glob("defter.xlsx.*.bak"))) == 2
    assert len(pd.read_excel(hedef)) == 5


def test_yazma_basarisizsa_hedef_dosya_bozulmaz(tmp_path):
    hedef = str(tmp_path / "defter.xlsx")
    pc.atomik_yaz(defter(satir()), hedef)
    onceki = hedef and open(hedef, "rb").read()

    def bozuk_yazici(cerceve, yol):
        raise OSError("disk dolu")

    with pytest.raises(OSError):
        pc.atomik_yaz(defter(satir(), satir()), hedef, yazici=bozuk_yazici)

    assert open(hedef, "rb").read() == onceki
    assert not (tmp_path / "defter.tmp.xlsx").exists()


def test_eksik_yazilan_dosya_devreye_alinmaz(tmp_path):
    hedef = str(tmp_path / "defter.xlsx")
    pc.atomik_yaz(defter(satir()), hedef)

    def eksik_yazici(cerceve, yol):
        cerceve.head(0).to_excel(yol, index=False)

    with pytest.raises(ValueError, match="Doğrulama başarısız"):
        pc.atomik_yaz(defter(satir(), satir()), hedef, yazici=eksik_yazici)
    assert len(pd.read_excel(hedef)) == 1


def test_kilit_ikinci_yaziciyi_bekletir(tmp_path):
    hedef = str(tmp_path / "defter.xlsx")
    with pc.dosya_kilidi(hedef):
        with pytest.raises(TimeoutError):
            with pc.dosya_kilidi(hedef, bekleme=0.2):
                pass
    with pc.dosya_kilidi(hedef, bekleme=0.2):
        pass
    assert not os.path.exists(f"{hedef}.lock")


def test_bayat_kilit_temizlenir(tmp_path):
    hedef = str(tmp_path / "defter.xlsx")
    kilit = f"{hedef}.lock"
    open(kilit, "w").close()
    os.utime(kilit, (time.time() - 120, time.time() - 120))
    with pc.dosya_kilidi(hedef, bekleme=0.5, bayatlama=30):
        pass
    assert not os.path.exists(kilit)


def test_sil_sutunu_diske_yazilmaz(tmp_path):
    hedef = str(tmp_path / "defter.xlsx")
    veri = defter(satir())
    veri.insert(0, "Sil", False)
    pc.atomik_yaz(veri, hedef)
    assert "Sil" not in pd.read_excel(hedef).columns