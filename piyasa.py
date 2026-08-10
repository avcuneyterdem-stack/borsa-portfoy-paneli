"""Piyasa verisi katmanı: kurlar, hisse ve kripto fiyatları.

Streamlit içermez; hem panel hem de komut satırı betikleri kullanabilir.
Önbellekleme çağıran tarafın işidir (panelde `st.cache_data`, betiklerde
tek seferlik çalıştırma).

Buradaki hiçbir fonksiyon veri bulamadığında uydurma değer döndürmez;
bulunamayan alan `None` kalır. Sabit bir kur varsayımı (ör. "USD 34.0")
sessizce yanlış portföy değeri üretir.
"""

from __future__ import annotations

import contextlib
import json
import logging

import pandas as pd
import requests
import yfinance as yf

import portfoy_core as pc

kayitci = logging.getLogger(__name__)

BINANCE = "https://api.binance.com"
TEMEL_PARA_BIRIMLERI = ("USD", "EUR", "GBP")


def _hizli_al(hizli_bilgi, *adlar):
    """yfinance FastInfo'dan sürümden bağımsız alan okuma."""
    for ad in adlar:
        with contextlib.suppress(Exception):
            deger = hizli_bilgi[ad]
            if deger is not None:
                return deger
        with contextlib.suppress(Exception):
            deger = getattr(hizli_bilgi, ad)
            if deger is not None and not callable(deger):
                return deger
    return None


def kurlari_getir(para_birimleri=()):
    """İstenen para birimlerinin TL karşılığı. Çekilemeyen birim None kalır.

    Sözlük TL tabanlıdır: kurlar["USD"] = 1 doların TL karşılığı.
    """
    kurlar = {"TRY": 1.0}
    istenen = [
        pb for pb in sorted(set(para_birimleri) | set(TEMEL_PARA_BIRIMLERI))
        if pb and pb != "TRY"
    ]
    for pb in istenen:
        kurlar[pb] = None
    if not istenen:
        return kurlar

    semboller = [f"{pb}TRY=X" for pb in istenen]
    try:
        veri = yf.download(semboller, period="5d", progress=False, auto_adjust=False)["Close"]
        for pb, sembol in zip(istenen, semboller):
            try:
                seri = (veri[sembol] if len(semboller) > 1 else veri).dropna()
                if not seri.empty:
                    kurlar[pb] = float(seri.iloc[-1])
            except (KeyError, IndexError, TypeError, ValueError):
                kayitci.warning("Kur çekilemedi: %s", sembol)
    except Exception:
        kayitci.exception("Kur servisi yanıt vermedi")
    return kurlar


def sembol_meta(kod):
    """Sembolün borsa para birimi ve piyasa değeri. Yavaş olan `.info` çağrılmaz."""
    meta = {"borsa_pb": pc.varsayilan_borsa_pb(kod), "piyasa_degeri": None}
    try:
        hizli = yf.Ticker(kod).fast_info
        meta["borsa_pb"] = pc.varsayilan_borsa_pb(kod, _hizli_al(hizli, "currency"))
        meta["piyasa_degeri"] = _hizli_al(hizli, "market_cap", "marketCap")
    except Exception:
        kayitci.warning("Sembol bilgisi alınamadı: %s", kod)
    return meta


def hisse_fiyatlari(semboller):
    """Hisseleri tek çağrıda çeker: son fiyat, günlük değişim, RSI(14).

    Anahtarlar normalize edilmiş kodlardır (`pc.sembol_normalize`).
    """
    kodlar = sorted({pc.sembol_normalize(s) for s in semboller if str(s).strip()})
    if not kodlar:
        return {}
    try:
        veri = yf.download(
            kodlar, period="90d", group_by="ticker",
            auto_adjust=False, progress=False, threads=True,
        )
    except Exception:
        kayitci.exception("Toplu fiyat çekimi başarısız")
        return {}

    sonuc = {}
    for kod in kodlar:
        try:
            cerceve = veri if len(kodlar) == 1 else veri[kod]
            kapanis = cerceve["Close"].dropna()
            if len(kapanis) < 2:
                continue
            son_rsi = pc.wilder_rsi(kapanis).iloc[-1]
            sonuc[kod] = {
                "fiyat": float(kapanis.iloc[-1]),
                "degisim": (float(kapanis.iloc[-1]) / float(kapanis.iloc[-2]) - 1) * 100,
                "rsi": None if pd.isna(son_rsi) else round(float(son_rsi), 2),
            }
        except (KeyError, IndexError, TypeError, ValueError):
            kayitci.warning("Fiyat verisi ayrıştırılamadı: %s", kod)
    return sonuc


def binance_sembolleri():
    try:
        yanit = requests.get(f"{BINANCE}/api/v3/ticker/price", timeout=5)
        yanit.raise_for_status()
        return sorted({s["symbol"] for s in yanit.json() if s["symbol"].endswith("USDT")})
    except Exception:
        kayitci.exception("Binance sembol listesi alınamadı")
        return []


def kripto_fiyatlari(semboller, gecerli_liste=None):
    """Kripto fiyatı ve 24 saatlik değişim. Yalnızca geçerli pariteler sorulur."""
    gecerli = set(gecerli_liste if gecerli_liste is not None else binance_sembolleri())
    parite = {f"{str(s).upper().replace('USDT', '')}USDT": str(s).upper() for s in semboller if str(s).strip()}
    sorulacak = [p for p in sorted(parite) if p in gecerli]
    if not sorulacak:
        return {}
    try:
        yanit = requests.get(
            f"{BINANCE}/api/v3/ticker/24hr",
            params={"symbols": json.dumps(sorulacak, separators=(",", ":"))},
            timeout=8,
        )
        yanit.raise_for_status()
        return {
            parite[kayit["symbol"]]: {
                "fiyat": float(kayit["lastPrice"]),
                "degisim": float(kayit["priceChangePercent"]),
            }
            for kayit in yanit.json() if kayit["symbol"] in parite
        }
    except Exception:
        kayitci.exception("Kripto fiyatları alınamadı")
        return {}


def kripto_rsi(sembol):
    try:
        yanit = requests.get(
            f"{BINANCE}/api/v3/klines",
            params={"symbol": f"{str(sembol).upper()}USDT", "interval": "1d", "limit": 90},
            timeout=8,
        )
        yanit.raise_for_status()
        kapanis = pd.Series([float(mum[4]) for mum in yanit.json()])
        if len(kapanis) < 20:
            return None
        son = pc.wilder_rsi(kapanis).iloc[-1]
        return None if pd.isna(son) else round(float(son), 2)
    except Exception:
        kayitci.warning("Kripto RSI alınamadı: %s", sembol)
        return None


# --- Portföy geneli ---------------------------------------------------------

def portfoy_degerle(defter_hisse, defter_kripto):
    """İki defteri de canlı fiyatlarla değerler.

    Döndürülen sözlükte `kur_eksik` veya `fiyatsiz` doluysa rakamlar
    eksiktir; çağıran taraf buna göre karar vermelidir.
    """
    hisse_semboller = sorted(set(defter_hisse["Hisse"]) - {""})
    kripto_semboller = sorted(set(defter_kripto["Hisse"]) - {""})

    gereken = (
        set(defter_hisse["Para_Birimi"]) | set(defter_kripto["Para_Birimi"])
        | {pc.KURUSLU_BIRIMLER.get(pc.varsayilan_borsa_pb(s), pc.varsayilan_borsa_pb(s)).upper()
           for s in hisse_semboller}
    )
    kurlar = kurlari_getir(tuple(gereken))
    fiyatlar = hisse_fiyatlari(hisse_semboller)
    kripto = kripto_fiyatlari(kripto_semboller)

    sonuc = {
        "kurlar": kurlar,
        "maliyet_usd": 0.0,
        "deger_usd": 0.0,
        "gerceklesen_kz_usd": 0.0,
        "gelir_usd": 0.0,
        "fiyatsiz": [],
        "kur_eksik": kurlar.get("USD") is None,
        "uyarilar": [],
    }

    for defter, kripto_mu in ((defter_hisse, False), (defter_kripto, True)):
        ozet = pc.pozisyon_ozeti(defter, kurlar)
        sonuc["gerceklesen_kz_usd"] += ozet["gerceklesen_kz_usd"]
        sonuc["gelir_usd"] += ozet["gelir_usd"]
        for ad, sayi in (("eşleşmeyen satış", ozet["eslesmeyen_satis"]),
                         ("tarihsel kuru olmayan satır", ozet["tahmini_kur_satir"]),
                         ("hesaplanamayan satır", ozet["hesaplanamayan_satir"])):
            if sayi:
                sonuc["uyarilar"].append(f"{sayi} {ad}")

        for sembol, pozisyon in pc.acik_pozisyonlar(ozet).items():
            sonuc["maliyet_usd"] += pozisyon["maliyet_usd"]
            if kripto_mu:
                fiyat_usd = kripto.get(sembol, {}).get("fiyat")
            else:
                kod = pc.sembol_normalize(sembol)
                fiyat_usd = pc.fiyati_usd_yap(
                    fiyatlar.get(kod, {}).get("fiyat"),
                    sembol_meta(kod)["borsa_pb"],
                    kurlar,
                )
            if fiyat_usd is None:
                sonuc["fiyatsiz"].append(sembol)
            else:
                sonuc["deger_usd"] += pozisyon["adet"] * fiyat_usd

    return sonuc
