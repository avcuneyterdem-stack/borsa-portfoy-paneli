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
