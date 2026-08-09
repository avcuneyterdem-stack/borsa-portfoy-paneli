import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
import os
from datetime import datetime

# Streamlit Sayfa Ayarları
st.set_page_config(page_title="Ajan Portföy Paneli", page_icon="🤖", layout="wide")

# ==========================================
# 📂 EXCEL VE VERİ YÖNETİMİ
# ==========================================
EXCEL_PATH = "portfoy_defteri_hisse.xlsx"

@st.cache_data(ttl=60)
def excel_oku():
    if os.path.exists(EXCEL_PATH):
        try:
            df_islem = pd.read_excel(EXCEL_PATH, sheet_name="İşlemler")
            df_ozet = pd.read_excel(EXCEL_PATH, sheet_name="Özet Bilanço")
            return df_islem, df_ozet
        except Exception as e:
            st.error(f"Excel okunurken hata oluştu: {e}")
            return None, None
    return None, None

def excel_islem_ekle(tarih, tur, kod, adet, fiyat, kazan, notlar):
    try:
        if os.path.exists(EXCEL_PATH):
            df_islem = pd.read_excel(EXCEL_PATH, sheet_name="İşlemler")
            df_ozet = pd.read_excel(EXCEL_PATH, sheet_name="Özet Bilanço")
        else:
            df_islem = pd.DataFrame(columns=["Tarih", "İşlem Türü", "Hisse Kodu", "Adet", "Birim Fiyat (TL)", "Kazan", "Notlar"])
            df_ozet = pd.DataFrame(columns=["Tarih", "Toplam Portföy Değeri", "Nakit", "A Kazan", "B Kazan", "C Kazan"])

        yeni_islem = pd.DataFrame([{
            "Tarih": tarih.strftime("%Y-%m-%d"),
            "İşlem Türü": tur,
            "Hisse Kodu": str(kod).upper().strip(),
            "Adet": float(adet),
            "Birim Fiyat (TL)": float(fiyat),
            "Kazan": kazan,
            "Notlar": notlar
        }])

        df_islem = pd.concat([df_islem, yeni_islem], ignore_index=True)

        with pd.ExcelWriter(EXCEL_PATH, engine="openpyxl") as writer:
            df_islem.to_excel(writer, sheet_name="İşlemler", index=False)
            df_ozet.to_excel(writer, sheet_name="Özet Bilanço", index=False)

        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Kaydederken hata oluştu: {e}")
        return False

# ==========================================
# 📊 ARAYÜZ VE SOL MENÜ (SIDEBAR)
# ==========================================
df_islem, df_ozet = excel_oku()

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2092/2092663.png", width=80)
    st.title("🤖 Portföy Yönetimi")
    st.caption("Ajan Komuta Merkezi")
    st.markdown("---")
    
    st.subheader("➕ Hızlı İşlem Girişi")
    with st.form("sidebar_islem_formu", clear_on_submit=True):
        tarih = st.date_input("Tarih", datetime.now())
        tur = st.selectbox("İşlem Türü", ["ALIM", "SATIM"])
        kod = st.text_input("Varlık Kodu (THYAO, BTC vb.)", "THYAO")
        kazan = st.selectbox("Kazan", ["A Kazanı (Hisse)", "B Kazanı (Kripto/Döviz/Metal)", "C Kazanı (Nakit)"])
        adet = st.number_input("Adet", min_value=0.0001, value=1.0)
        fiyat = st.number_input("Birim Fiyat (TL)", min_value=0.01, value=100.0)
        notlar = st.text_input("Not", "")
        
        btn = st.form_submit_button("💾 Kaydet")
        if btn:
            if excel_islem_ekle(tarih, tur, kod, adet, fiyat, kazan, notlar):
                st.success("İşlem eklendi!")
                st.rerun()

st.title("🤖 Ajan Portföy Paneli")
st.caption("3 Kazanlı Sermaye Yönetimi & Canlı Piyasa Takip Ajanı")

# 📑 SEKMELER
tab1, tab2, tab3, tab4 = st.tabs(["📊 Portföy Durumu", "📈 Canlı Piyasa Grafikleri", "📋 Geçmiş İşlemler", "⚡ Canlı Takip Radarı"])

# ------------------------------------------
# SEKME 1: PORTFÖY DURUMU
# ------------------------------------------
with tab1:
    st.header("Portföy Genel Bakış")
    if df_ozet is not None and not df_ozet.empty:
        son_durum = df_ozet.iloc[-1]
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Toplam Portföy Değeri", f"₺{son_durum.get('Toplam Portföy Değeri', 0):,.2f}")
        col2.metric("A Kazanı (Hisse)", f"₺{son_durum.get('A Kazan', 0):,.2f}")
        col3.metric("B Kazanı (Kripto/Döviz)", f"₺{son_durum.get('B Kazan', 0):,.2f}")
        col4.metric("C Kazanı (Nakit)", f"₺{son_durum.get('C Kazan', 0):,.2f}")
        
        st.markdown("---")
        col_sol, col_sag = st.columns(2)
        with col_sol:
            st.subheader("3 Kazan Dağılımı")
            kazan_data = {
                "Kazan": ["A Kazanı", "B Kazanı", "C Kazanı"],
                "Değer": [son_durum.get('A Kazan', 0), son_durum.get('B Kazan', 0), son_durum.get('C Kazan', 0)]
            }
            fig_kazan = px.pie(kazan_data, values="Değer", names="Kazan", hole=0.4, color_discrete_sequence=px.colors.qualitative.Set3)
            st.plotly_chart(fig_kazan, use_container_width=True)
            
        with col_sag:
            st.subheader("Portföy Büyüme Trendi")
            fig_line = px.line(df_ozet, x="Tarih", y="Toplam Portföy Değeri", markers=True, line_shape="spline")
            st.plotly_chart(fig_line, use_container_width=True)
    else:
        st.info("Henüz kaydedilmiş özet bilanço verisi yok. Sol taraftaki menüden ilk işleminizi girebilirsiniz.")

# ------------------------------------------
# SEKME 2: CANLI PİYASA GRAFİKLERİ
# ------------------------------------------
with tab2:
    st.header("📈 Canlı Piyasa & Döviz Grafikleri")
    grafik_secim = st.selectbox("Grafik Seçin", ["Gram Altın (TL)", "Dolar / TL", "BIST 100", "Bitcoin ($)", "S&P 500"])
    
    sembol_map = {
        "Gram Altın (TL)": "GC=F",
        "Dolar / TL": "USDTRY=X",
        "BIST 100": "XU100.IS",
        "Bitcoin ($)": "BTC-USD",
        "S&P 500": "^GSPC"
    }
    
    periyot = st.radio("Zaman Aralığı", ["1mo", "3mo", "6mo", "1y"], horizontal=True)
    
    try:
        data_hist = yf.Ticker(sembol_map[grafik_secim]).history(period=periyot)
        if not data_hist.empty:
            fig_chart = px.area(data_hist, x=data_hist.index, y="Close", title=f"{grafik_secim} Trend Grafiği")
            st.plotly_chart(fig_chart, use_container_width=True)
    except Exception as e:
        st.warning("Grafik yüklenirken bir sorun oluştu.")

# ------------------------------------------
# SEKME 3: GEÇMİŞ İŞLEMLER
# ------------------------------------------
with tab3:
    st.header("📋 İşlem Geçmişi & Defter")
    if df_islem is not None and not df_islem.empty:
        st.dataframe(df_islem, use_container_width=True)
    else:
        st.info("Geçmiş işlem kaydı bulunmuyor.")

# ------------------------------------------
# SEKME 4: CANLI TAKİP RADARI
# ------------------------------------------
with tab4:
    st.header("⚡ Canlı Piyasa & Portföy Radarı")
    if st.button("🔄 Verileri Yenile"):
        st.rerun()
        
    m1, m2, m3, m4 = st.columns(4)
    try:
        makro_data = yf.Tickers("GC=F USDTRY=X EURTRY=X BTC-USD")
        ons = makro_data.tickers["GC=F"].fast_info.get('lastPrice', 0)
        dolar = makro_data.tickers["USDTRY=X"].fast_info.get('lastPrice', 0)
        euro = makro_data.tickers["EURTRY=X"].fast_info.get('lastPrice', 0)
        btc = makro_data.tickers["BTC-USD"].fast_info.get('lastPrice', 0)
        gram = (ons * dolar) / 31.1035 if ons and dolar else 0
        
        m1.metric("Gram Altın", f"₺{gram:,.2f}")
        m2.metric("Dolar / TL", f"₺{dolar:,.2f}")
        m3.metric("Euro / TL", f"₺{euro:,.2f}")
        m4.metric("Bitcoin", f"${btc:,.2f}")
    except Exception:
        pass