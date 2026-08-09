import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
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
# 📊 ARAYÜZ BAŞLIĞI
# ==========================================
st.title("🤖 Ajan Portföy Paneli")
st.caption("3 Kazanlı Sermaye Yönetimi & Canlı Piyasa Takip Ajanı")

df_islem, df_ozet = excel_oku()

# 📑 SEKMELER
tab1, tab2, tab3 = st.tabs(["📊 Portföy Durumu", "➕ Yeni İşlem Ekle", "⚡ Canlı Takip Radarı"])

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
            st.subheader("Kazan Dağılımı")
            kazan_data = {
                "Kazan": ["A Kazanı", "B Kazanı", "C Kazanı"],
                "Değer": [son_durum.get('A Kazan', 0), son_durum.get('B Kazan', 0), son_durum.get('C Kazan', 0)]
            }
            fig_kazan = px.pie(kazan_data, values="Değer", names="Kazan", hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
            st.plotly_chart(fig_kazan, use_container_width=True)
            
        with col_sag:
            st.subheader("Zaman İçinde Portföy Büyümesi")
            fig_line = px.line(df_ozet, x="Tarih", y="Toplam Portföy Değeri", markers=True)
            st.plotly_chart(fig_line, use_container_width=True)
    else:
        st.info("Henüz özet bilanço verisi bulunmuyor. Sol menüden işlem ekleyebilirsiniz.")

    if df_islem is not None and not df_islem.empty:
        st.subheader("Geçmiş İşlem Defteri")
        st.dataframe(df_islem, use_container_width=True)

# ------------------------------------------
# SEKME 2: YENİ İŞLEM EKLE
# ------------------------------------------
with tab2:
    st.header("Yeni İşlem Kaydı")
    with st.form("islem_formu", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            tarih = st.date_input("İşlem Tarihi", datetime.now())
            tur = st.selectbox("İşlem Türü", ["ALIM", "SATIM"])
            kod = st.text_input("Varlık / Hisse Kodu (Örn: THYAO, BTC, AAPL)", "THYAO")
            kazan = st.selectbox("Kazan Sınıfı", ["A Kazanı (Hisse)", "B Kazanı (Kripto/Döviz/Metal)", "C Kazanı (Nakit/Mevduat)"])
        with col2:
            adet = st.number_input("Adet / Miktar", min_value=0.0001, value=1.0, step=1.0)
            fiyat = st.number_input("Birim Fiyat (TL)", min_value=0.01, value=100.0, step=0.5)
            notlar = st.text_area("İşlem Notu / Strateji", "")
            
        submit = st.form_submit_button("💾 İşlemi Excel Defterine Kaydet")
        
        if submit:
            if excel_islem_ekle(tarih, tur, kod, adet, fiyat, kazan, notlar):
                st.success(f"{kod} işlemi başarıyla kaydedildi!")
                st.rerun()

# ------------------------------------------
# SEKME 3: CANLI TAKİP RADARI
# ------------------------------------------
with tab3:
    st.header("⚡ Canlı Piyasa & Portföy Radarı")
    st.caption("Veriler yfinance ve canlı hesaplama motoruyla anlık taranır.")
    
    if st.button("🔄 Fiyatları Şimdi Yenile"):
        st.rerun()
        
    m1, m2, m3, m4 = st.columns(4)
    try:
        makro_data = yf.Tickers("GC=F USDTRY=X EURTRY=X ^GSPC BTC-USD")
        ons = makro_data.tickers["GC=F"].fast_info.get('lastPrice', 0)
        dolar = makro_data.tickers["USDTRY=X"].fast_info.get('lastPrice', 0)
        euro = makro_data.tickers["EURTRY=X"].fast_info.get('lastPrice', 0)
        btc = makro_data.tickers["BTC-USD"].fast_info.get('lastPrice', 0)
        gram = (ons * dolar) / 31.1035 if ons and dolar else 0
        
        m1.metric("Gram Altın (Canlı)", f"₺{gram:,.2f}")
        m2.metric("Dolar / TL", f"₺{dolar:,.2f}")
        m3.metric("Euro / TL", f"₺{euro:,.2f}")
        m4.metric("Bitcoin ($)", f"${btc:,.2f}")
    except Exception:
        st.warning("Makro veriler çekilirken anlık gecikme oluştu.")
        
    st.markdown("---")
    st.subheader("📋 Portföydeki Varlıkların Canlı Fiyat Takibi")
    
    if df_islem is not None and not df_islem.empty:
        varliklar = df_islem["Hisse Kodu"].dropna().unique().tolist()
        canli_liste = []
        
        for v in varliklar:
            v_str = str(v).strip().upper()
            if v_str in ["BTC", "ETH", "SOL", "AVAX"]:
                sembol = f"{v_str}-USD"
            elif len(v_str) <= 4 and not v_str.endswith(".IS"):
                sembol = v_str
            else:
                sembol = f"{v_str.replace('.IS', '')}.IS"
                
            try:
                t_obj = yf.Ticker(sembol)
                fiyat = t_obj.fast_info.get('lastPrice', None)
                onceki = t_obj.fast_info.get('previousClose', None)
                degisim = ((fiyat - onceki) / onceki) * 100 if fiyat and onceki else 0
                
                canli_liste.append({
                    "Varlık Kodu": v_str,
                    "Takip Sembolü": sembol,
                    "Canlı Fiyat": round(fiyat, 2) if fiyat else "N/A",
                    "Günlük Değişim": f"%{degisim:+.2f}"
                })
            except:
                canli_liste.append({"Varlık Kodu": v_str, "Takip Sembolü": sembol, "Canlı Fiyat": "N/A", "Günlük Değişim": "%0.00"})
                
        st.dataframe(pd.DataFrame(canli_liste), use_container_width=True)
    else:
        st.info("Portföyünüzde takip edilecek varlık bulunamadı. Lütfen önce işlem ekleyin.")