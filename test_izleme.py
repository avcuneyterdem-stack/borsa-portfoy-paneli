"""izleme için testler — izleme listesi ve alarmlar, ağ erişimi olmadan.

Korudukları: bozuk bir JSON dosyasının paneli çökertmemesi, geçersiz kuralın
alarm olarak kaydedilmemesi, ve alarmın "koşul sağlandı" ile "veri gelmedi"
durumlarını karıştırmaması. Sonuncusu önemli: veri çekilemediğinde alarm
tetiklenirse kullanıcı olmayan bir olaya göre karar verir.
"""

import json

import pytest

import izleme
import indikator as ind


@pytest.fixture
def calisma_dizini(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


RSI_KURALI = {"ad": "RSI<30", "gosterge": "rsi", "operator": "<", "esik": 30, "yon": "AL"}


# --- İzleme listesi ---------------------------------------------------------

def test_liste_yokken_bos_doner(calisma_dizini):
    assert izleme.liste_oku() == []


def test_sembol_eklenir_ve_kalici_olur(calisma_dizini):
    assert izleme.sembol_ekle("aapl", "hisse") is None
    assert izleme.liste_oku() == [{"sembol": "AAPL", "tur": "hisse"}]


def test_ayni_sembol_iki_kez_eklenmez(calisma_dizini):
    izleme.sembol_ekle("BTC", "kripto")
    assert "zaten listede" in izleme.sembol_ekle("btc", "kripto")
    assert len(izleme.liste_oku()) == 1


def test_gecersiz_tur_reddedilir(calisma_dizini):
    assert izleme.sembol_ekle("AAPL", "tahvil") is not None
    assert izleme.liste_oku() == []


def test_bos_sembol_reddedilir(calisma_dizini):
    assert izleme.sembol_ekle("   ", "hisse") is not None


def test_sembol_silinir(calisma_dizini):
    izleme.sembol_ekle("AAPL", "hisse")
    izleme.sembol_sil("aapl")
    assert izleme.liste_oku() == []


def test_olmayan_sembolu_silmek_cokmez(calisma_dizini):
    izleme.sembol_sil("YOK")
    assert izleme.liste_oku() == []


def test_bozuk_json_paneli_cokertmez(calisma_dizini):
    (calisma_dizini / izleme.IZLEME_DOSYA).write_text("{bozuk", encoding="utf-8")
    assert izleme.liste_oku() == []


def test_bozuk_kayitlar_elenir(calisma_dizini):
    (calisma_dizini / izleme.IZLEME_DOSYA).write_text(
        json.dumps([{"sembol": "AAPL", "tur": "hisse"}, {"sembol": "X"}, "çöp"]),
        encoding="utf-8")
    assert izleme.liste_oku() == [{"sembol": "AAPL", "tur": "hisse"}]


def test_turlere_ayirma(calisma_dizini):
    izleme.sembol_ekle("AAPL", "hisse")
    izleme.sembol_ekle("BTC", "kripto")
    hisseler, kriptolar = izleme.turlere_ayir(izleme.liste_oku())
    assert hisseler == ["AAPL"] and kriptolar == ["BTC"]


# --- Alarmlar ---------------------------------------------------------------

def test_alarm_eklenir(calisma_dizini):
    assert izleme.alarm_ekle("AAPL", RSI_KURALI) is None
    alarmlar = izleme.alarm_oku()
    assert len(alarmlar) == 1
    assert alarmlar[0]["sembol"] == "AAPL" and alarmlar[0]["aktif"] is True


def test_gecersiz_kural_alarm_olarak_kaydedilmez(calisma_dizini):
    bozuk = {"ad": "x", "gosterge": "rsi", "operator": "??", "esik": 1, "yon": "AL"}
    assert izleme.alarm_ekle("AAPL", bozuk) is not None
    assert izleme.alarm_oku() == []


def test_diskteki_gecersiz_kural_okumada_atlanir(calisma_dizini):
    (calisma_dizini / izleme.ALARM_DOSYA).write_text(
        json.dumps([{"id": "1", "sembol": "A", "kural": {"ad": "x"}, "aktif": True}]),
        encoding="utf-8")
    assert izleme.alarm_oku() == []


def test_alarm_silinir(calisma_dizini):
    izleme.alarm_ekle("AAPL", RSI_KURALI)
    izleme.alarm_sil(izleme.alarm_oku()[0]["id"])
    assert izleme.alarm_oku() == []


def test_alarm_pasiflestirilir(calisma_dizini):
    izleme.alarm_ekle("AAPL", RSI_KURALI)
    izleme.alarm_durum_degistir(izleme.alarm_oku()[0]["id"], False)
    assert izleme.alarm_oku()[0]["aktif"] is False


# --- Alarm değerlendirme ----------------------------------------------------

def test_kosul_saglaninca_tetiklenir(calisma_dizini):
    izleme.alarm_ekle("AAPL", RSI_KURALI)
    tetiklenen = izleme.alarmlari_degerlendir({"AAPL": {"rsi": 25}})
    assert len(tetiklenen) == 1
    assert tetiklenen[0]["sembol"] == "AAPL" and tetiklenen[0]["deger"] == 25


def test_kosul_saglanmayinca_tetiklenmez(calisma_dizini):
    izleme.alarm_ekle("AAPL", RSI_KURALI)
    assert izleme.alarmlari_degerlendir({"AAPL": {"rsi": 55}}) == []


def test_veri_yokken_tetiklenmez(calisma_dizini):
    """Gösterge çekilemediyse alarm çalmamalı — olmayan olaya karar verilmez."""
    izleme.alarm_ekle("AAPL", RSI_KURALI)
    assert izleme.alarmlari_degerlendir({"AAPL": {"rsi": None}}) == []
    assert izleme.alarmlari_degerlendir({}) == []


def test_pasif_alarm_tetiklenmez(calisma_dizini):
    izleme.alarm_ekle("AAPL", RSI_KURALI)
    izleme.alarm_durum_degistir(izleme.alarm_oku()[0]["id"], False)
    assert izleme.alarmlari_degerlendir({"AAPL": {"rsi": 25}}) == []


def test_tetiklenince_zaman_damgasi_yazilir(calisma_dizini):
    izleme.alarm_ekle("AAPL", RSI_KURALI)
    izleme.alarmlari_degerlendir({"AAPL": {"rsi": 25}})
    assert izleme.alarm_oku()[0]["son_tetik"] is not None


def test_kosul_surdukce_her_yenilemede_bildirilir(calisma_dizini):
    """Bir kez bildirip susmak, panel kapalıyken uyarıyı kaybettirir."""
    izleme.alarm_ekle("AAPL", RSI_KURALI)
    ilk = izleme.alarmlari_degerlendir({"AAPL": {"rsi": 25}})
    ikinci = izleme.alarmlari_degerlendir({"AAPL": {"rsi": 25}})
    assert len(ilk) == 1 and len(ikinci) == 1


def test_varsayilan_kurallarin_hepsi_alarm_olabilir(calisma_dizini):
    """Sinyal tablosu ve alarmlar aynı kural motorunu paylaşır."""
    for kural in ind.VARSAYILAN_KURALLAR:
        assert izleme.alarm_ekle("TEST", kural) is None
    assert len(izleme.alarm_oku()) == len(ind.VARSAYILAN_KURALLAR)


# --- Kendi kuralların -------------------------------------------------------

def test_kural_dosyasi_yokken_varsayilanlar_etkin(calisma_dizini):
    assert izleme.kural_oku() == []
    assert izleme.etkin_kurallar() == list(ind.VARSAYILAN_KURALLAR)


def test_kendi_kuralin_eklenir_ve_etkin_olur(calisma_dizini):
    kural, _ = ind.kural_olustur("rsi", "<", 40, "AL")
    assert izleme.kural_ekle(kural) is None
    assert izleme.kural_oku() == [kural]
    assert kural in izleme.etkin_kurallar()
    assert len(izleme.etkin_kurallar()) == len(ind.VARSAYILAN_KURALLAR) + 1


def test_ayni_adli_kural_iki_kez_eklenmez(calisma_dizini):
    kural, _ = ind.kural_olustur("rsi", "<", 40, "AL")
    izleme.kural_ekle(kural)
    assert "zaten var" in izleme.kural_ekle(kural)
    assert len(izleme.kural_oku()) == 1


def test_varsayilan_kural_adiyla_cakisma_engellenir(calisma_dizini):
    taklit = dict(ind.VARSAYILAN_KURALLAR[0])
    assert izleme.kural_ekle(taklit) is not None


def test_gecersiz_kural_kaydedilmez(calisma_dizini):
    assert izleme.kural_ekle({"ad": "x", "gosterge": "rsi"}) is not None
    assert izleme.kural_oku() == []


def test_kural_silinir(calisma_dizini):
    kural, _ = ind.kural_olustur("rsi", "<", 40, "AL")
    izleme.kural_ekle(kural)
    izleme.kural_sil(kural["ad"])
    assert izleme.kural_oku() == []


def test_varsayilanlar_kapatilabilir(calisma_dizini):
    kural, _ = ind.kural_olustur("rsi", "<", 40, "AL")
    izleme.kural_ekle(kural)
    izleme.varsayilan_kullanimi_degistir(False)
    assert izleme.etkin_kurallar() == [kural]


def test_hepsi_kapaliysa_kural_listesi_bos(calisma_dizini):
    izleme.varsayilan_kullanimi_degistir(False)
    assert izleme.etkin_kurallar() == []


def test_bozuk_kural_dosyasi_cokertmez(calisma_dizini):
    (calisma_dizini / izleme.KURAL_DOSYA).write_text("{bozuk", encoding="utf-8")
    assert izleme.etkin_kurallar() == list(ind.VARSAYILAN_KURALLAR)


def test_diskteki_gecersiz_kendi_kuralin_okumada_atlanir(calisma_dizini):
    (calisma_dizini / izleme.KURAL_DOSYA).write_text(
        json.dumps({"varsayilanlari_kullan": False,
                    "kurallar": [{"ad": "bozuk", "gosterge": "rsi"}]}),
        encoding="utf-8")
    assert izleme.etkin_kurallar() == []


def test_kural_ekleme_modul_sabitini_kirletmez(calisma_dizini):
    """Sığ kopya hatası: ilk ekleme varsayılan listeye sızarsa, sonraki
    çalışmalarda hiç tanımlanmamış kurallar ortaya çıkar."""
    onceki = len(ind.VARSAYILAN_KURALLAR)
    kural, _ = ind.kural_olustur("rsi", "<", 41, "AL")
    izleme.kural_ekle(kural)
    assert len(ind.VARSAYILAN_KURALLAR) == onceki
    assert all(k["ad"] != kural["ad"] for k in ind.VARSAYILAN_KURALLAR)


def test_kendi_kuralin_alarm_olarak_kurulabilir(calisma_dizini):
    kural, _ = ind.kural_olustur("rsi", "<", 45, "AL")
    assert izleme.alarm_ekle("AAPL", kural) is None
    assert izleme.alarmlari_degerlendir({"AAPL": {"rsi": 40}})[0]["kural_adi"] == kural["ad"]


# --- Toplu ekleme -----------------------------------------------------------

def test_toplu_sembol_virgulle_eklenir(calisma_dizini):
    sonuc = izleme.sembol_toplu_ekle("aapl, msft, nvda", "hisse")
    assert sonuc["eklenen"] == ["AAPL", "MSFT", "NVDA"]
    assert len(izleme.liste_oku()) == 3


def test_toplu_sembol_satir_ve_bosluk_da_ayirir(calisma_dizini):
    sonuc = izleme.sembol_toplu_ekle("BTC ETH\nSOL;AVAX", "kripto")
    assert sonuc["eklenen"] == ["BTC", "ETH", "SOL", "AVAX"]


def test_toplu_eklemede_tekrar_atlanir_digerleri_girer(calisma_dizini):
    izleme.sembol_ekle("AAPL", "hisse")
    sonuc = izleme.sembol_toplu_ekle("AAPL, MSFT", "hisse")
    assert sonuc["eklenen"] == ["MSFT"]
    assert "AAPL" in sonuc["atlanan"]
    assert len(izleme.liste_oku()) == 2


def test_ayni_metindeki_tekrar_bir_kez_islenir(calisma_dizini):
    sonuc = izleme.sembol_toplu_ekle("AAPL AAPL aapl", "hisse")
    assert sonuc["eklenen"] == ["AAPL"] and len(izleme.liste_oku()) == 1


def test_bos_metin_hicbir_sey_eklemez(calisma_dizini):
    sonuc = izleme.sembol_toplu_ekle("   ,, \n ", "hisse")
    assert sonuc["eklenen"] == [] and sonuc["atlanan"] == {}


def test_gecersiz_tur_hepsini_atlar(calisma_dizini):
    sonuc = izleme.sembol_toplu_ekle("AAPL, MSFT", "tahvil")
    assert sonuc["eklenen"] == [] and len(sonuc["atlanan"]) == 2


def test_toplu_alarm_her_sembol_icin_her_kurali_kurar(calisma_dizini):
    kurallar = ind.VARSAYILAN_KURALLAR[:2]
    sonuc = izleme.alarm_toplu_ekle(["AAPL", "MSFT"], kurallar)
    assert sonuc["eklenen"] == 4 and sonuc["atlanan"] == 0
    assert len(izleme.alarm_oku()) == 4


def test_toplu_alarm_ikinci_kez_cogaltmaz(calisma_dizini):
    """Düğmeye iki kez basmak uyarıları ikiye katlamamalı."""
    kurallar = ind.VARSAYILAN_KURALLAR[:2]
    izleme.alarm_toplu_ekle(["AAPL"], kurallar)
    sonuc = izleme.alarm_toplu_ekle(["AAPL"], kurallar)
    assert sonuc["eklenen"] == 0 and sonuc["atlanan"] == 2
    assert len(izleme.alarm_oku()) == 2


def test_alarm_var_mi_sembol_ve_kurala_bakar(calisma_dizini):
    kural = ind.VARSAYILAN_KURALLAR[0]
    izleme.alarm_ekle("AAPL", kural)
    assert izleme.alarm_var_mi("aapl", kural["ad"]) is True
    assert izleme.alarm_var_mi("MSFT", kural["ad"]) is False
    assert izleme.alarm_var_mi("AAPL", "olmayan kural") is False
