"""Teknik gösterge hesabı ve kural motoru.

Bu modül `portfoy_core` gibi bilinçli olarak saftır: ağ, dosya ve streamlit
içermez. Girdi bir kapanış fiyatı serisi, çıktı sayıdır. Böylece gösterge
matematiği internet olmadan test edilebilir ve panelden bağımsız doğrulanır.

Veri yetmediğinde uydurma değer üretilmez, `None` döner. 200 günlük ortalama
için 200 kapanış yoksa sonuç "yok"tur — 150 günlük ortalamayı 200 diye
sunmak sessizce yanlış sinyal üretir.

RSI'ın tek tanımı `portfoy_core.wilder_rsi`'dir; burada yeniden yazılmaz,
oradan alınır. İki ayrı RSI tanımı, biri düzeltilip diğeri unutulduğunda
panelin iki yerinde farklı rakam gösterir.

Kural motoru hem "sinyal tablosu" hem "alarm" için kullanılır: ikisi de aynı
şeydir — bir göstergeyi bir eşikle karşılaştıran ifade. Tek motor, tek test.

YATIRIM TAVSİYESİ DEĞİLDİR. Buradaki hiçbir fonksiyon "al" veya "sat"
önermez; yalnızca kullanıcının kendi tanımladığı kuralın sonucunu bildirir.
"""

from __future__ import annotations

import math

import pandas as pd

from portfoy_core import wilder_rsi  # noqa: F401 — dışarıya yeniden sunulur

# Göstergelerin ihtiyaç duyduğu asgari kapanış sayısı. Altında None dönülür.
ASGARI_BAR = {
    "rsi": 15,          # 14 periyot + ilk fark
    "macd": 35,         # 26 yavaş EMA + 9 sinyal
    "sma50": 50,
    "sma200": 200,
    "bollinger": 20,
}


def _seri(kapanislar):
    """Girdiyi sayısal, boşluksuz bir pandas Series'e çevirir."""
    seri = pd.Series(kapanislar, dtype="float64") if not isinstance(kapanislar, pd.Series) \
        else kapanislar.astype("float64")
    return seri.dropna().reset_index(drop=True)


def _son(seri):
    """Serinin son değerini float olarak verir; NaN ise None."""
    if seri is None or len(seri) == 0:
        return None
    deger = seri.iloc[-1]
    return None if pd.isna(deger) else float(deger)


# ===========================================================================
# GÖSTERGELER
# ===========================================================================

def ema(kapanislar, periyot):
    """Üssel hareketli ortalama (adjust=False — TradingView ile aynı)."""
    return _seri(kapanislar).ewm(span=periyot, adjust=False).mean()


def sma(kapanislar, periyot):
    """Basit hareketli ortalama. Yeterli bar yoksa boş seri döner."""
    seri = _seri(kapanislar)
    if len(seri) < periyot:
        return pd.Series(dtype="float64")
    return seri.rolling(window=periyot).mean()


def macd(kapanislar, hizli=12, yavas=26, sinyal_periyot=9):
    """MACD çizgisi, sinyal çizgisi ve histogram.

    Üçü de aynı uzunlukta seri döner. Yeterli bar yoksa üçü de boştur;
    kısmi hesap dönmez çünkü ilk barlardaki EMA değerleri güvenilmezdir.
    """
    seri = _seri(kapanislar)
    bos = pd.Series(dtype="float64")
    if len(seri) < ASGARI_BAR["macd"]:
        return {"macd": bos, "sinyal": bos, "histogram": bos}

    cizgi = ema(seri, hizli) - ema(seri, yavas)
    sinyal = cizgi.ewm(span=sinyal_periyot, adjust=False).mean()
    return {"macd": cizgi, "sinyal": sinyal, "histogram": cizgi - sinyal}


def bollinger(kapanislar, periyot=20, sapma=2.0):
    """Bollinger bantları ve %B.

    %B, fiyatın bantlar içindeki göreli yerini verir: 0 alt bant, 1 üst
    bant. Bant genişliği sıfırsa (fiyat hiç oynamamışsa) %B tanımsızdır ve
    None döner — 0'a bölme sonucunu sayı diye sunmak yanlış olur.
    """
    seri = _seri(kapanislar)
    bos = pd.Series(dtype="float64")
    if len(seri) < periyot:
        return {"orta": bos, "ust": bos, "alt": bos, "yuzde_b": None}

    orta = seri.rolling(window=periyot).mean()
    # ddof=0: popülasyon standart sapması — Bollinger'ın orijinal tanımı.
    std = seri.rolling(window=periyot).std(ddof=0)
    ust, alt = orta + sapma * std, orta - sapma * std

    genislik = _son(ust) - _son(alt) if _son(ust) is not None and _son(alt) is not None else None
    yuzde_b = None
    if genislik:  # 0 ve None birlikte elenir
        yuzde_b = (float(seri.iloc[-1]) - _son(alt)) / genislik

    return {"orta": orta, "ust": ust, "alt": alt, "yuzde_b": yuzde_b}


def kesisim(hizli_seri, yavas_seri, bakilacak_bar=5):
    """Son `bakilacak_bar` içinde kesişim olmuş mu?

    Döner: "yukari" (hızlı olan yavaşı yukarı kesti — altın kesişim),
    "asagi" (ölüm kesişimi), None (kesişim yok veya veri yetersiz).

    Yalnızca son barda değil, birkaç bar geriye bakılır: kesişimi kaçırmamak
    için. Panel günde bir kez açılıyorsa tek barlık pencere kesişimlerin
    çoğunu görmez.
    """
    if hizli_seri is None or yavas_seri is None:
        return None
    fark = (pd.Series(hizli_seri) - pd.Series(yavas_seri)).dropna()
    if len(fark) < 2:
        return None

    pencere = fark.iloc[-min(bakilacak_bar + 1, len(fark)):]
    isaretler = [1 if d > 0 else (-1 if d < 0 else 0) for d in pencere]
    for onceki, simdiki in zip(isaretler, isaretler[1:]):
        if onceki < 0 and simdiki > 0:
            return "yukari"
        if onceki > 0 and simdiki < 0:
            return "asagi"
    return None


def gostergeler(kapanislar):
    """Bir kapanış serisinden bütün göstergeleri tek sözlükte toplar.

    Her alan ya bir sayı ya None'dır; NaN dışarı sızmaz. Hesaplanamayan
    gösterge `veri_eksik` listesinde adıyla belirtilir, böylece panel
    "veri yok" ile "nötr" arasını ayırt edebilir.
    """
    seri = _seri(kapanislar)
    sonuc = {
        "bar_sayisi": len(seri),
        "fiyat": _son(seri),
        "rsi": None, "macd": None, "macd_sinyal": None, "macd_histogram": None,
        "macd_kesisim": None, "sma50": None, "sma200": None, "ma_kesisim": None,
        "fiyat_sma200_uzerinde": None, "bb_yuzde_b": None,
        "veri_eksik": [],
    }

    if len(seri) >= ASGARI_BAR["rsi"]:
        sonuc["rsi"] = _son(wilder_rsi(seri))
    else:
        sonuc["veri_eksik"].append("rsi")

    if len(seri) >= ASGARI_BAR["macd"]:
        m = macd(seri)
        sonuc["macd"] = _son(m["macd"])
        sonuc["macd_sinyal"] = _son(m["sinyal"])
        sonuc["macd_histogram"] = _son(m["histogram"])
        sonuc["macd_kesisim"] = kesisim(m["macd"], m["sinyal"])
    else:
        sonuc["veri_eksik"].append("macd")

    for periyot in (50, 200):
        anahtar = f"sma{periyot}"
        if len(seri) >= periyot:
            sonuc[anahtar] = _son(sma(seri, periyot))
        else:
            sonuc["veri_eksik"].append(anahtar)

    if sonuc["sma50"] is not None and sonuc["sma200"] is not None:
        sonuc["ma_kesisim"] = kesisim(sma(seri, 50), sma(seri, 200))
    if sonuc["fiyat"] is not None and sonuc["sma200"] is not None:
        sonuc["fiyat_sma200_uzerinde"] = sonuc["fiyat"] > sonuc["sma200"]

    if len(seri) >= ASGARI_BAR["bollinger"]:
        sonuc["bb_yuzde_b"] = bollinger(seri)["yuzde_b"]
    else:
        sonuc["veri_eksik"].append("bollinger")

    return sonuc


def rsi_durum(rsi):
    """RSI'ı okunur bir etikete çevirir (portfoy_core ile aynı eşikler)."""
    if rsi is None or (isinstance(rsi, float) and math.isnan(rsi)):
        return "Veri yok"
    if rsi > 70:
        return "Aşırı alım"
    if rsi < 30:
        return "Aşırı satım"
    return "Nötr"


# ===========================================================================
# KURAL MOTORU — sinyal tablosu ve alarmlar aynı motoru kullanır
# ===========================================================================

# Kural sözlüğü: {"ad", "gosterge", "operator", "esik", "yon"}
#   gosterge : gostergeler() çıktısındaki alan adı
#   operator : "<", ">", "==", "kesisim"
#   esik     : sayı; "kesisim" için "yukari"/"asagi"
#   yon      : "AL" veya "SAT" — yalnızca etikettir, emir değildir
OPERATORLER = ("<", ">", "==", "kesisim")
YONLER = ("AL", "SAT")

VARSAYILAN_KURALLAR = [
    {"ad": "RSI aşırı satım (<30)", "gosterge": "rsi", "operator": "<", "esik": 30, "yon": "AL"},
    {"ad": "RSI aşırı alım (>70)", "gosterge": "rsi", "operator": ">", "esik": 70, "yon": "SAT"},
    {"ad": "MACD yukarı kesişim", "gosterge": "macd_kesisim", "operator": "kesisim",
     "esik": "yukari", "yon": "AL"},
    {"ad": "MACD aşağı kesişim", "gosterge": "macd_kesisim", "operator": "kesisim",
     "esik": "asagi", "yon": "SAT"},
    {"ad": "Altın kesişim (SMA50 > SMA200)", "gosterge": "ma_kesisim", "operator": "kesisim",
     "esik": "yukari", "yon": "AL"},
    {"ad": "Ölüm kesişimi (SMA50 < SMA200)", "gosterge": "ma_kesisim", "operator": "kesisim",
     "esik": "asagi", "yon": "SAT"},
    {"ad": "Fiyat alt Bollinger bandında (%B<0.05)", "gosterge": "bb_yuzde_b",
     "operator": "<", "esik": 0.05, "yon": "AL"},
    {"ad": "Fiyat üst Bollinger bandında (%B>0.95)", "gosterge": "bb_yuzde_b",
     "operator": ">", "esik": 0.95, "yon": "SAT"},
]


def kural_gecerli_mi(kural):
    """Kural sözlüğü yapısal olarak kullanılabilir mi? Hata mesajı veya None."""
    if not isinstance(kural, dict):
        return "Kural bir sözlük olmalı."
    for alan in ("ad", "gosterge", "operator", "esik", "yon"):
        if alan not in kural:
            return f"Eksik alan: {alan}"
    if kural["operator"] not in OPERATORLER:
        return f"Bilinmeyen operatör: {kural['operator']}"
    if kural["yon"] not in YONLER:
        return f"Yön 'AL' veya 'SAT' olmalı, '{kural['yon']}' değil."
    if kural["operator"] == "kesisim":
        if kural["esik"] not in ("yukari", "asagi"):
            return "Kesişim eşiği 'yukari' veya 'asagi' olmalı."
    elif not isinstance(kural["esik"], (int, float)) or isinstance(kural["esik"], bool):
        return "Eşik sayı olmalı."
    return None


def kural_degerlendir(kural, olculer):
    """Kuralı ölçülere uygular.

    Döner: True (tetiklendi), False (tetiklenmedi), None (gösterge yok —
    veri yetersiz). None ile False'ın ayrı olması önemli: "veri gelmedi" ile
    "koşul sağlanmadı" farklı şeylerdir ve kullanıcıya farklı görünmelidir.
    """
    if kural_gecerli_mi(kural) is not None:
        return None
    deger = olculer.get(kural["gosterge"])
    if deger is None:
        return None

    operator, esik = kural["operator"], kural["esik"]
    if operator == "kesisim":
        return deger == esik
    if operator == "<":
        return deger < esik
    if operator == ">":
        return deger > esik
    return deger == esik


def sinyal_ozeti(olculer, kurallar=None):
    """Bütün kuralları uygular ve tek bir özet döndürür.

    `puan` = tetiklenen AL sayısı − tetiklenen SAT sayısı. Bu bir tavsiye
    değil, yalnızca kullanıcının kendi kurallarının sayımıdır; kuralların
    ağırlığı yoktur ve hiçbiri diğerinden değerli sayılmaz.
    """
    kurallar = VARSAYILAN_KURALLAR if kurallar is None else kurallar
    al, sat, olculemedi = [], [], []

    for kural in kurallar:
        sonuc = kural_degerlendir(kural, olculer)
        if sonuc is None:
            olculemedi.append(kural["ad"])
        elif sonuc:
            (al if kural["yon"] == "AL" else sat).append(kural["ad"])

    puan = len(al) - len(sat)
    if olculemedi and not al and not sat:
        etiket = "Veri yok"
    elif puan > 0:
        etiket = "AL yönlü"
    elif puan < 0:
        etiket = "SAT yönlü"
    else:
        etiket = "Nötr"

    return {"al": al, "sat": sat, "olculemedi": olculemedi,
            "puan": puan, "etiket": etiket}
