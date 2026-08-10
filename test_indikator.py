"""indikator için testler — ağ erişimi olmadan.

İki şeyi koruyorlar: gösterge matematiğinin doğruluğu (elle hesaplanabilir
girdilerle), ve veri yetersizken uydurma değer üretilmemesi. İkincisi bir
tasarım sınırı: 150 barlık veriyle "200 günlük ortalama" göstermek, kullanıcı
fark etmeden yanlış sinyal üretir.
"""

import math

import pandas as pd
import pytest

import indikator as ind


def artan(n, baslangic=100.0, adim=1.0):
    return pd.Series([baslangic + adim * i for i in range(n)])


def azalan(n, baslangic=300.0, adim=1.0):
    return pd.Series([baslangic - adim * i for i in range(n)])


def sabit(n, deger=100.0):
    return pd.Series([float(deger)] * n)


# --- RSI --------------------------------------------------------------------

def test_rsi_surekli_artista_ust_sinira_yaklasir():
    """Hiç kayıp yoksa RSI 100'e dayanır."""
    assert ind.gostergeler(artan(60))["rsi"] == pytest.approx(100.0, abs=0.01)


def test_rsi_surekli_dususte_alt_sinira_yaklasir():
    assert ind.gostergeler(azalan(60))["rsi"] == pytest.approx(0.0, abs=0.01)


def test_rsi_esikleri_etikete_cevrilir():
    assert ind.rsi_durum(80) == "Aşırı alım"
    assert ind.rsi_durum(20) == "Aşırı satım"
    assert ind.rsi_durum(50) == "Nötr"
    assert ind.rsi_durum(None) == "Veri yok"
    assert ind.rsi_durum(float("nan")) == "Veri yok"


# --- Hareketli ortalamalar --------------------------------------------------

def test_sma_bilinen_degeri_verir():
    seri = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    assert ind.sma(seri, 5).iloc[-1] == pytest.approx(3.0)


def test_sma_yetersiz_barda_bos_doner():
    """4 barla 5 günlük ortalama hesaplanamaz; kısmi sonuç üretilmez."""
    assert ind.sma(pd.Series([1.0, 2.0, 3.0, 4.0]), 5).empty


def test_ema_ilk_degeri_seriyle_ayni():
    """adjust=False EMA'sı ilk barda fiyatın kendisidir."""
    assert ind.ema(pd.Series([10.0, 20.0, 30.0]), 5).iloc[0] == pytest.approx(10.0)


# --- MACD -------------------------------------------------------------------

def test_macd_sabit_seride_sifirdir():
    m = ind.macd(sabit(60))
    assert m["macd"].iloc[-1] == pytest.approx(0.0, abs=1e-9)
    assert m["histogram"].iloc[-1] == pytest.approx(0.0, abs=1e-9)


def test_macd_artan_seride_pozitif():
    """Yükselen trendde hızlı EMA yavaşın üstündedir."""
    assert ind.macd(artan(80))["macd"].iloc[-1] > 0


def test_macd_yetersiz_barda_bos_doner():
    m = ind.macd(artan(20))
    assert m["macd"].empty and m["sinyal"].empty and m["histogram"].empty


# --- Bollinger --------------------------------------------------------------

def test_bollinger_bantlari_ortayi_simetrik_sarar():
    b = ind.bollinger(pd.Series([100, 102, 98, 101, 99] * 8), periyot=20)
    orta, ust, alt = b["orta"].iloc[-1], b["ust"].iloc[-1], b["alt"].iloc[-1]
    assert ust - orta == pytest.approx(orta - alt)


def test_bollinger_sabit_seride_yuzde_b_tanimsiz():
    """Bant genişliği sıfırken %B için 0'a bölme yapılmaz."""
    assert ind.bollinger(sabit(40))["yuzde_b"] is None


def test_bollinger_yuzde_b_ust_bantta_bire_yaklasir():
    seri = pd.Series([100.0] * 19 + [120.0])
    assert ind.bollinger(seri, periyot=20)["yuzde_b"] > 0.9


# --- Kesişim ----------------------------------------------------------------

def test_yukari_kesisim_yakalanir():
    hizli = pd.Series([1.0, 2.0, 3.0, 6.0])
    yavas = pd.Series([5.0, 5.0, 5.0, 5.0])
    assert ind.kesisim(hizli, yavas) == "yukari"


def test_asagi_kesisim_yakalanir():
    hizli = pd.Series([9.0, 8.0, 7.0, 2.0])
    yavas = pd.Series([5.0, 5.0, 5.0, 5.0])
    assert ind.kesisim(hizli, yavas) == "asagi"


def test_kesisim_yoksa_none():
    assert ind.kesisim(pd.Series([6.0, 7.0, 8.0]), pd.Series([1.0, 1.0, 1.0])) is None


def test_eski_kesisim_pencere_disinda_sayilmaz():
    """20 bar önceki kesişim bugünün sinyali değildir."""
    hizli = pd.Series([1.0] + [9.0] * 20)
    yavas = pd.Series([5.0] * 21)
    assert ind.kesisim(hizli, yavas, bakilacak_bar=5) is None


# --- gostergeler() bütünü ---------------------------------------------------

def test_yetersiz_veride_hicbir_gosterge_uydurulmaz():
    olcu = ind.gostergeler(artan(10))
    for alan in ("rsi", "macd", "sma50", "sma200", "bb_yuzde_b"):
        assert olcu[alan] is None, f"{alan} uydurulmuş"
    assert {"rsi", "macd", "sma50", "sma200", "bollinger"} <= set(olcu["veri_eksik"])


def test_bos_seride_cokmez():
    olcu = ind.gostergeler(pd.Series(dtype="float64"))
    assert olcu["bar_sayisi"] == 0 and olcu["fiyat"] is None


def test_yeterli_veride_gostergeler_sayi_doner():
    olcu = ind.gostergeler(artan(260))
    for alan in ("rsi", "macd", "sma50", "sma200", "bb_yuzde_b", "fiyat"):
        assert isinstance(olcu[alan], float) and not math.isnan(olcu[alan])
    assert olcu["veri_eksik"] == []


def test_nan_degerler_disari_sizmaz():
    """Seri içindeki boşluklar temizlenir, sonuçta NaN kalmaz."""
    ham = list(artan(60))
    ham[5] = float("nan")
    olcu = ind.gostergeler(pd.Series(ham))
    assert olcu["rsi"] is not None and not math.isnan(olcu["rsi"])


def test_artan_seride_fiyat_sma200_uzerinde():
    assert ind.gostergeler(artan(260))["fiyat_sma200_uzerinde"] is True


# --- Kural motoru -----------------------------------------------------------

def test_varsayilan_kurallarin_hepsi_gecerli():
    for kural in ind.VARSAYILAN_KURALLAR:
        assert ind.kural_gecerli_mi(kural) is None, kural["ad"]


def test_gecersiz_kurallar_reddedilir():
    assert ind.kural_gecerli_mi({"ad": "x"}) is not None
    assert ind.kural_gecerli_mi(
        {"ad": "x", "gosterge": "rsi", "operator": "??", "esik": 1, "yon": "AL"}) is not None
    assert ind.kural_gecerli_mi(
        {"ad": "x", "gosterge": "rsi", "operator": "<", "esik": 1, "yon": "BELKI"}) is not None
    assert ind.kural_gecerli_mi(
        {"ad": "x", "gosterge": "rsi", "operator": "<", "esik": "otuz", "yon": "AL"}) is not None


def test_kural_esik_altinda_tetiklenir():
    kural = {"ad": "t", "gosterge": "rsi", "operator": "<", "esik": 30, "yon": "AL"}
    assert ind.kural_degerlendir(kural, {"rsi": 25}) is True
    assert ind.kural_degerlendir(kural, {"rsi": 35}) is False


def test_veri_yokken_kural_false_degil_none_doner():
    """'Koşul sağlanmadı' ile 'veri gelmedi' karıştırılmamalı."""
    kural = {"ad": "t", "gosterge": "rsi", "operator": "<", "esik": 30, "yon": "AL"}
    assert ind.kural_degerlendir(kural, {"rsi": None}) is None
    assert ind.kural_degerlendir(kural, {}) is None


def test_kesisim_kurali_yon_ayirt_eder():
    kural = {"ad": "t", "gosterge": "ma_kesisim", "operator": "kesisim",
             "esik": "yukari", "yon": "AL"}
    assert ind.kural_degerlendir(kural, {"ma_kesisim": "yukari"}) is True
    assert ind.kural_degerlendir(kural, {"ma_kesisim": "asagi"}) is False


def test_sinyal_ozeti_al_ve_sat_sayar():
    olcu = {"rsi": 25, "macd_kesisim": "yukari", "ma_kesisim": None,
            "bb_yuzde_b": 0.99}
    ozet = ind.sinyal_ozeti(olcu)
    assert "RSI aşırı satım (<30)" in ozet["al"]
    assert "Fiyat üst Bollinger bandında (%B>0.95)" in ozet["sat"]
    assert ozet["puan"] == len(ozet["al"]) - len(ozet["sat"])


def test_hicbir_gosterge_yokken_etiket_veri_yok():
    ozet = ind.sinyal_ozeti({})
    assert ozet["etiket"] == "Veri yok"
    assert ozet["al"] == [] and ozet["sat"] == []
    assert len(ozet["olculemedi"]) == len(ind.VARSAYILAN_KURALLAR)


def test_dengeli_sinyal_notr():
    ozet = ind.sinyal_ozeti({"rsi": 25, "bb_yuzde_b": 0.99})
    assert ozet["puan"] == 0 and ozet["etiket"] == "Nötr"


def test_kullanici_kurallari_varsayilanin_yerine_gecer():
    kendi = [{"ad": "kendi", "gosterge": "rsi", "operator": ">", "esik": 10, "yon": "AL"}]
    ozet = ind.sinyal_ozeti({"rsi": 50}, kurallar=kendi)
    assert ozet["al"] == ["kendi"] and ozet["sat"] == []


# --- Gösterge kataloğu ve kural kurucu --------------------------------------

def test_katalogdaki_her_gosterge_gostergeler_ciktisinda_var():
    """Katalogda olup ölçülemeyen bir alan, kurulabilir ama hiç tetiklenmeyen
    kural demektir — sessiz ölü kural."""
    olcu = ind.gostergeler(artan(260))
    for alan in ind.GOSTERGE_KATALOGU:
        assert alan in olcu, f"{alan} gostergeler() çıktısında yok"


def test_kesisim_gostergesi_buyuktur_ile_reddedilir():
    kural, sorun = ind.kural_olustur("ma_kesisim", ">", 1, "AL")
    assert kural is None and "kesişim" in sorun.lower()


def test_mantiksal_gostergede_esitlik_kabul_edilir():
    kural, sorun = ind.kural_olustur("fiyat_sma200_uzerinde", "==", True, "AL")
    assert sorun is None
    assert ind.kural_degerlendir(kural, {"fiyat_sma200_uzerinde": True}) is True
    assert ind.kural_degerlendir(kural, {"fiyat_sma200_uzerinde": False}) is False


def test_mantiksal_gostergede_buyuktur_reddedilir():
    kural, sorun = ind.kural_olustur("fiyat_sma200_uzerinde", ">", 0.5, "AL")
    assert kural is None and sorun is not None


def test_sayisal_gostergede_kesisim_reddedilir():
    kural, sorun = ind.kural_olustur("rsi", "kesisim", "yukari", "AL")
    assert kural is None and sorun is not None


def test_kural_adi_otomatik_uretilir():
    kural, sorun = ind.kural_olustur("rsi", "<", 40, "AL")
    assert sorun is None and kural["ad"] == "RSI(14) < 40 → AL"


def test_kesisim_kuralinin_adi_okunur():
    kural, _ = ind.kural_olustur("ma_kesisim", "kesisim", "yukari", "AL")
    assert "yukarı" in kural["ad"] and "AL" in kural["ad"]


def test_kendi_adini_verebilirsin():
    kural, _ = ind.kural_olustur("rsi", "<", 40, "AL", ad="Benim kuralım")
    assert kural["ad"] == "Benim kuralım"


def test_bos_ad_otomatige_duser():
    kural, _ = ind.kural_olustur("rsi", "<", 40, "AL", ad="   ")
    assert kural["ad"] == "RSI(14) < 40 → AL"


def test_ondalikli_esik_adda_duzgun_yazilir():
    kural, _ = ind.kural_olustur("bb_yuzde_b", "<", 0.05, "AL")
    assert "0.05" in kural["ad"]
