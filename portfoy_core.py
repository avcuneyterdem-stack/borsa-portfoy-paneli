"""Portföy panelinin saf hesap katmanı.

Bu modül bilinçli olarak streamlit, yfinance ve requests içermez. Para
hesaplarının tamamı burada olduğu için ağ erişimi olmadan test edilebilir.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import glob
import math
import os
import re
import time

import pandas as pd

# --- Defter şeması ----------------------------------------------------------
ZORUNLU_SUTUNLAR = [
    "Tarih", "Hisse", "Kazan", "Tip", "Fiyat", "Adet", "Toplam",
    "Para_Birimi", "Islem_Kuru", "Islem_USDTRY", "Borsa_PB", "Borsa",
]
SAYISAL_SUTUNLAR = ["Fiyat", "Adet", "Toplam", "Islem_Kuru", "Islem_USDTRY"]
METINSEL_SUTUNLAR = ["Tarih", "Hisse", "Kazan", "Tip", "Para_Birimi", "Borsa_PB", "Borsa"]

AL, SAT, GELIR = "AL", "SAT", "GELIR"

KURUSLU_BIRIMLER = {"GBp": "GBP", "GBX": "GBP", "ILA": "ILS", "ZAc": "ZAR"}

BIST_YEDEK_LISTE = {
    "THYAO", "GARAN", "KCHOL", "TUPRS", "SAHOL", "AKBNK", "YKBNK",
    "BIMAS", "SISE", "EREGL", "ASELS", "ISCTR", "FROTO", "PGSUS",
    "TCELL", "TTKOM", "ARCLK", "PETKM", "TOASO", "HEKTS",
}

TV_BORSA_ONEKI = {
    "NASDAQ": "NASDAQ", "NYSE": "NYSE", "NYSEARCA": "AMEX", "AMEX": "AMEX",
    "ISTANBUL": "BIST", "BIST": "BIST", "XETRA": "XETR", "LSE": "LSE",
}


def _pozitif(deger):
    try:
        sayi = float(deger)
    except (TypeError, ValueError):
        return None
    return sayi if math.isfinite(sayi) and sayi > 0 else None


def islem_tipi(tip_metni):
    metin = str(tip_metni).upper()
    if "TEMETT" in metin or "STAKING" in metin or "KUPON" in metin:
        return GELIR
    if "SAT" in metin:
        return SAT
    if "AL" in metin:
        return AL
    return None


def sema_uygula(df):
    df = df.copy()
    for sutun in ZORUNLU_SUTUNLAR:
        if sutun not in df.columns:
            df[sutun] = float("nan") if sutun in SAYISAL_SUTUNLAR else ""

    for sutun in SAYISAL_SUTUNLAR:
        df[sutun] = pd.to_numeric(df[sutun], errors="coerce")
    for sutun in METINSEL_SUTUNLAR:
        df[sutun] = df[sutun].fillna("").astype(str).str.strip()

    df["Fiyat"] = df["Fiyat"].fillna(0.0)
    df["Adet"] = df["Adet"].fillna(0.0)
    df["Hisse"] = df["Hisse"].str.upper()
    df["Para_Birimi"] = df["Para_Birimi"].str.upper().replace({"": "USD"})

    eksik_toplam = df["Toplam"].isna()
    df.loc[eksik_toplam, "Toplam"] = df.loc[eksik_toplam, "Fiyat"] * df.loc[eksik_toplam, "Adet"]

    ekstra = [sutun for sutun in df.columns if sutun not in ZORUNLU_SUTUNLAR]
    return df[ZORUNLU_SUTUNLAR + ekstra]


def bos_defter():
    return sema_uygula(pd.DataFrame(columns=ZORUNLU_SUTUNLAR))


def tarihe_gore_sirala(df):
    if df.empty:
        return df, 0
    try:
        anahtar = pd.to_datetime(df["Tarih"], errors="coerce", format="mixed")
    except (ValueError, TypeError):
        anahtar = pd.to_datetime(df["Tarih"], errors="coerce")
    sirali = (
        df.assign(_sira=anahtar)
        .sort_values("_sira", kind="stable", na_position="first")
        .drop(columns="_sira")
    )
    return sirali, int(anahtar.isna().sum())


def usd_maliyet(fiyat, adet, para_birimi, islem_kuru, islem_usdtry, kurlar):
    try:
        tutar = float(fiyat) * float(adet)
    except (TypeError, ValueError):
        return None, False
    if not math.isfinite(tutar):
        return None, False

    para_birimi = (str(para_birimi).strip().upper() or "USD")
    kayitli_kur = _pozitif(islem_kuru)
    kayitli_usdtry = _pozitif(islem_usdtry)

    if kayitli_kur and kayitli_usdtry:
        return tutar * kayitli_kur / kayitli_usdtry, False

    if para_birimi == "USD":
        return tutar, False

    guncel_pb = _pozitif(kurlar.get(para_birimi))
    guncel_usd = _pozitif(kurlar.get("USD"))
    if not guncel_pb or not guncel_usd:
        return None, True
    return tutar * guncel_pb / guncel_usd, True


def fiyati_usd_yap(fiyat, borsa_pb, kurlar):
    deger = _pozitif(fiyat)
    if deger is None:
        return None

    birim = (str(borsa_pb).strip() or "USD")
    if birim in KURUSLU_BIRIMLER:
        deger /= 100.0
        birim = KURUSLU_BIRIMLER[birim]
    birim = birim.upper() or "USD"

    if birim == "USD":
        return deger
    birim_kuru = _pozitif(kurlar.get(birim))
    usd_kuru = _pozitif(kurlar.get("USD"))
    if not birim_kuru or not usd_kuru:
        return None
    return deger * birim_kuru / usd_kuru


def satilabilir_adet(defter, sembol):
    if defter.empty:
        return 0.0
    satirlar = defter[defter["Hisse"].astype(str).str.upper() == str(sembol).strip().upper()]
    if satirlar.empty:
        return 0.0
    tipler = satirlar["Tip"].map(islem_tipi)
    alinan = pd.to_numeric(satirlar.loc[tipler == AL, "Adet"], errors="coerce").sum()
    satilan = pd.to_numeric(satirlar.loc[tipler == SAT, "Adet"], errors="coerce").sum()
    return float(alinan - satilan)


def pozisyon_ozeti(defter, kurlar):
    ozet = {
        "pozisyonlar": {},
        "gerceklesen_kz_usd": 0.0,
        "gelir_usd": 0.0,
        "eslesmeyen_satis": 0,
        "tahmini_kur_satir": 0,
        "hesaplanamayan_satir": 0,
        "tarihsiz_satir": 0,
    }
    if defter.empty:
        return ozet

    sirali, ozet["tarihsiz_satir"] = tarihe_gore_sirala(defter)

    for _, satir in sirali.iterrows():
        tip = islem_tipi(satir["Tip"])
        if tip is None:
            ozet["hesaplanamayan_satir"] += 1
            continue

        adet = _pozitif(satir["Adet"])
        tutar_usd, tahmini = usd_maliyet(
            satir["Fiyat"], satir["Adet"], satir["Para_Birimi"],
            satir["Islem_Kuru"], satir["Islem_USDTRY"], kurlar,
        )
        if tutar_usd is None:
            ozet["hesaplanamayan_satir"] += 1
            continue
        if tahmini:
            ozet["tahmini_kur_satir"] += 1

        if tip is GELIR:
            ozet["gelir_usd"] += tutar_usd
            continue
        if adet is None:
            ozet["hesaplanamayan_satir"] += 1
            continue

        sembol = str(satir["Hisse"]).upper()
        pozisyon = ozet["pozisyonlar"].setdefault(
            sembol, {"adet": 0.0, "maliyet_usd": 0.0, "borsa_pb": "", "borsa": ""}
        )
        if satir["Borsa_PB"]:
            pozisyon["borsa_pb"] = satir["Borsa_PB"]
        if satir["Borsa"]:
            pozisyon["borsa"] = satir["Borsa"]

        if tip is AL:
            pozisyon["adet"] += adet
            pozisyon["maliyet_usd"] += tutar_usd
            continue

        if pozisyon["adet"] <= 1e-9:
            ozet["eslesmeyen_satis"] += 1
            continue
        satilan = min(adet, pozisyon["adet"])
        if satilan < adet - 1e-9:
            ozet["eslesmeyen_satis"] += 1
        ortalama = pozisyon["maliyet_usd"] / pozisyon["adet"]
        gelir = tutar_usd * (satilan / adet)
        ozet["gerceklesen_kz_usd"] += gelir - satilan * ortalama
        pozisyon["adet"] -= satilan
        pozisyon["maliyet_usd"] -= satilan * ortalama

    return ozet


def acik_pozisyonlar(ozet, esik=1e-6):
    return {
        sembol: veri for sembol, veri in ozet["pozisyonlar"].items()
        if veri["adet"] > esik
    }


def temettu_verimi(yillik_temettu, fiyat, ham_yield=None):
    temettu = _pozitif(yillik_temettu)
    birim_fiyat = _pozitif(fiyat)
    if temettu and birim_fiyat:
        return temettu / birim_fiyat, "hesaplandi"
    if _pozitif(ham_yield):
        return None, "belirsiz"
    return None, "yok"


def sembol_normalize(sembol):
    kod = str(sembol).strip().upper()
    if not kod or kod.endswith(".IS") or "-" in kod or "." in kod or "=" in kod:
        return kod
    if kod in BIST_YEDEK_LISTE:
        return f"{kod}.IS"
    return kod


def varsayilan_borsa_pb(sembol, canli_pb=None):
    if canli_pb:
        return str(canli_pb).strip()
    kod = str(sembol).strip().upper()
    if kod.endswith(".IS"):
        return "TRY"
    if kod.endswith(".L"):
        return "GBp"
    if kod.endswith((".DE", ".PA", ".AS", ".MI")):
        return "EUR"
    return "USD"


def tv_sembol(sembol, borsa="", kripto=False):
    kod = re.sub(r"[^A-Z0-9._-]", "", str(sembol).strip().upper())
    if not kod:
        return ""
    if kripto:
        return f"BINANCE:{kod.replace('USDT', '').replace('-USD', '')}USDT"
    if kod.endswith(".IS"):
        return f"BIST:{kod[:-3]}"
    onek = TV_BORSA_ONEKI.get(re.sub(r"[^A-Z]", "", str(borsa).upper()))
    return f"{onek}:{kod}" if onek else kod


def wilder_rsi(kapanislar, periyot=14):
    fark = kapanislar.diff()
    kazanc = fark.where(fark > 0, 0.0)
    kayip = (-fark).where(fark < 0, 0.0)
    ort_kazanc = kazanc.ewm(alpha=1 / periyot, adjust=False).mean()
    ort_kayip = kayip.ewm(alpha=1 / periyot, adjust=False).mean()
    rs = ort_kazanc / ort_kayip
    return 100 - (100 / (1 + rs))


def rsi_durum(rsi):
    if rsi is None or (isinstance(rsi, float) and math.isnan(rsi)):
        return "Veri yok"
    if rsi > 70:
        return "Aşırı alım"
    if rsi < 30:
        return "Aşırı satım"
    return "Nötr"


A_KAZANI = "A Kazanı (%50 - Sakin Liman)"
B_KAZANI = "B Kazanı (%40 - Büyüme)"
C_KAZANI = "C Kazanı (%10 - Agresif)"


def kazan_sinifi(piyasa_degeri=None, beta=None, kripto_mu=False, sembol=""):
    if kripto_mu:
        return A_KAZANI if str(sembol).upper() in {"BTC", "ETH"} else C_KAZANI
    deger = _pozitif(piyasa_degeri)
    if deger is None:
        return ""
    beta_degeri = _pozitif(beta)
    if deger > 50e9 or (beta_degeri and beta_degeri < 0.85 and deger > 10e9):
        return A_KAZANI
    if deger > 2e9:
        return B_KAZANI
    return C_KAZANI


@contextlib.contextmanager
def dosya_kilidi(dosya, bekleme=10.0, bayatlama=30.0):
    kilit_yolu = f"{dosya}.lock"
    baslangic = time.monotonic()
    while True:
        try:
            tanitici = os.open(kilit_yolu, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(tanitici, str(os.getpid()).encode())
            os.close(tanitici)
            break
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(kilit_yolu) > bayatlama:
                    os.remove(kilit_yolu)
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() - baslangic > bekleme:
                raise TimeoutError(f"{dosya} için kilit alınamadı (başka bir oturum yazıyor).")
            time.sleep(0.05)
    try:
        yield
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.remove(kilit_yolu)


def yedekleri_dondur(dosya, saklanacak=10, damga=None):
    damga = damga or dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    os.replace(dosya, f"{dosya}.{damga}.bak")
    for eski in sorted(glob.glob(f"{dosya}.*.bak"), reverse=True)[saklanacak:]:
        with contextlib.suppress(OSError):
            os.remove(eski)


def atomik_yaz(df, dosya, saklanacak_yedek=10, yazici=None, okuyucu=None):
    yazici = yazici or (lambda cerceve, yol: cerceve.to_excel(yol, index=False))
    okuyucu = okuyucu or pd.read_excel

    veri = df.drop(columns=["Sil"], errors="ignore")
    kok, uzanti = os.path.splitext(dosya)
    gecici = f"{kok}.tmp{uzanti}"
    try:
        with dosya_kilidi(dosya):
            yazici(veri, gecici)
            dogrulama = okuyucu(gecici)
            if len(dogrulama) != len(veri):
                raise ValueError(
                    f"Doğrulama başarısız: {len(veri)} satır yazıldı, {len(dogrulama)} satır geri okundu."
                )
            if os.path.exists(dosya):
                yedekleri_dondur(dosya, saklanacak_yedek)
            os.replace(gecici, dosya)
    except Exception:
        with contextlib.suppress(OSError):
            os.remove(gecici)
        raise