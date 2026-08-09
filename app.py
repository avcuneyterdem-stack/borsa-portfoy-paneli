# --- ÜST BİLGİ BARI: CANLI DÖVİZ KURLARI VE DEĞERLİ METALLER ---
st.title("🤖 Ajan Portföy Paneli")

st.markdown("### 💱 Canlı Döviz Kurları & 🥇 Değerli Metaller")

# 1. SIRA: DÖVİZ KURLARI
col_k1, col_k2, col_k3 = st.columns(3)
with col_k1: components.html(tradingview_mini_widget("FX_IDC:USDTRY"), height=220)
with col_k2: components.html(tradingview_mini_widget("FX_IDC:EURTRY"), height=220)
with col_k3: components.html(tradingview_mini_widget("FX_IDC:GBPTRY"), height=220)

# 2. SIRA: DEĞERLİ METALLER (ALTIN & GÜMÜŞ)
col_m1, col_m2, col_m3 = st.columns(3)
with col_m1: components.html(tradingview_mini_widget("OANDA:XAUUSD"), height=220) # Ons Altın ($)
with col_m2: components.html(tradingview_mini_widget("OANDA:XAGUSD"), height=220) # Ons Gümüş ($)
with col_m3: components.html(tradingview_mini_widget("TVC:GOLD"), height=220)     # Altın Genel Trend

kurlar = doviz_kurlari_getir()
st.markdown("---")