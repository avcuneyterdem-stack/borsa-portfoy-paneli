"""Global Ajan Portföy Paneli — Streamlit arayüzü.

Para hesaplarının tamamı portfoy_core içindedir ve testlidir. Bu dosya
yalnızca üç işi yapar: diskten okuma/yazma, piyasa verisi çekme ve çizim.
"""

from __future__ import annotations

import datetime as dt
import glob
import json
import logging
import os
import time
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
from streamlit_searchbox import st_searchbox

import indikator as ind
import izleme
import portfoy_core as pc
# Sekme 4'te `piyasa` adında yerel bir değişken var; modülü olduğu gibi
# içe aktarmak onu ezerdi. Bu yüzden fonksiyonlar tek tek alınıyor.
from piyasa import (
    binance_sembolleri as _binance_sembolleri,
    gosterge_paketi as _gosterge_paketi,
    hisse_fiyatlari as _hisse_fiyatlari,
    kripto_fiyatlari as _kripto_fiyatlari,
    kripto_rsi as _kripto_rsi,
    kurlari_getir as _kurlari_getir,
    sembol_meta as _sembol_meta,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
kayitci = logging.getLogger("portfoy")

st.set_page_config(page_title="Global Ajan Portföy Paneli", page_icon="🌍", layout="wide")

EXCEL_HISSE = "portfoy_defteri_hisse.xlsx"
EXCEL_KRIPTO = "portfoy_defteri_kripto.xlsx"
YEDEK_SAYISI = 10
TSI = ZoneInfo("Europe/Istanbul")
BINANCE = "https://api.binance.com"

if os.path.exists("portfoy_defteri.xlsx") and not os.path.exists(EXCEL_HISSE):
    os.rename("portfoy_defteri.xlsx", EXCEL_HISSE)


@st.cache_data(show_spinner=False, max_entries=8)
def _excel_oku(dosya, _degisiklik_zamani):
    return pd.read_excel(dosya)


def veri_yukle(dosya):
    hatalar = st.session_state.setdefault("yukleme_hatalari", {})
    if not os.path.exists(dosya):
        hatalar[dosya] = None
        return pc.bos_defter()
    try:
        ham = _excel_oku(dosya, os.path.getmtime(dosya))
        hatalar[dosya] = None
        return pc.sema_uygula(ham)
    except Exception as hata:
        kayitci.exception("Defter okunamadı: %s", dosya)
        hatalar[dosya] = str(hata)
        st.error(
            f"⚠️ **{dosya} okunamadı:** {hata}\n\n"
            "Veri kaybını önlemek için bu deftere yazma kilitlendi. "
            "Dosya başka bir programda açıksa kapatıp sayfayı yenileyin."
        )
        return pc.bos_defter()


def veri_kaydet(df, dosya):
    if st.session_state.get("yukleme_hatalari", {}).get(dosya):
        st.error("❌ Bu defter okunamadığı için yazma engellendi. Önce dosya sorununu giderin.")
        return False
    try:
        pc.atomik_yaz(df, dosya, saklanacak_yedek=YEDEK_SAYISI)
        _excel_oku.clear()
        return True
    except Exception as hata:
        kayitci.exception("Kayıt başarısız: %s", dosya)
        st.error(f"❌ Kayıt başarısız: {hata}  \nDosyanın önceki hâli değiştirilmedi.")
        return False


# --- Piyasa verisi ----------------------------------------------------------
# Bu fonksiyonların gövdesi `piyasa.py` içindedir; buradakiler yalnızca
# streamlit önbelleğini ekleyen ince sarmalayıcılardır.
#
# Daha önce her ikisinde de tam kopyaları vardı. Kopya, bugün yanlış sayı
# üretmiyordu (ölçüldü) ama ilk düzeltmede üretmeye başlardı: birinde
# düzeltilen hata diğerinde kalırdı. Tek kaynak, tek davranış.

@st.cache_data(ttl=300, show_spinner=False)
def kurlari_getir(para_birimleri):
    return _kurlari_getir(para_birimleri)


@st.cache_data(ttl=21600, show_spinner=False, max_entries=512)
def sembol_meta(kod):
    return _sembol_meta(kod)


@st.cache_data(ttl=180, show_spinner=False)
def hisse_piyasa_verisi(semboller):
    return _hisse_fiyatlari(semboller)


@st.cache_data(ttl=3600, show_spinner=False)
def binance_sembolleri():
    return _binance_sembolleri()


@st.cache_data(ttl=120, show_spinner=False)
def kripto_piyasa_verisi(semboller):
    return _kripto_fiyatlari(semboller, gecerli_liste=set(binance_sembolleri()))


@st.cache_data(ttl=600, show_spinner=False, max_entries=128)
def kripto_rsi(sembol):
    return _kripto_rsi(sembol)


@st.cache_data(ttl=3600, show_spinner=False, max_entries=256)
def temettu_bilgisi(kod):
    try:
        varlik = yf.Ticker(kod)
        bilgi = varlik.info
        return {
            "yillik_temettu": bilgi.get("dividendRate"),
            "fiyat": bilgi.get("currentPrice") or bilgi.get("previousClose"),
            "ham_yield": bilgi.get("dividendYield"),
            "ex_tarih": bilgi.get("exDividendDate"),
            "sektor": bilgi.get("sector"),
            "para_birimi": bilgi.get("currency", "USD"),
        }
    except Exception as hata:
        kayitci.warning("Temettü bilgisi alınamadı: %s (%s)", kod, hata)
        return None


def hisse_ara(arama):
    if not str(arama).strip():
        return []
    try:
        yanit = requests.get(
            "https://query2.finance.yahoo.com/v1/finance/search",
            params={"q": arama, "quotesCount": 10, "newsCount": 0},
            headers={"User-Agent": "Mozilla/5.0"}, timeout=4,
        )
        yanit.raise_for_status()
        sonuclar = []
        for kayit in yanit.json().get("quotes", []):
            sembol = kayit.get("symbol")
            if not sembol:
                continue
            ad = kayit.get("shortname") or kayit.get("longname") or sembol
            borsa = kayit.get("exchDisp", "")
            sonuclar.append((f"🌐 {sembol} — {ad} ({borsa})", f"{sembol}|{borsa}"))
        return sonuclar
    except Exception:
        kayitci.warning("Hisse araması başarısız: %s", arama)
        return [(f"{str(arama).upper()} (arama servisi yanıt vermedi)", f"{str(arama).upper()}|")]


def kripto_ara(arama):
    terim = str(arama).strip().upper()
    if not terim:
        return []
    semboller = binance_sembolleri()
    baslayanlar = [s for s in semboller if s.startswith(terim)]
    icerenler = [s for s in semboller if terim in s and not s.startswith(terim)]
    return [
        (f"🪙 {s[:-4]} / USDT", s[:-4])
        for s in (baslayanlar + icerenler)[:15]
    ] or [(f"🪙 {terim} / USDT (listede yok)", terim)]


def secimi_coz(secim):
    if not secim:
        return "", ""
    sembol, _, borsa = str(secim).partition("|")
    return sembol.strip().upper(), borsa.strip()


def pozisyon_tablosu(ozet, fiyat_saglayici, kurlar, kripto_mu=False):
    satirlar, toplam_maliyet, toplam_deger, fiyatsiz = [], 0.0, 0.0, 0
    for sembol, pozisyon in sorted(pc.acik_pozisyonlar(ozet).items()):
        maliyet = pozisyon["maliyet_usd"]
        piyasa = fiyat_saglayici(sembol, pozisyon)
        canli_usd = piyasa.get("fiyat_usd")
        toplam_maliyet += maliyet

        if canli_usd is None:
            fiyatsiz += 1
            deger_metni = kz_metni = fiyat_metni = "N/A"
        else:
            deger = pozisyon["adet"] * canli_usd
            toplam_deger += deger
            fiyat_metni = f"${canli_usd:,.2f}"
            deger_metni = f"${deger:,.2f}"
            kz_metni = f"${deger - maliyet:,.2f}"

        satirlar.append({
            "Varlık": sembol,
            "Kazan": piyasa.get("kazan", ""),
            "Adet": round(pozisyon["adet"], 6 if kripto_mu else 4),
            "Ort. Maliyet ($)": round(maliyet / pozisyon["adet"], 4 if kripto_mu else 2),
            "Canlı Fiyat ($)": fiyat_metni,
            "Güncel Değer ($)": deger_metni,
            "Açık K/Z ($)": kz_metni,
            "RSI (14)": piyasa.get("rsi") if piyasa.get("rsi") is not None else "—",
            "RSI Durumu": pc.rsi_durum(piyasa.get("rsi")),
        })
    return pd.DataFrame(satirlar), toplam_maliyet, toplam_deger, fiyatsiz


def ozet_uyarilari(ozet, fiyatsiz):
    if ozet["hesaplanamayan_satir"]:
        st.warning(f"⚠️ {ozet['hesaplanamayan_satir']} satır eksik/bozuk veri nedeniyle hesaba katılamadı.")
    if ozet["eslesmeyen_satis"]:
        st.warning(
            f"⚠️ {ozet['eslesmeyen_satis']} satış kaydı eldeki pozisyonla eşleşmedi "
            "(elde olandan fazla veya alım kaydı olmayan satış). Gerçekleşen K/Z eksik olabilir."
        )
    if ozet["tahmini_kur_satir"]:
        st.info(
            f"ℹ️ {ozet['tahmini_kur_satir']} eski kayıtta işlem anındaki kur bulunmadığı için "
            "bugünkü kur kullanıldı; bu satırların dolar maliyeti yaklaşıktır."
        )
    if ozet["tarihsiz_satir"]:
        st.info(f"ℹ️ {ozet['tarihsiz_satir']} kaydın tarihi okunamadı; sıralamada en başa alındı.")
    if fiyatsiz:
        st.warning(f"⚠️ {fiyatsiz} varlığın canlı fiyatı çekilemedi; ilgili satırlar N/A ve toplamlara dahil değil.")


def metrik_satiri(ozet, toplam_maliyet, toplam_deger, gelir_etiketi):
    kutu = st.columns(5)
    kutu[0].metric("Toplam Maliyet ($)", f"${toplam_maliyet:,.2f}")
    kutu[1].metric("Güncel Değer ($)", f"${toplam_deger:,.2f}" if toplam_deger else "N/A")
    kutu[2].metric(
        "Açık Pozisyon K/Z ($)",
        f"${toplam_deger - toplam_maliyet:,.2f}" if toplam_deger else "N/A",
    )
    kutu[3].metric("Gerçekleşen K/Z ($)", f"${ozet['gerceklesen_kz_usd']:,.2f}")
    kutu[4].metric(gelir_etiketi, f"${ozet['gelir_usd']:,.2f}")


def silme_bolumu(df, dosya, anahtar):
    st.subheader("📜 Tüm İşlem Kayıtları")
    duzenlenebilir = df.copy()
    duzenlenebilir.insert(0, "Sil", False)
    duzenlenmis = st.data_editor(
        duzenlenebilir,
        column_config={"Sil": st.column_config.CheckboxColumn("Sil 🗑️", default=False)},
        disabled=[s for s in duzenlenebilir.columns if s != "Sil"],
        hide_index=True, use_container_width=True, key=anahtar,
    )
    secilenler = duzenlenmis[duzenlenmis["Sil"]]
    if not secilenler.empty and st.button(
        f"🗑️ Seçilen {len(secilenler)} kaydı kalıcı olarak sil", type="primary", key=f"{anahtar}_sil"
    ):
        kalan = duzenlenmis[~duzenlenmis["Sil"]].drop(columns=["Sil"])
        if veri_kaydet(kalan, dosya):
            st.success(f"✅ {len(secilenler)} kayıt silindi (önceki hâli yedeklendi).")
            st.rerun()


def mukerrer_mi(imza):
    return st.session_state.get("son_kayit_imzasi") == imza


def tradingview_html(ic_yapilandirma, betik, yukseklik):
    return f"""
    <div class="tradingview-widget-container" style="height:{yukseklik}px;width:100%">
      <div class="tradingview-widget-container__widget" id="tv_kutu"></div>
      <script type="text/javascript" src="{betik}" async>{ic_yapilandirma}</script>
    </div>"""


# ===========================================================================
# VERİ HAZIRLIĞI
# ===========================================================================

defter_hisse = veri_yukle(EXCEL_HISSE)
defter_kripto = veri_yukle(EXCEL_KRIPTO)

hisse_sembolleri = tuple(sorted(set(defter_hisse["Hisse"]) - {""}))
kripto_sembolleri = tuple(sorted(set(defter_kripto["Hisse"]) - {""}))

_sonek_birimleri = {pc.varsayilan_borsa_pb(s) for s in hisse_sembolleri}
gereken_birimler = (
    set(defter_hisse["Para_Birimi"]) | set(defter_kripto["Para_Birimi"])
    | {pc.KURUSLU_BIRIMLER.get(b, b).upper() for b in _sonek_birimleri}
)
kurlar = kurlari_getir(tuple(sorted(pb for pb in gereken_birimler if pb)))


def borsa_pb_getir(sembol, pozisyon=None):
    meta = sembol_meta(pc.sembol_normalize(sembol))
    return meta["borsa_pb"] or (pozisyon or {}).get("borsa_pb") or "USD"

hisse_fiyatlari = hisse_piyasa_verisi(hisse_sembolleri)
kripto_fiyatlari = kripto_piyasa_verisi(kripto_sembolleri)

ozet_hisse = pc.pozisyon_ozeti(defter_hisse, kurlar)
ozet_kripto = pc.pozisyon_ozeti(defter_kripto, kurlar)


def hisse_piyasa_saglayici(sembol, pozisyon):
    kod = pc.sembol_normalize(sembol)
    piyasa = hisse_fiyatlari.get(kod, {})
    return {
        "fiyat_usd": pc.fiyati_usd_yap(piyasa.get("fiyat"), borsa_pb_getir(sembol, pozisyon), kurlar),
        "rsi": piyasa.get("rsi"),
        "kazan": pc.kazan_sinifi(piyasa_degeri=sembol_meta(kod)["piyasa_degeri"]),
    }


def kripto_piyasa_saglayici(sembol, pozisyon):
    piyasa = kripto_fiyatlari.get(sembol, {})
    return {
        "fiyat_usd": piyasa.get("fiyat"),
        "rsi": kripto_rsi(sembol) if piyasa else None,
        "kazan": pc.kazan_sinifi(kripto_mu=True, sembol=sembol),
    }


# ===========================================================================
# ÜST BİLGİ
# ===========================================================================

st.title("🌍 Global Ajan Portföy Paneli")

if kurlar.get("USD") is None:
    st.warning(
        "⚠️ **Canlı dolar kuru çekilemedi.** TL/EUR/GBP cinsinden işlemler dolara "
        "çevrilemiyor; ilgili satırlar hesaba katılmıyor. Dolar cinsinden işlemler "
        "etkilenmez ve kaydedilebilir."
    )

st.markdown("### 💱 Canlı Döviz Kurları & Küresel Endeksler")
ust_kutu = st.columns(3)
for kutu, sembol in zip(ust_kutu, ["FX_IDC:USDTRY", "FOREXCOM:SPXUSD", "FOREXCOM:NSXUSD"]):
    with kutu:
        components.html(
            tradingview_html(
                json.dumps({"symbol": sembol, "width": "100%", "height": 210, "locale": "tr",
                            "dateRange": "1M", "colorTheme": "dark", "isTransparent": False}),
                "https://s3.tradingview.com/external-embedding/embed-widget-mini-symbol-overview.js",
                220,
            ),
            height=220,
        )

tablo_hisse, hisse_maliyet, hisse_deger, hisse_fiyatsiz = pozisyon_tablosu(
    ozet_hisse, hisse_piyasa_saglayici, kurlar
)
tablo_kripto, kripto_maliyet, kripto_deger, kripto_fiyatsiz = pozisyon_tablosu(
    ozet_kripto, kripto_piyasa_saglayici, kurlar, kripto_mu=True
)
toplam_maliyet = hisse_maliyet + kripto_maliyet
toplam_deger = hisse_deger + kripto_deger

if toplam_maliyet:
    st.markdown("### 💼 Toplam Portföy (Hisse + Kripto)")
    birlesik = st.columns(4)
    birlesik[0].metric("Toplam Maliyet ($)", f"${toplam_maliyet:,.2f}")
    birlesik[1].metric("Güncel Değer ($)", f"${toplam_deger:,.2f}" if toplam_deger else "N/A")
    birlesik[2].metric(
        "Açık K/Z ($)", f"${toplam_deger - toplam_maliyet:,.2f}" if toplam_deger else "N/A",
        delta=f"{(toplam_deger / toplam_maliyet - 1) * 100:,.2f}%" if toplam_deger and toplam_maliyet else None,
    )
    birlesik[3].metric(
        "Gerçekleşen K/Z ($)",
        f"${ozet_hisse['gerceklesen_kz_usd'] + ozet_kripto['gerceklesen_kz_usd']:,.2f}",
    )

st.markdown("---")

# ===========================================================================
# YAN MENÜ
# ===========================================================================

st.sidebar.header("⚙️ Portföy & Veri Yönetimi")
indirme = st.sidebar.columns(2)
for kutu, dosya, etiket in [(indirme[0], EXCEL_HISSE, "Hisse"), (indirme[1], EXCEL_KRIPTO, "Kripto")]:
    if os.path.exists(dosya):
        with kutu, open(dosya, "rb") as akis:
            st.download_button(f"📥 {etiket} Excel", akis, file_name=dosya)

st.sidebar.markdown("---")
st.sidebar.subheader("🛡️ 3 Kazanlı Sermaye Stratejisi")
st.sidebar.info("**A Kazanı (%50):** Dev şirketler & BTC/ETH")
st.sidebar.success("**B Kazanı (%40):** Büyüme şirketleri")
st.sidebar.warning("**C Kazanı (%10):** Agresif hisseler & altcoinler")
st.sidebar.caption("Sınıflandırma kayıt anında dondurulmaz; her açılışta güncel piyasa değerinden hesaplanır.")

st.sidebar.markdown("---")
st.sidebar.header("📜 İşlem Geçmişi & Filtreler")
gecmis_turu = st.sidebar.radio("Geçmiş Türü:", ["Hisse İşlemleri", "Kripto İşlemleri"], horizontal=True)
gecmis_defteri = defter_hisse if "Hisse" in gecmis_turu else defter_kripto

if not gecmis_defteri.empty:
    metin_filtresi = st.sidebar.text_input("🔍 Varlık Ara:", "").strip().upper()
    tip_filtresi = st.sidebar.selectbox(
        "🏷️ İşlem Tipi:", ["Tümü", "Sadece AL 🟢", "Sadece SAT 🔴", "Sadece Temettü/Staking 💰"]
    )
    suzulmus = gecmis_defteri
    if metin_filtresi:
        suzulmus = suzulmus[suzulmus["Hisse"].str.contains(metin_filtresi, regex=False, na=False)]
    if tip_filtresi != "Tümü":
        hedef = {"Sadece AL 🟢": pc.AL, "Sadece SAT 🔴": pc.SAT, "Sadece Temettü/Staking 💰": pc.GELIR}[tip_filtresi]
        suzulmus = suzulmus[suzulmus["Tip"].map(pc.islem_tipi) == hedef]

    with st.sidebar.expander(f"📂 Filtrelenmiş Kayıtlar ({len(suzulmus)})", expanded=True):
        st.dataframe(
            suzulmus.iloc[::-1][["Tarih", "Hisse", "Tip", "Fiyat", "Adet", "Para_Birimi"]],
            height=300, use_container_width=True,
        )

# ===========================================================================
# SEKMELER
# ===========================================================================

sekme1, sekme2, sekme3, sekme4, sekme5, sekme6, sekme7 = st.tabs([
    "📈 Hisse Portföyü", "🪙 Kripto Portföyü", "🤖 Grafik Ajanı",
    "⚡ Canlı Radar & Makro Takvim", "💻 Sistem & QA Ajanı", "📅 Temettü",
    "📊 İndikatörler",
])

# --- SEKME 1: HİSSE --------------------------------------------------------
with sekme1:
    st.subheader("📈 Hisse Senedi İşlem Kaydı (BIST / Nasdaq / NYSE)")
    ust = st.columns([1, 1])
    with ust[0]:
        secim = st_searchbox(hisse_ara, key="hisse_arama", placeholder="Hisse kodu (AAPL, NVDA, THYAO)...")
        secilen_hisse, secilen_borsa = secimi_coz(secim)
    with ust[1]:
        borsa_pb = "USD"
        if secilen_hisse:
            kod = pc.sembol_normalize(secilen_hisse)
            borsa_pb = sembol_meta(kod)["borsa_pb"]
            anlik = hisse_piyasa_verisi((secilen_hisse,)).get(kod, {}).get("fiyat")
            if anlik:
                st.success(f"✅ **{secilen_hisse}** | Anlık: **{anlik:,.2f} {borsa_pb}**")
            else:
                st.warning(f"⚠️ **{secilen_hisse}** için canlı fiyat yok; işlem yine de kaydedilebilir.")

    with st.form("hisse_formu", clear_on_submit=True):
        alan = st.columns(4)
        tip = alan[0].selectbox("İşlem Tipi", ["AL 🟢", "SAT 🔴", "TEMETTÜ 💰"])
        para_birimi = alan[1].selectbox("Girdiğiniz Para Birimi", ["USD ($)", "TRY (₺)", "EUR (€)", "GBP (£)"])
        fiyat = alan[2].number_input("İşlem Fiyatı / Tutar", min_value=0.0, value=None,
                                     placeholder="220.50", step=0.01, format="%.4f")
        adet = alan[3].number_input("Adet", min_value=0.0001, value=1.0, step=1.0, format="%.4f")
        onaylar = [
            st.checkbox("🛡️ Stratejime uygun."),
            st.checkbox("🧠 Duygusal değil."),
            st.checkbox("📱 Kurumda gerçekleşti."),
        ]

        if st.form_submit_button("💾 Hisse İşlemini Kaydet"):
            pb_kodu = para_birimi.split(" ")[0]
            islem_kuru = kurlar.get(pb_kodu)
            islem_usdtry = kurlar.get("USD")
            imza = (secilen_hisse, tip, fiyat, adet, pb_kodu, dt.datetime.now(TSI).strftime("%Y-%m-%d %H:%M"))

            hata = None
            if not secilen_hisse:
                hata = "Hisse kodu seçilmedi."
            elif not all(onaylar):
                hata = "Üç onay kutusunun da işaretlenmesi gerekiyor."
            elif fiyat is None or fiyat <= 0:
                hata = "Geçerli bir işlem fiyatı girin."
            elif pb_kodu != "USD" and not (islem_kuru and islem_usdtry):
                hata = f"{pb_kodu} kuru çekilemediği için bu işlem doğru kaydedilemez. Dolar cinsinden girebilirsiniz."
            elif pc.islem_tipi(tip) is pc.SAT and adet > pc.satilabilir_adet(defter_hisse, secilen_hisse) + 1e-9:
                hata = (f"Elde {pc.satilabilir_adet(defter_hisse, secilen_hisse):.4f} adet var; "
                        f"{adet:.4f} adet satılamaz.")
            elif mukerrer_mi(imza):
                hata = "Bu işlemi az önce kaydettiniz. Gerçekten tekrarlamak istiyorsanız dakikayı değiştirin."

            if hata:
                st.error(f"❌ {hata}")
            else:
                yeni = pd.DataFrame([{
                    "Tarih": imza[5], "Hisse": secilen_hisse, "Kazan": "", "Tip": tip,
                    "Fiyat": fiyat, "Adet": adet, "Toplam": fiyat * adet,
                    "Para_Birimi": pb_kodu,
                    "Islem_Kuru": islem_kuru if pb_kodu != "USD" else islem_usdtry,
                    "Islem_USDTRY": islem_usdtry,
                    "Borsa_PB": borsa_pb, "Borsa": secilen_borsa,
                }])
                if veri_kaydet(pd.concat([defter_hisse, yeni], ignore_index=True), EXCEL_HISSE):
                    st.session_state["son_kayit_imzasi"] = imza
                    st.success("✅ İşlem, o anki kur birlikte kaydedildi.")
                    st.rerun()

    if not defter_hisse.empty:
        st.markdown("---")
        st.subheader("📊 Açık Pozisyonlar")
        tablo = tablo_hisse
        metrik_satiri(ozet_hisse, hisse_maliyet, hisse_deger, "Toplam Temettü ($)")
        ozet_uyarilari(ozet_hisse, hisse_fiyatsiz)

        if not tablo.empty:
            grafik = st.columns([2, 1])
            grafik[0].dataframe(tablo, use_container_width=True)
            dagilim = tablo[tablo["Güncel Değer ($)"] != "N/A"].copy()
            if not dagilim.empty and dagilim["Kazan"].str.strip().any():
                dagilim["deger"] = (
                    dagilim["Güncel Değer ($)"].str.replace(r"[$,]", "", regex=True).astype(float)
                )
                pasta = px.pie(
                    dagilim[dagilim["Kazan"] != ""], names="Kazan", values="deger", hole=0.4,
                    title="🎨 3 Kazan Dağılımı", color_discrete_sequence=px.colors.qualitative.Pastel,
                )
                pasta.update_layout(margin=dict(t=40, b=0, l=0, r=0), height=280)
                grafik[1].plotly_chart(pasta, use_container_width=True)

        st.markdown("---")
        silme_bolumu(defter_hisse, EXCEL_HISSE, "duzenleyici_hisse")

# --- SEKME 2: KRİPTO -------------------------------------------------------
with sekme2:
    st.subheader("🪙 Kripto Varlık İşlem Kaydı")
    ust_k = st.columns([1, 1])
    with ust_k[0]:
        secilen_kripto = (st_searchbox(kripto_ara, key="kripto_arama",
                                       placeholder="Kripto ara (BTC, ETH, SOL)...") or "").strip().upper()
    with ust_k[1]:
        anlik_kripto = kripto_piyasa_verisi((secilen_kripto,)).get(secilen_kripto, {}).get("fiyat") if secilen_kripto else None
        if anlik_kripto:
            st.success(f"⚡ **{secilen_kripto}/USDT:** **${anlik_kripto:,.4f}**")
        elif secilen_kripto:
            st.warning(f"⚠️ **{secilen_kripto}** için Binance fiyatı alınamadı.")

    with st.form("kripto_formu", clear_on_submit=True):
        alan_k = st.columns(3)
        k_tip = alan_k[0].selectbox("İşlem Tipi", ["AL 🟢", "SAT 🔴", "STAKING 💰"])
        k_fiyat = alan_k[1].number_input("Fiyat ($ USDT)", min_value=0.0, value=None,
                                         placeholder=f"{anlik_kripto:,.4f}" if anlik_kripto else "0.0000",
                                         format="%.4f")
        k_adet = alan_k[2].number_input("Adet", min_value=0.000001, value=1.0, step=0.1, format="%.6f")
        k_onaylar = [
            st.checkbox("🛡️ Stratejime uygun.", key="k_o1"),
            st.checkbox("🧠 Duygusal değil.", key="k_o2"),
            st.checkbox("📱 Borsada gerçekleşti.", key="k_o3"),
        ]

        if st.form_submit_button("💾 Kripto İşlemini Kaydet"):
            imza_k = (secilen_kripto, k_tip, k_fiyat, k_adet, "USD", dt.datetime.now(TSI).strftime("%Y-%m-%d %H:%M"))
            hata_k = None
            if not secilen_kripto:
                hata_k = "Kripto varlık seçilmedi."
            elif not all(k_onaylar):
                hata_k = "Üç onay kutusunun da işaretlenmesi gerekiyor."
            elif k_fiyat is None or k_fiyat <= 0:
                hata_k = "Geçerli bir fiyat girin."
            elif pc.islem_tipi(k_tip) is pc.SAT and k_adet > pc.satilabilir_adet(defter_kripto, secilen_kripto) + 1e-9:
                hata_k = (f"Elde {pc.satilabilir_adet(defter_kripto, secilen_kripto):.6f} adet var; "
                          f"{k_adet:.6f} adet satılamaz.")
            elif mukerrer_mi(imza_k):
                hata_k = "Bu işlemi az önce kaydettiniz."

            if hata_k:
                st.error(f"❌ {hata_k}")
            else:
                yeni_k = pd.DataFrame([{
                    "Tarih": imza_k[5], "Hisse": secilen_kripto, "Kazan": "", "Tip": k_tip,
                    "Fiyat": k_fiyat, "Adet": k_adet, "Toplam": k_fiyat * k_adet,
                    "Para_Birimi": "USD",
                    "Islem_Kuru": kurlar.get("USD"), "Islem_USDTRY": kurlar.get("USD"),
                    "Borsa_PB": "USD", "Borsa": "BINANCE",
                }])
                if veri_kaydet(pd.concat([defter_kripto, yeni_k], ignore_index=True), EXCEL_KRIPTO):
                    st.session_state["son_kayit_imzasi"] = imza_k
                    st.success("✅ Kripto işlemi kaydedildi.")
                    st.rerun()

    if not defter_kripto.empty:
        st.markdown("---")
        st.subheader("📊 Açık Kripto Pozisyonları")
        metrik_satiri(ozet_kripto, kripto_maliyet, kripto_deger, "Toplam Staking ($)")
        ozet_uyarilari(ozet_kripto, kripto_fiyatsiz)
        if not tablo_kripto.empty:
            st.dataframe(tablo_kripto, use_container_width=True)

        st.markdown("---")
        silme_bolumu(defter_kripto, EXCEL_KRIPTO, "duzenleyici_kripto")

# --- SEKME 3: GRAFİK -------------------------------------------------------
with sekme3:
    st.subheader("🤖 TradingView Grafik Ajanı")
    grafik_ust = st.columns([2, 1])
    with grafik_ust[0]:
        grafik_secim = st_searchbox(hisse_ara, key="grafik_arama", placeholder="Grafiği açılacak varlık...")
        grafik_sembol, grafik_borsa = secimi_coz(grafik_secim)
    with grafik_ust[1]:
        varlik_turu = st.radio("Varlık Türü:", ["Hisse (BIST/US)", "Kripto (Binance)"], horizontal=True)

    if st.button("🔍 Grafiği Yükle") and grafik_sembol:
        tv_kodu = pc.tv_sembol(grafik_sembol, grafik_borsa, kripto_mu="Kripto" in varlik_turu)
        st.caption(f"TradingView sembolü: `{tv_kodu}`")
        components.html(f"""
        <div class="tradingview-widget-container" style="height:600px;width:100%">
          <div id="tv_grafik" style="height:560px;width:100%"></div>
          <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
          <script type="text/javascript">
            new TradingView.widget({json.dumps({
                "autosize": True, "symbol": tv_kodu, "interval": "D",
                "timezone": "Europe/Istanbul", "theme": "dark", "locale": "tr",
                "container_id": "tv_grafik",
            })});
          </script>
        </div>""", height=620)

# --- SEKME 4: RADAR --------------------------------------------------------
with sekme4:
    st.subheader("⚡ Canlı Radar & Küresel Makro Takvim")
    radar_kutu = st.columns([1, 1])

    with radar_kutu[0]:
        st.markdown("**📋 Portföydeki Varlıkların Canlı Durumu**")
        radar = []
        for sembol in hisse_sembolleri:
            kod = pc.sembol_normalize(sembol)
            piyasa = hisse_fiyatlari.get(kod, {})
            birim = pc.varsayilan_borsa_pb(sembol)
            rsi = piyasa.get("rsi")
            radar.append({
                "Varlık": sembol, "Tür": "Hisse",
                "Son Fiyat": f"{piyasa['fiyat']:,.2f}" if piyasa.get("fiyat") else "N/A",
                "Para Birimi": birim,
                "Günlük Değişim": f"%{piyasa['degisim']:+.2f}" if piyasa.get("degisim") is not None else "N/A",
                "RSI(14)": f"{rsi:.1f}" if rsi is not None else "N/A",
                "RSI Durumu": ind.rsi_durum(rsi),
            })
        for sembol in kripto_sembolleri:
            piyasa = kripto_fiyatlari.get(sembol, {})
            rsi = kripto_rsi(sembol)
            radar.append({
                "Varlık": sembol, "Tür": "Kripto",
                "Son Fiyat": f"{piyasa['fiyat']:,.4f}" if piyasa.get("fiyat") else "N/A",
                "Para Birimi": "USDT",
                "Günlük Değişim": f"%{piyasa['degisim']:+.2f}" if piyasa.get("degisim") is not None else "N/A",
                "RSI(14)": f"{rsi:.1f}" if rsi is not None else "N/A",
                "RSI Durumu": ind.rsi_durum(rsi),
            })
        if radar:
            st.dataframe(pd.DataFrame(radar), use_container_width=True, hide_index=True)
        else:
            st.info("Portföyünüz henüz boş.")

    with radar_kutu[1]:
        st.markdown("**🏛️ Küresel Ekonomik & FED Makro Takvimi**")
        components.html(
            tradingview_html(
                json.dumps({"colorTheme": "dark", "isTransparent": False, "width": "100%",
                            "height": 450, "locale": "tr", "importanceFilter": "0,1",
                            "currencyFilter": "USD,EUR,TRY"}),
                "https://s3.tradingview.com/external-embedding/embed-widget-events.js",
                460,
            ),
            height=460,
        )

# --- SEKME 5: SİSTEM & QA --------------------------------------------------
with sekme5:
    st.subheader("💻 Portföy Asistanı & Sistem Durumu")

    st.markdown("### 🤖 Portföy Asistanı")
    st.caption(
        "Portföyünüz hakkında serbest soru sorun. Asistan defterinizi ve canlı "
        "fiyatları okuyabilir; **yazamaz** — işlem giremez, kayıt değiştiremez."
    )

    soru = st.text_input(
        "Sorunuz:",
        placeholder="Örn: Portföyümde ne durumdayım? En çok hangi varlıkta zarardayım?",
        key="asistan_sorusu",
    )
    if st.button("💬 Sor", key="asistan_sor") and soru.strip():
        with st.spinner("Asistan defterinizi okuyor..."):
            import ajan
            yanit = ajan.sor(soru)

        if yanit["hata"]:
            st.error(yanit["hata"])
        else:
            st.markdown(yanit["cevap"])
            st.caption(
                f"{yanit['girdi_token']:,} girdi + {yanit['cikti_token']:,} çıktı token"
                f" · kullanılan araçlar: {', '.join(yanit['arac_cagrilari']) or 'yok'}"
            )

    with st.expander("ℹ️ Asistan hakkında — kurulum, gizlilik, maliyet"):
        st.markdown(
            "**Bu bölüm ücretlidir.** Asistan, Claude aboneliğinden değil, ayrı bir "
            "**Claude Console (API)** hesabından çalışır ve kullandıkça ücretlendirilir. "
            "Ödeme yapmak istemiyorsanız bu bölümü kullanmayın; panelin diğer "
            "sekmeleri hiçbir ücret gerektirmez.\n\n"
            "**Kurulum.** platform.claude.com üzerinde bir Console hesabı açıp kredi "
            "yüklemeniz, sonra terminalde bir kez `ant auth login` çalıştırmanız gerekir. "
            "Alternatif olarak `ANTHROPIC_API_KEY` ortam değişkeni tanımlanabilir.\n\n"
            "**Maliyet.** Claude Opus 5 için milyon girdi token'ı 5 $, milyon çıktı "
            "token'ı 25 $. Bu asistanda soru başına kabaca 0,10–0,15 $. `ajan.py` "
            "içindeki `ETKI` sabitini düşürmek veya `MODEL`'i `claude-sonnet-5` "
            "yapmak maliyeti belirgin biçimde azaltır.\n\n"
            "**Gizlilik.** Soru sorduğunuzda portföy verileriniz (pozisyonlar, "
            "maliyetler, kâr/zarar) Anthropic API'sine gönderilir. Soru sormadığınız "
            "sürece hiçbir veri dışarı çıkmaz."
        )

    st.markdown("---")
    st.markdown("### 🔌 Servis ve Dosya Denetimi")
    if st.button("🔍 Kontrol et", key="sistem_kontrol"):
        st.write(f"{'✅' if os.path.exists(EXCEL_HISSE) else 'ℹ️'} **Hisse defteri:** `{EXCEL_HISSE}`")
        st.write(f"{'✅' if os.path.exists(EXCEL_KRIPTO) else 'ℹ️'} **Kripto defteri:** `{EXCEL_KRIPTO}`")
        baslangic = time.monotonic()
        try:
            r = requests.get(f"{BINANCE}/api/v3/ping", timeout=3)
            gecikme = (time.monotonic() - baslangic) * 1000
            st.write(f"{'✅' if r.ok else '⚠️'} **Binance API:** HTTP {r.status_code} · `{gecikme:.0f} ms`")
        except Exception as e:
            st.write(f"❌ **Binance API:** erişilemedi — {e}")

    st.markdown("---")
    st.markdown("### 📊 Gerçek Zamanlı Süreç & Sistem Durumu")
    qa_kutu = st.columns(2)
    with qa_kutu[0]:
        st.markdown("**🗂️ Defter Durumu**")
        for dosya, defter in [(EXCEL_HISSE, defter_hisse), (EXCEL_KRIPTO, defter_kripto)]:
            hata = st.session_state.get("yukleme_hatalari", {}).get(dosya)
            yedek_sayisi = len(glob.glob(f"{dosya}.*.bak"))
            if hata:
                st.write(f"❌ **{dosya}:** okunamıyor — yazma kilitli")
            elif os.path.exists(dosya):
                st.write(f"✅ **{dosya}:** {len(defter)} kayıt · {yedek_sayisi} yedek")
            else:
                st.write(f"ℹ️ **{dosya}:** henüz oluşturulmadı")

    with qa_kutu[1]:
        st.markdown("**📊 Süreç Kaynak Kullanımı**")
        try:
            import psutil
            surec = psutil.Process(os.getpid())
            bellek = surec.memory_info().rss / (1024 * 1024)
            st.metric("Süreç belleği (RSS)", f"{bellek:,.1f} MB")
        except ImportError:
            st.info("psutil kurulu değil; bellek ölçümü atlandı.")

        st.write(f"Sunucu saati (TSİ): `{dt.datetime.now(TSI).strftime('%Y-%m-%d %H:%M:%S')}`")

    st.markdown("---")
    st.warning(
        "**Bilinen sınır — kalıcılık:** Defterler sunucudaki Excel dosyalarında tutulur. "
        "Streamlit Cloud'da dosya sistemi geçicidir (yeniden dağıtımda silinir) ve tüm "
        "ziyaretçiler aynı defteri paylaşır. Kişisel veya çok kullanıcılı kullanım için "
        "kimlik doğrulamalı bir veritabanına geçilmelidir. Excel'i düzenli olarak yan menüden indirin."
    )

# --- SEKME 6: TEMETTÜ ------------------------------------------------------
with sekme6:
    st.subheader("📅 Temettü")
    temettu_kutu = st.columns([1, 1])

    with temettu_kutu[0]:
        st.markdown("**🔍 Hisse Temettü Sorgula**")
        t_secim = st_searchbox(hisse_ara, key="temettu_arama", placeholder="Hisse kodu (EREGL, NVO, KO)...")
        t_sembol, _ = secimi_coz(t_secim)
        if t_sembol:
            kod = pc.sembol_normalize(t_sembol)
            bilgi = temettu_bilgisi(kod)
            if not bilgi:
                st.error("Temettü verisi çekilemedi.")
            else:
                oran, kaynak = pc.temettu_verimi(
                    bilgi["yillik_temettu"], bilgi["fiyat"], bilgi["ham_yield"]
                )
                birim = bilgi.get("para_birimi", "USD")
                yillik = bilgi["yillik_temettu"]
                yillik_metni = f"{yillik:,.4f} {birim}" if yillik else "—"
                st.write(f"**Sembol:** {kod} · **Sektör:** {bilgi.get('sektor') or '—'}")
                st.write(f"**Yıllık temettü:** {yillik_metni}")
                if kaynak == "hesaplandi":
                    st.write(f"**Temettü verimi:** %{oran * 100:,.2f}  \n*(yıllık temettü ÷ güncel fiyat)*")
                elif kaynak == "belirsiz":
                    st.warning(
                        f"**Temettü verimi hesaplanamadı.** Sağlayıcıdan yalnızca ham değer geldi: "
                        f"`{bilgi['ham_yield']}`. Bu değerin kesir mi yüzde mi olduğu sürüme göre "
                        "değiştiği için ölçeklenmedi — yorumu size bırakılıyor."
                    )
                else:
                    st.info("Bu hisse için temettü kaydı bulunmadı.")

                ex_tarih = bilgi.get("ex_tarih")
                if ex_tarih:
                    st.write(
                        "**Hak kullanım (ex-date):** "
                        + dt.datetime.fromtimestamp(ex_tarih, tz=dt.timezone.utc).strftime("%Y-%m-%d")
                        + "  *(UTC)*"
                    )

    with temettu_kutu[1]:
        st.markdown("**💼 Kaydedilmiş Temettü / Staking Gelirleri**")
        gelirler = pd.concat([defter_hisse, defter_kripto], ignore_index=True)
        gelirler = gelirler[gelirler["Tip"].map(pc.islem_tipi) == pc.GELIR]
        if gelirler.empty:
            st.info("Henüz temettü veya staking kaydı girilmemiş.")
        else:
            st.dataframe(
                gelirler[["Tarih", "Hisse", "Tip", "Fiyat", "Adet", "Toplam", "Para_Birimi"]].iloc[::-1],
                use_container_width=True, hide_index=True,
            )
            st.metric(
                "Toplam gelir ($)",
                f"${ozet_hisse['gelir_usd'] + ozet_kripto['gelir_usd']:,.2f}",
            )

st.markdown("---")
st.caption(
    "Bu panel bir yatırım tavsiyesi aracı değildir. Fiyatlar gecikmeli olabilir; "
    "kayıtlarınızı düzenli olarak yedekleyin."
)

# --- SEKME 7: İNDİKATÖRLER -------------------------------------------------
@st.cache_data(ttl=900, show_spinner=False)
def gosterge_verisi(hisseler, kriptolar):
    """Gösterge paketi. 15 dk önbellek: günlük mumla çalışır, sık yenilemeye
    gerek yoktur ve her yenileme 1 yıllık geçmiş indirmek demektir."""
    return _gosterge_paketi(list(hisseler), list(kriptolar))


def _sayi(deger, basamak=2):
    return "N/A" if deger is None else f"{deger:,.{basamak}f}"


# "yok" = kesişim aranmış, bulunamamış. None = veri yetersiz, aranamamış.
KESISIM_ETIKET = {"yukari": "▲ yukarı", "asagi": "▼ aşağı",
                  "yok": "—", None: "veri yok"}
SINYAL_RENK = {"AL yönlü": "🟢", "SAT yönlü": "🔴", "Nötr": "⚪", "Veri yok": "⚫"}

with sekme7:
    st.subheader("📊 Teknik İndikatörler")
    st.caption(
        "RSI(14) Wilder yöntemiyle, MACD(12/26/9) ve Bollinger(20, 2σ) günlük "
        "kapanışlardan hesaplanır. Hesaplanamayan gösterge boş bırakılır, "
        "tahmin edilmez."
    )

    izleme_listesi = izleme.liste_oku()
    izleme_hisse, izleme_kripto = izleme.turlere_ayir(izleme_listesi)
    kural_ayarlari = izleme.kural_ayarlari_oku()
    etkin_kurallar = izleme.etkin_kurallar()

    if not etkin_kurallar:
        st.warning(
            "Hiç etkin kural yok — sinyal sütunu boş kalacak. Aşağıdaki "
            "**Kendi kuralların** bölümünden kural ekleyin ya da varsayılan "
            "kural setini yeniden açın."
        )

    kapsam = st.multiselect(
        "Kapsam", ["Portföyüm", "İzleme listem"], default=["Portföyüm", "İzleme listem"],
        key="ind_kapsam",
    )
    secili_hisse, secili_kripto = [], []
    if "Portföyüm" in kapsam:
        secili_hisse += list(hisse_sembolleri)
        secili_kripto += list(kripto_sembolleri)
    if "İzleme listem" in kapsam:
        secili_hisse += [s for s in izleme_hisse if s not in secili_hisse]
        secili_kripto += [s for s in izleme_kripto if s not in secili_kripto]

    if not secili_hisse and not secili_kripto:
        st.info(
            "Gösterilecek varlık yok. Portföyünüze işlem girin ya da aşağıdaki "
            "**İzleme listesi** bölümünden sembol ekleyin."
        )
        paket = {}
    else:
        with st.spinner("Göstergeler hesaplanıyor (1 yıllık geçmiş indiriliyor)..."):
            paket = gosterge_verisi(tuple(sorted(secili_hisse)), tuple(sorted(secili_kripto)))

        eksik = [s for s in secili_hisse + secili_kripto if s not in paket]
        if eksik:
            st.warning(
                "Şu varlıkların geçmiş verisi çekilemedi, tabloda yer almıyorlar: "
                + ", ".join(sorted(eksik))
            )

    # --- Tetiklenen alarmlar ------------------------------------------------
    if paket:
        tetiklenen = izleme.alarmlari_degerlendir(paket)
        if tetiklenen:
            st.markdown("### 🔔 Tetiklenen alarmlar")
            for olay in tetiklenen:
                simge = "🟢" if olay["yon"] == "AL" else "🔴"
                deger = olay["deger"]
                deger_metni = deger if isinstance(deger, str) else _sayi(deger)
                st.warning(f"{simge} **{olay['sembol']}** — {olay['kural_adi']} (değer: {deger_metni})")

    # --- Ana tablo ----------------------------------------------------------
    if paket:
        satirlar = []
        for sembol in sorted(paket):
            olcu = paket[sembol]
            ozet = ind.sinyal_ozeti(olcu, etkin_kurallar)
            satirlar.append({
                "Varlık": sembol,
                "Fiyat": _sayi(olcu["fiyat"]),
                "RSI(14)": _sayi(olcu["rsi"], 1),
                "RSI Durumu": ind.rsi_durum(olcu["rsi"]),
                "MACD Hist.": _sayi(olcu["macd_histogram"], 3),
                "MACD Kesişim": KESISIM_ETIKET.get(olcu["macd_kesisim"], "—"),
                "SMA50": _sayi(olcu["sma50"]),
                "SMA200": _sayi(olcu["sma200"]),
                "MA Kesişim": KESISIM_ETIKET.get(olcu["ma_kesisim"], "—"),
                "Bollinger %B": _sayi(olcu["bb_yuzde_b"], 2),
                "Sinyal": f"{SINYAL_RENK.get(ozet['etiket'], '')} {ozet['etiket']}",
                "Puan": ozet["puan"],
            })
        st.dataframe(pd.DataFrame(satirlar), use_container_width=True, hide_index=True)

        st.caption(
            f"**Puan** = tetiklenen AL kuralı sayısı − tetiklenen SAT kuralı sayısı "
            f"({len(etkin_kurallar)} etkin kural üzerinden). Kuralların ağırlığı "
            "yoktur ve hiçbiri diğerinden değerli sayılmaz; bu bir tavsiye değil, "
            "sizin tanımladığınız kuralların sayımıdır."
        )

        with st.expander("🔍 Varlık detayı — hangi kurallar tetiklendi?"):
            secim = st.selectbox("Varlık", sorted(paket), key="ind_detay")
            olcu = paket[secim]
            ozet = ind.sinyal_ozeti(olcu, etkin_kurallar)
            sutun = st.columns(3)
            sutun[0].metric("RSI(14)", _sayi(olcu["rsi"], 1), ind.rsi_durum(olcu["rsi"]))
            sutun[1].metric("Fiyat", _sayi(olcu["fiyat"]))
            sutun[2].metric("Bar sayısı", olcu["bar_sayisi"])
            if ozet["al"]:
                st.success("🟢 AL yönlü: " + " · ".join(ozet["al"]))
            if ozet["sat"]:
                st.error("🔴 SAT yönlü: " + " · ".join(ozet["sat"]))
            if not ozet["al"] and not ozet["sat"]:
                st.info("Hiçbir kural tetiklenmedi.")
            if ozet["olculemedi"]:
                st.caption("Veri yetersiz olduğu için değerlendirilemeyen kurallar: "
                           + ", ".join(ozet["olculemedi"]))

    st.markdown("---")

    # --- Serbest sembol sorgusu --------------------------------------------
    with st.expander("🔎 Serbest sembol sorgusu"):
        st.caption("Portföyünde ve izleme listende olmayan bir sembole tek seferlik bakış.")
        sorgu_sutun = st.columns([2, 1, 1])
        sorgu_sembol = sorgu_sutun[0].text_input("Sembol", key="ind_sorgu_sembol",
                                                 placeholder="AAPL, THYAO, BTC...")
        sorgu_tur = sorgu_sutun[1].selectbox("Tür", ["hisse", "kripto"], key="ind_sorgu_tur")
        if sorgu_sutun[2].button("Sorgula", key="ind_sorgula") and sorgu_sembol.strip():
            hedef = sorgu_sembol.strip().upper()
            with st.spinner(f"{hedef} göstergeleri hesaplanıyor..."):
                tekil = gosterge_verisi(
                    (hedef,) if sorgu_tur == "hisse" else (),
                    (hedef,) if sorgu_tur == "kripto" else (),
                )
            if hedef not in tekil:
                st.error(f"{hedef} için geçmiş veri çekilemedi. Sembol yanlış olabilir.")
            else:
                olcu = tekil[hedef]
                ozet = ind.sinyal_ozeti(olcu, etkin_kurallar)
                st.markdown(f"**{hedef}** — {SINYAL_RENK.get(ozet['etiket'], '')} {ozet['etiket']}")
                st.dataframe(pd.DataFrame([{
                    "Fiyat": _sayi(olcu["fiyat"]), "RSI(14)": _sayi(olcu["rsi"], 1),
                    "MACD Hist.": _sayi(olcu["macd_histogram"], 3),
                    "SMA50": _sayi(olcu["sma50"]), "SMA200": _sayi(olcu["sma200"]),
                    "Bollinger %B": _sayi(olcu["bb_yuzde_b"], 2),
                }]), use_container_width=True, hide_index=True)

    # --- İzleme listesi yönetimi -------------------------------------------
    with st.expander(f"⭐ İzleme listesi ({len(izleme_listesi)} sembol)"):
        st.caption("Elinde olmayan ama takip ettiğin semboller. Deftere ve portföy "
                   "değerine karışmaz.")
        ekle_sutun = st.columns([2, 1, 1])
        yeni_sembol = ekle_sutun[0].text_input("Sembol", key="izleme_yeni",
                                               placeholder="NVDA, ASELS, SOL...")
        yeni_tur = ekle_sutun[1].selectbox("Tür", ["hisse", "kripto"], key="izleme_tur")
        if ekle_sutun[2].button("➕ Ekle", key="izleme_ekle"):
            sorun = izleme.sembol_ekle(yeni_sembol, yeni_tur)
            if sorun:
                st.error(sorun)
            else:
                st.success(f"{yeni_sembol.strip().upper()} eklendi.")
                st.rerun()

        st.markdown("**Toplu ekle**")
        toplu_sutun = st.columns([3, 1, 1])
        toplu_metin = toplu_sutun[0].text_area(
            "Semboller", key="izleme_toplu", height=68,
            placeholder="AAPL, MSFT, NVDA — virgül, boşluk veya alt alta",
        )
        toplu_tur = toplu_sutun[1].selectbox("Tür", ["hisse", "kripto"], key="izleme_toplu_tur")
        if toplu_sutun[2].button("➕ Hepsini ekle", key="izleme_toplu_ekle"):
            sonuc = izleme.sembol_toplu_ekle(toplu_metin, toplu_tur)
            if sonuc["eklenen"]:
                st.success(f"Eklendi: {', '.join(sonuc['eklenen'])}")
            for sembol, sebep in sonuc["atlanan"].items():
                st.warning(f"{sembol} atlandı — {sebep}")
            if sonuc["eklenen"]:
                st.rerun()

        st.markdown("---")
        if izleme_listesi:
            for kayit in izleme_listesi:
                satir = st.columns([3, 1])
                satir[0].write(f"**{kayit['sembol']}** · {kayit['tur']}")
                if satir[1].button("Sil", key=f"izleme_sil_{kayit['sembol']}"):
                    izleme.sembol_sil(kayit["sembol"])
                    st.rerun()
        else:
            st.info("İzleme listen boş.")

    # --- Alarm yönetimi -----------------------------------------------------
    alarmlar = izleme.alarm_oku()
    with st.expander(f"🔔 Alarmlar ({len(alarmlar)} tanımlı)"):
        st.caption("Bir varlık senin seçtiğin koşula geldiğinde bu sekmenin üstünde "
                   "uyarı çıkar. Panel kapalıyken alarm çalışmaz.")
        tum_semboller = sorted(set(list(hisse_sembolleri) + list(kripto_sembolleri)
                                   + [k["sembol"] for k in izleme_listesi]))
        if not tum_semboller:
            st.info("Önce portföyüne işlem gir veya izleme listene sembol ekle.")
        else:
            alarm_sutun = st.columns([1, 2, 1])
            alarm_sembol = alarm_sutun[0].selectbox("Varlık", tum_semboller, key="alarm_sembol")
            kural_adlari = [k["ad"] for k in etkin_kurallar]
            if not kural_adlari:
                alarm_sutun[1].info("Önce kural tanımlayın.")
                alarm_kural_adi = None
            else:
                alarm_kural_adi = alarm_sutun[1].selectbox("Koşul", kural_adlari, key="alarm_kural")
            if alarm_kural_adi and alarm_sutun[2].button("➕ Alarm kur", key="alarm_ekle"):
                kural = next(k for k in etkin_kurallar if k["ad"] == alarm_kural_adi)
                sorun = izleme.alarm_ekle(alarm_sembol, kural)
                if sorun:
                    st.error(sorun)
                else:
                    st.success(f"{alarm_sembol} için alarm kuruldu.")
                    st.rerun()

        if tum_semboller and etkin_kurallar:
            st.markdown("**Toplu kurulum**")
            hazir_sutun = st.columns([3, 2])
            hazir_kurallar = hazir_sutun[0].multiselect(
                "Kurulacak koşullar", [k["ad"] for k in etkin_kurallar],
                default=[k["ad"] for k in etkin_kurallar
                         if k["gosterge"] == "rsi"],
                key="alarm_toplu_kural",
            )
            hedef_secim = hazir_sutun[1].selectbox(
                "Hangi varlıklara?",
                ["Portföyümdekiler", "İzleme listem", "Hepsi"],
                key="alarm_toplu_hedef",
            )
            if hedef_secim == "Portföyümdekiler":
                hedefler = sorted(set(list(hisse_sembolleri) + list(kripto_sembolleri)))
            elif hedef_secim == "İzleme listem":
                hedefler = sorted(k["sembol"] for k in izleme_listesi)
            else:
                hedefler = tum_semboller

            st.caption(f"{len(hedefler)} varlık × {len(hazir_kurallar)} koşul = "
                       f"{len(hedefler) * len(hazir_kurallar)} alarm")
            if st.button("🔔 Toplu alarm kur", key="alarm_toplu_dugme"):
                if not hedefler or not hazir_kurallar:
                    st.error("En az bir varlık ve bir koşul seçin.")
                else:
                    secili = [k for k in etkin_kurallar if k["ad"] in hazir_kurallar]
                    sonuc = izleme.alarm_toplu_ekle(hedefler, secili)
                    if sonuc["eklenen"]:
                        st.success(f"{sonuc['eklenen']} alarm kuruldu.")
                    if sonuc["atlanan"]:
                        st.info(f"{sonuc['atlanan']} alarm zaten vardı, atlandı.")
                    if sonuc["eklenen"]:
                        st.rerun()
            st.markdown("---")

        if alarmlar:
            st.markdown("**Tanımlı alarmlar**")
            for alarm in alarmlar:
                satir = st.columns([2, 3, 2, 1, 1])
                satir[0].write(f"**{alarm['sembol']}**")
                satir[1].write(alarm["kural"]["ad"])
                satir[2].caption(f"Son tetik: {alarm.get('son_tetik') or '—'}")
                etiket = "⏸️" if alarm.get("aktif", True) else "▶️"
                if satir[3].button(etiket, key=f"alarm_durum_{alarm['id']}"):
                    izleme.alarm_durum_degistir(alarm["id"], not alarm.get("aktif", True))
                    st.rerun()
                if satir[4].button("🗑️", key=f"alarm_sil_{alarm['id']}"):
                    izleme.alarm_sil(alarm["id"])
                    st.rerun()

    # --- Kendi kuralların ---------------------------------------------------
    kendi_kurallar = kural_ayarlari["kurallar"]
    with st.expander(f"🧮 Kendi kuralların ({len(kendi_kurallar)} tanımlı)"):
        st.caption(
            "Bir gösterge, bir karşılaştırma ve bir eşik seç; kural hem sinyal "
            "tablosunda hem alarm menüsünde belirir."
        )

        varsayilan_acik = st.checkbox(
            "Varsayılan 8 kuralı da uygula",
            value=kural_ayarlari["varsayilanlari_kullan"],
            key="kural_varsayilan",
            help="Kapatırsan yalnızca kendi kuralların değerlendirilir.",
        )
        if varsayilan_acik != kural_ayarlari["varsayilanlari_kullan"]:
            izleme.varsayilan_kullanimi_degistir(varsayilan_acik)
            st.rerun()

        st.markdown("**Yeni kural**")
        gosterge_secenekleri = list(ind.GOSTERGE_KATALOGU)
        kural_sutun = st.columns([2, 1, 1, 1])
        secili_gosterge = kural_sutun[0].selectbox(
            "Gösterge", gosterge_secenekleri, key="kural_gosterge",
            format_func=ind.gosterge_etiketi,
        )
        tur = ind.gosterge_turu(secili_gosterge)

        # Operatör ve eşik, göstergenin türüne göre değişir: kesişim
        # göstergesiyle "küçüktür" karşılaştırması anlamsızdır.
        if tur == "kesisim":
            secili_operator = "kesisim"
            kural_sutun[1].markdown("&nbsp;\n\nkesişim yönü")
            secili_esik = kural_sutun[2].selectbox(
                "Yön", ["yukari", "asagi"], key="kural_esik_kesisim",
                format_func=lambda y: ind.KESISIM_ESIKLERI[y],
            )
        elif tur == "mantiksal":
            secili_operator = "=="
            kural_sutun[1].markdown("&nbsp;\n\neşittir")
            secili_esik = kural_sutun[2].selectbox(
                "Değer", [True, False], key="kural_esik_mantik",
                format_func=lambda d: "doğru" if d else "yanlış",
            )
        else:
            secili_operator = kural_sutun[1].selectbox(
                "Karşılaştırma", ["<", ">"], key="kural_operator")
            secili_esik = kural_sutun[2].number_input(
                "Eşik", value=30.0, step=1.0, format="%.4f", key="kural_esik_sayi")

        secili_yon = kural_sutun[3].selectbox("Yön", ind.YONLER, key="kural_yon")

        onizleme = ind.kural_adi_uret(secili_gosterge, secili_operator, secili_esik, secili_yon)
        st.caption(f"Kural adı: **{onizleme}**")

        if st.button("➕ Kuralı ekle", key="kural_ekle_dugme"):
            kural, sorun = ind.kural_olustur(
                secili_gosterge, secili_operator, secili_esik, secili_yon)
            if sorun:
                st.error(sorun)
            else:
                kayit_sorunu = izleme.kural_ekle(kural)
                if kayit_sorunu:
                    st.error(kayit_sorunu)
                else:
                    st.success(f"Eklendi: {kural['ad']}")
                    st.rerun()

        if kendi_kurallar:
            st.markdown("**Tanımlı kuralların**")
            for kural in kendi_kurallar:
                satir = st.columns([5, 1])
                simge = "🟢" if kural["yon"] == "AL" else "🔴"
                satir[0].write(f"{simge} {kural['ad']}")
                if satir[1].button("🗑️", key=f"kural_sil_{kural['ad']}"):
                    izleme.kural_sil(kural["ad"])
                    st.rerun()
        else:
            st.info("Henüz kendi kuralın yok; yukarıdan ekleyebilirsin.")

        with st.popover("📖 Varsayılan kurallar"):
            for kural in ind.VARSAYILAN_KURALLAR:
                simge = "🟢" if kural["yon"] == "AL" else "🔴"
                st.write(f"{simge} {kural['ad']}")

    st.info(
        "⚠️ **Yatırım tavsiyesi değildir.** Teknik göstergeler geçmiş fiyat "
        "hareketinin matematiksel özetidir; geleceği bilmezler. Bu tablo, "
        "kendi kurallarını tek ekranda görmen içindir — karar senindir."
    )
