import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import streamlit.components.v1 as components
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
# 📊 SOL KENAR ÇUBUĞU (SIDEBAR)
# ==========================================
df_islem, df_ozet = excel_oku()

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2092/2092663.png", width=70)
    st.title("🤖 Veri Girişi")
    st.caption("İşlem & Portföy Yönetimi")
    st.markdown("---")
    
    st.subheader("➕ Yeni İşlem Kaydı")
    with st.form("sidebar_islem_formu", clear_on_submit=True):
        tarih = st.date_input("İşlem Tarihi", datetime.now())
        tur = st.selectbox("İşlem Türü", ["ALIM", "SATIM"])
        kod = st.text_input("Varlık Kodu (Örn: THYAO, BTC)", "THYAO")
        kazan = st.selectbox("Kazan Sınıfı", ["A Kazanı (Hisse)", "B Kazanı (Kripto/Döviz/Metal)", "C Kazanı (Nakit)"])
        adet = st.number_input("Adet / Miktar", min_value=0.0001, value=1.0)
        fiyat = st.number_input("Birim Fiyat (TL)", min_value=0.01, value=100.0)
        notlar = st.text_input("Not / Açıklama", "")
        
        btn = st.form_submit_button("💾 Excel Defterine Kaydet")
        if btn:
            if excel_islem_ekle(tarih, tur, kod, adet, fiyat, kazan, notlar):
                st.success("İşlem başarıyla eklendi!")
                st.rerun()

# ==========================================
# 🏠 ANA SAYFA VE BAŞLIK
# ==========================================
st.title("🤖 Ajan Portföy Paneli")
st.caption("3 Kazanlı Sermaye Yönetimi & Canlı Piyasa Takip Ajanı")

# 📑 SEKMELER
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Portföy & Canlı Hisse Durumu", 
    "📈 TradingView Canlı Piyasa", 
    "📋 Hisse Senedi İşlem Defteri", 
    "⚡ Canlı Takip Radarı"
])

# ------------------------------------------
# SEKME 1: CANLI HİSSE VE PORTFÖY DURUMU
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
            st.subheader("Varlık Kazan Dağılımı")
            kazan_data = {
                "Kazan": ["A Kazanı", "B Kazanı", "C Kazanı"],
                "Değer": [son_durum.get('A Kazan', 0), son_durum.get('B Kazan', 0), son_durum.get('C Kazan', 0)]
            }
            fig_kazan = px.pie(kazan_data, values="Değer", names="Kazan", hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
            st.plotly_chart(fig_kazan, use_container_width=True)
            
        with col_sag:
            st.subheader("Portföy Büyüme Grafiği")
            fig_line = px.line(df_ozet, x="Tarih", y="Toplam Portföy Değeri", markers=True)
            st.plotly_chart(fig_line, use_container_width=True)
    else:
        st.info("Henüz kaydedilmiş özet bilanço verisi yok. Sol taraftaki menüden ilk işleminizi girebilirsiniz.")

    # Canlı Hisse Senedi Portföy Durumu Tablosu
    st.markdown("---")
    st.subheader("📌 Canlı Hisse Senedi Portföy Durumu")
    if df_islem is not None and not df_islem.empty:
        st.dataframe(df_islem, use_container_width=True)

# ------------------------------------------
# SEKME 2: TRADINGVIEW CANLI DÖVİZ & GRAFİKLER
# ------------------------------------------
with tab2:
    st.header("📈 TradingView Canlı Döviz Kurları & Piyasalar")
    st.caption("Piyasa hareketlerini anlık TradingView widget'ları üzerinden takip edin.")
    
    # TradingView 1. Grafik (BIST 100 & Döviz Bantı)
    st.subheader("💱 Canlı Piyasa Bantı")
    ticker_widget = """
    <!-- TradingView Widget BEGIN -->
    <div class="tradingview-widget-container">
      <div class="tradingview-widget-container__widget"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js" async>
      {
      "symbols": [
        {"proName": "FX_IDC:USDTRY", "title": "USD/TRY"},
        {"proName": "FX_IDC:EURTRY", "title": "EUR/TRY"},
        {"proName": "BIST:XU100", "title": "BIST 100"},
        {"proName": "BITSTAMP:BTCUSD", "title": "Bitcoin"},
        {"proName": "OANDA:XAUUSD", "title": "Ons Altın"}
      ],
      "showSymbolLogo": true,
      "colorTheme": "light",
      "isTransparent": false,
      "displayMode": "adaptive",
      "locale": "tr"
    }
      </script>
    </div>
    <!-- TradingView Widget END -->
    """
    components.html(ticker_widget, height=100)
    
    st.markdown("---")
    st.subheader("📊 Canlı Teknik Analiz Grafikleri (3 Temel Varlık)")
    
    g1, g2, g3 = st.columns(3)
    
    with g1:
        st.markdown("**🇹🇷 BIST 100 Grafiği**")
        chart1 = """
        <iframe src="https://s.tradingview.com/widgetembed/?symbol=BIST%3AXU100&amp;interval=D&amp;symboledit=1&amp;saveimage=1&amp;toolbarbg=f1f3f6&amp;studies=%5B%5D&amp;theme=light&amp;style=1&amp;timezone=Etc%2FUTC&amp;studies_overrides=%7B%7D&amp;overrides=%7B%7D&amp;enabled_features=%5B%5D&amp;disabled_features=%5B%5D&amp;locale=tr" width="100%" height="350" frameborder="0" allowtransparency="true" scrolling="no"></iframe>
        """
        components.html(chart1, height=360)
        
    with g2:
        st.markdown("**💵 Dolar / TL Grafiği**")
        chart2 = """
        <iframe src="https://s.tradingview.com/widgetembed/?symbol=FX_IDC%3AUSDTRY&amp;interval=D&amp;symboledit=1&amp;saveimage=1&amp;toolbarbg=f1f3f6&amp;studies=%5B%5D&amp;theme=light&amp;style=1&amp;timezone=Etc%2FUTC&amp;studies_overrides=%7B%7D&amp;overrides=%7B%7D&amp;enabled_features=%5B%5D&amp;disabled_features=%5B%5D&amp;locale=tr" width="100%" height="350" frameborder="0" allowtransparency="true" scrolling="no"></iframe>
        """
        components.html(chart2, height=360)

    with g3:
        st.markdown("**🪙 Ons Altın Grafiği**")
        chart3 = """
        <iframe src="https://s.tradingview.com/widgetembed/?symbol=OANDA%3AXAUUSD&amp;interval=D&amp;symboledit=1&amp;saveimage=1&amp;toolbarbg=f1f3f6&amp;studies=%5B%5D&amp;theme=light&amp;style=1&amp;timezone=Etc%2FUTC&amp;studies_overrides=%7B%7D&amp;overrides=%7B%7D&amp;enabled_features=%5B%5D&amp;disabled_features=%5B%5D&amp;locale=tr" width="100%" height="350" frameborder="0" allowtransparency="true" scrolling="no"></iframe>
        """
        components.html(chart3, height=360)

# ------------------------------------------
# SEKME 3: HİSSE SENEDİ İŞLEM DEFTERİ
# ------------------------------------------
with tab3:
    st.header("📋 Hisse Senedi İşlem Defteri")
    if df_islem is not None and not df_islem.empty:
        st.dataframe(df_islem, use_container_width=True)
    else:
        st.info("İşlem defterinde kayıtlı veri bulunamadı. Sol menüden işlem ekleyebilirsiniz.")

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