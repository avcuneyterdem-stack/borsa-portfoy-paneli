"""Pine betiği ile Python kural motorunun aynı sayıları kullandığını doğrular.

Pine betiği TradingView'de, `indikator.py` ise panelde çalışır. İkisi ayrı
yerlerde yaşadığı için birinde eşik değiştirilip diğerinde unutulması çok
kolaydır — ve sonuç sessizdir: grafikte AL, panelde nötr görürsün, hangisine
güveneceğini bilemezsin.

Bu testler Pine dosyasını metin olarak okuyup varsayılanlarını Python
tarafındakilerle karşılaştırır. Kod çalıştırmazlar; Pine'ı burada
yorumlayamayız, ama sayıların tutmasını garanti edebiliriz.
"""

import inspect
import os
import re

import pytest

import indikator as ind

PINE_DOSYA = os.path.join(os.path.dirname(__file__), "pine", "portfoy_sinyal_motoru.pine")


@pytest.fixture(scope="module")
def pine_metni():
    if not os.path.exists(PINE_DOSYA):
        pytest.skip("Pine betiği bulunamadı.")
    with open(PINE_DOSYA, encoding="utf-8") as akis:
        return akis.read()


def girdi_varsayilani(metin, degisken):
    """`x = input.int(14, ...)` satırından 14'ü çeker."""
    kalip = rf"{degisken}\s*=\s*input\.(?:int|float)\(\s*([0-9.]+)"
    eslesme = re.search(kalip, metin)
    assert eslesme, f"Pine betiğinde '{degisken}' girdisi bulunamadı."
    return float(eslesme.group(1))


def kural_esigi(gosterge, operator):
    """VARSAYILAN_KURALLAR içinden bir eşiği bulur."""
    for kural in ind.VARSAYILAN_KURALLAR:
        if kural["gosterge"] == gosterge and kural["operator"] == operator:
            return float(kural["esik"])
    raise AssertionError(f"Python tarafında {gosterge} {operator} kuralı yok.")


def python_varsayilani(fonksiyon, parametre):
    return inspect.signature(fonksiyon).parameters[parametre].default


# --- Eşikler ----------------------------------------------------------------

def test_rsi_asiri_satim_esigi_ayni(pine_metni):
    assert girdi_varsayilani(pine_metni, "rsiAsiriSat") == kural_esigi("rsi", "<")


def test_rsi_asiri_alim_esigi_ayni(pine_metni):
    assert girdi_varsayilani(pine_metni, "rsiAsiriAl") == kural_esigi("rsi", ">")


def test_bollinger_alt_esigi_ayni(pine_metni):
    assert girdi_varsayilani(pine_metni, "bbAltEsik") == kural_esigi("bb_yuzde_b", "<")


def test_bollinger_ust_esigi_ayni(pine_metni):
    assert girdi_varsayilani(pine_metni, "bbUstEsik") == kural_esigi("bb_yuzde_b", ">")


# --- Periyotlar -------------------------------------------------------------

def test_rsi_periyodu_ayni(pine_metni):
    """Python'da RSI periyodu wilder_rsi'ın varsayılanıdır."""
    assert girdi_varsayilani(pine_metni, "rsiPeriyot") == python_varsayilani(
        ind.wilder_rsi, "periyot")


def test_macd_periyotlari_ayni(pine_metni):
    assert girdi_varsayilani(pine_metni, "macdHizli") == python_varsayilani(ind.macd, "hizli")
    assert girdi_varsayilani(pine_metni, "macdYavas") == python_varsayilani(ind.macd, "yavas")
    assert girdi_varsayilani(pine_metni, "macdSinyalLen") == python_varsayilani(
        ind.macd, "sinyal_periyot")


def test_bollinger_ayarlari_ayni(pine_metni):
    assert girdi_varsayilani(pine_metni, "bbPeriyot") == python_varsayilani(ind.bollinger, "periyot")
    assert girdi_varsayilani(pine_metni, "bbSapma") == python_varsayilani(ind.bollinger, "sapma")


def test_kesisim_penceresi_ayni(pine_metni):
    """Pine tek bara, Python beş bara bakarsa aynı kesişimi farklı görürler."""
    assert girdi_varsayilani(pine_metni, "bakilacakBar") == python_varsayilani(
        ind.kesisim, "bakilacak_bar")


def test_sma_periyotlari_ayni(pine_metni):
    """Python'da 50/200 gostergeler() içinde sabittir."""
    olcu = ind.gostergeler([float(i) for i in range(1, 261)])
    assert olcu["sma50"] is not None and olcu["sma200"] is not None
    assert girdi_varsayilani(pine_metni, "smaKisa") == 50
    assert girdi_varsayilani(pine_metni, "smaUzun") == 200


# --- Kural sayısı -----------------------------------------------------------

def test_pine_sekiz_kuralin_hepsini_tasiyor(pine_metni):
    """Python'a kural eklenip Pine'a eklenmezse puanlar tutmaz."""
    pine_kurallari = re.findall(r"^kural[A-Za-z]+\s*=", pine_metni, flags=re.MULTILINE)
    assert len(pine_kurallari) == len(ind.VARSAYILAN_KURALLAR)


def test_pine_puani_al_eksi_sat_olarak_tanimli(pine_metni):
    assert re.search(r"puan\s*=\s*alSayisi\s*-\s*satSayisi", pine_metni)
