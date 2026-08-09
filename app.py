import streamlit as st
import pandas as pd
import yfinance as yf
import datetime
import os
import requests
import plotly.express as px
import streamlit.components.v1 as components
from streamlit_searchbox import st_searchbox

# --- SAYFA YAPILANDIRMASI ---
st.set_page_config(
    page_title="Global Ajan Portföy Paneli",
    page_icon="🌍",
    layout="wide"
)

EXCEL_HISSE = "portfoy_defteri_hisse.xlsx"
EXCEL_KRIPTO = "portfoy_defteri_kripto.xlsx"

if os.path.exists("portfoy_defteri.xlsx") and not os.path.exists(EXCEL_HISSE):
    os.rename("portfoy_defteri.xlsx", EXCEL_HISSE)

# --- CANLI ARAMA FONKSİYONLARI (KÜRESEL) ---
def canlı_hisse_sorgula(search_term: str):
    if not search_term or len(search_term.strip()) < 1:
        return []
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={search_term}&quotesCount=10&newsCount=0"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers, timeout=3)
        if res.status_code == 200:
            quotes = res.json().get('quotes', [])
            sonuclar = []
            for q in quotes:
                symbol = q.get('symbol', '')
                name = q.get('shortname') or q.get('longname') or symbol
                exch = q.get('exchDisp', '')
                if symbol:
                    sonuclar.append((f"🌐 {symbol} - {name} ({exch})", symbol))
            return sonuclar
    except Exception:
        pass
    return [(search_term.upper(), search_term.upper())]

def canlı_kripto_sorgula(search_term: str):
    if not search_term or len(search_term.strip()) < 1:
        return []
    term = search_term.strip().upper()
    if "SOLAN" in term: term = "SOL"
    elif "BITCOIN" in term: term = "BTC"
    elif "ETHEREUM" in term: term = "ETH"
    elif "RIPPLE" in term: term = "XRP"

    url = "https://api.binance.com/api/v3/ticker/price"
    try:
        res = requests.get(url, timeout=3)
        if res.status_code == 200:
            sonuclar = []
            for item in res.json():
                symbol = item['symbol']
                if symbol.endswith("USDT") and term in symbol:
                    coin_name = symbol.replace("USDT", "")
                    sonuclar.append((f"🪙 {coin_name} / USDT (Binance)", coin_name))
                if len(sonuclar) >= 15: break
            return sonuclar
    except Exception:
        pass
    return [(f"🪙 {term} / USDT", term)]

# --- YARDIMCI FONKSİYONLAR ---
@st.cache_data(ttl=60)
def doviz_kurlari_getir():
    kurlar = {"USD": 34.0, "EUR": 37.0, "GBP": 44.0, "TRY": 1.0}
    try:
        tickers = yf.Tickers("USDTRY=X EURTRY=X GBPTRY=X")
        u_hist = tickers.tickers["USDTRY=X"].history(period="1d")
        e_hist = tickers.tickers["EURTRY=X"].history(period="1d")
        g_hist = tickers.tickers["GBPTRY=X"].history(period="1d")
        if not u_hist.empty: kurlar["USD"] = float(u_hist['Close'].iloc[-1])
        if not e_hist.empty: kurlar["EUR"] = float(e_hist['Close'].iloc[-1])
        if not g_hist.empty: kurlar["GBP"] = float(g_hist['Close'].iloc[-1])
    except Exception:
        pass
    return kurlar

def tradingview_mini_widget(symbol):
    return f"""
    <div class="tradingview-widget-container">
      <div class="tradingview-widget-container__widget"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-mini-symbol-overview.js" async>
      {{ "symbol": "{symbol}", "width": "100%", "height": "210", "locale": "tr", "dateRange": "1M", "colorTheme": "dark", "isTransparent": false, "autosize": false }}
      </script>
    </div>
    """

def tradingview_gelismis_widget(tv_symbol):
    return f"""
    <div class="tradingview-widget-container" style="height:600px;width:100%">
      <div id="tradingview_advanced_chart" style="height:calc(100% - 32px);width:100%"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({{
        "autosize": true, "symbol": "{tv_symbol}", "interval": "D", "timezone": "Europe/Istanbul",
        "theme": "dark", "style": "1", "locale": "tr", "enable_publishing": false, "container_id": "tradingview_advanced_chart"
      }});
      </script>
    </div>
    """

def kazan_format_temizle(kazan_metni):
    kazan_str = str(kazan_metni)
    if "A Kazanı" in kazan_str: return "A Kazanı (%50 - Sakin Liman)"
    elif "B Kazanı" in kazan_str: return "B Kazanı (%40 - Büyüme)"
    elif "C Kazanı" in kazan_str: return "C Kazanı (%10 - Agresif)"
    return kazan_str

def veri_yukle(dosya_adi):
    if os.path.exists(dosya_adi):
        try:
            df = pd.read_excel(dosya_adi)
            for col in ["Para_Birimi", "Tip", "Kazan"]:
                if col not in df.columns: df[col] = "USD" if col == "Para_Birimi" else ""
            df["Kazan"] = df["Kazan"].apply(kazan_format_temizle)
            return df
        except Exception:
            return pd.DataFrame(columns=["Tarih", "Hisse", "Kazan", "Tip", "Fiyat", "Adet", "Toplam", "Para_Birimi"])
    return pd.DataFrame(columns=["Tarih", "Hisse", "Kazan", "Tip", "Fiyat", "Adet", "Toplam", "Para_Birimi"])

def veri_kaydet(df, dosya_adi):
    if "Kazan" in df.columns: df["Kazan"] = df["Kazan"].apply(kazan_format_temizle)
    if "Sil" in df.columns: df = df.drop(columns=["Sil"])
    df.to_excel(dosya_adi, index=False)

def binance_fiyat_getir(symbol):
    temiz = symbol.replace("USDT", "").replace("-USD", "").strip().upper() + "USDT"
    try:
        res = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={temiz}", timeout=3)
        if res.status_code == 200: return float(res.json()['price'])
    except Exception: pass
    return None

def hisse_kod_duzelt(hisse_kodu):
    kod = hisse_kodu.strip().upper()
    if kod.endswith(".IS"): return kod
    if kod in ["THYAO", "GARAN", "KCHOL", "TUPRS", "SAHOL", "AKBNK", "YKBNK", "BIMAS", "SISE", "EREGL", "ASELS", "ISCTR"]:
        return f"{kod}.IS"
    return kod

def hisse_fiyat_getir(hisse_kodu):
    kod = hisse_kod_duzelt(hisse_kodu)
    try:
        ticker = yf.Ticker(kod)
        hist = ticker.history(period="5d")
        if not hist.empty: return kod, float(hist['Close'].iloc[-1]), ticker.info.get('shortName', kod)
        return kod, None, None
    except Exception: return hisse_kodu, None, None

def hisse_kazan_otomatik_belirle(hisse_kodu):
    kod = hisse_kod_duzelt(hisse_kodu)
    # ABD Dev Şirketleri Otomatik A Kazanı
    if kod in ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "BRK-B"]:
        return "A Kazanı (%50 - Sakin Liman)"
    try:
        ticker = yf.Ticker(kod)
        info = ticker.info
        market_cap = info.get('marketCap', 0)
        beta = info.get('beta', 1.0)
        if kod.endswith(".IS") and kod.replace(".IS","") in ["THYAO", "GARAN", "KCHOL", "TUPRS"]: return "A Kazanı (%50 - Sakin Liman)"
        elif market_cap > 50_000_000_000 or (beta and beta < 0.85 and market_cap > 10_000_000_000): return "A Kazanı (%50 - Sakin Liman)"
        elif market_cap > 2_000_000_000: return "B Kazanı (%40 - Büyüme)"
        else: return "C Kazanı (%10 - Agresif)"
    except Exception: return "B Kazanı (%40 - Büyüme)"

def tv_sembol_donustur(hisse_kodu, kripto_mu=False):
    kod = hisse_kodu.strip().upper()
    if kripto_mu or kod in ["BTC", "ETH", "SOL", "AVAX", "XRP"] or "USDT" in kod:
        return f"BINANCE:{kod.replace('USDT', '').replace('-USD', '')}USDT"
    elif kod.endswith(".IS"): return f"BIST:{kod.replace('.IS', '')}"
    elif len(kod) <= 5 and not any(char.isdigit() for char in kod): return f"NASDAQ:{kod}"
    return kod

# --- ÜST BİLGİ BARI: CANLI KÜRESEL BORSA & DÖVİZ KURLARI ---
st.title("🌍 Global Ajan Portföy Paneli")

st.markdown("### 💱 Canlı Döviz Kurları & Küresel Endeksler")
col_k1, col_k2, col_k3 = st.columns(3)
with col_k1: components.html(tradingview_mini_widget("FX_IDC:USDTRY"), height=220)
with col_k2: components.html(tradingview_mini_widget("FOREXCOM:SPXUSD"), height=220)
with col_k3: components.html(tradingview_mini_widget("FOREXCOM:NSXUSD"), height=220)

st.markdown("### 🥇 Canlı Değerli Metaller (Altın & Gümüş)")
col_m1, col_m2, col_m3 = st.columns(3)
with col_m1: components.html(tradingview_mini_widget("OANDA:XAUUSD"), height=220)
with col_m2: components.html(tradingview_mini_widget("OANDA:XAGUSD"), height=220)
with col_m3: components.html(tradingview_mini_widget("TVC:GOLD"), height=220)

kurlar = doviz_kurlari_getir()
st.markdown("---")

# --- YAN MENÜ ---
st.sidebar.header("⚙️ Portföy & Veri Yönetimi")
col_y1, col_y2 = st.sidebar.columns(2)
with col_y1:
    if os.path.exists(EXCEL_HISSE):
        with open(EXCEL_HISSE, "rb") as file: st.download_button("📥 Hisse Excel", file, file_name="hisse_portfoy.xlsx")
with col_y2:
    if os.path.exists(EXCEL_KRIPTO):
        with open(EXCEL_KRIPTO, "rb") as file: st.download_button("📥 Kripto Excel", file, file_name="kripto_portfoy.xlsx")

st.sidebar.markdown("---")
st.sidebar.subheader("🛡️ 3 Kazanlı Sermaye Stratejisi")
st.sidebar.info("**A Kazanı (%50):** Dev Şirketler (BIST/US) & BTC/ETH")
st.sidebar.success("**B Kazanı (%40):** Büyüme Şirketleri")
st.sidebar.warning("**C Kazanı (%10):** Agresif Hisseler & Altcoinler")

st.sidebar.markdown("---")
st.sidebar.header("📜 İşlem Geçmişi & Filtreler")
secilen_gecmis_tur = st.sidebar.radio("Geçmiş Türü:", ["Hisse İşlemleri", "Kripto İşlemleri"], horizontal=True)
dosya_gecmis = EXCEL_HISSE if "Hisse" in secilen_gecmis_tur else EXCEL_KRIPTO
df_gecmis_mevcut = veri_yukle(dosya_gecmis)

if not df_gecmis_mevcut.empty:
    hisse_filtre = st.sidebar.text_input("🔍 Hisse/Kripto Ara:", "").strip().upper()
    tip_filtre = st.sidebar.selectbox("🏷️ İşlem Tipi Süzgeci:", ["Tümü", "Sadece AL 🟢", "Sadece SAT 🔴", "Sadece Temettü/Staking 💰"])
    df_sol_gecmis = df_gecmis_mevcut.copy()
    if hisse_filtre: df_sol_gecmis = df_sol_gecmis[df_sol_gecmis["Hisse"].str.contains(hisse_filtre, na=False)]
    if tip_filtre == "Sadece AL 🟢": df_sol_gecmis = df_sol_gecmis[df_sol_gecmis["Tip"].str.contains("AL", na=False)]
    elif tip_filtre == "Sadece SAT 🔴": df_sol_gecmis = df_sol_gecmis[df_sol_gecmis["Tip"].str.contains("SAT", na=False)]
    elif tip_filtre == "Sadece Temettü/Staking 💰": df_sol_gecmis = df_sol_gecmis[df_sol_gecmis["Tip"].str.contains("TEMETTÜ|STAKING", na=False)]
    
    with st.sidebar.expander("📂 Filtrelenmiş Kayıtlar (Tıkla/Aç)", expanded=True):
        st.dataframe(df_sol_gecmis.iloc[::-1][["Tarih", "Hisse", "Tip", "Fiyat", "Adet", "Para_Birimi"]], height=300, width='stretch')

# --- ANA EKRAN SEKMELERİ ---
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📈 Hisse Senedi Portföyü (BIST & ABD)", 
    "🪙 Kripto Varlık Portföyü", 
    "🤖 AI Araştırmacı Ajanı", 
    "⚡ Canlı Takip Radarı",
    "💻 Sistem & Yazılım Ar-Ge Ajanı"
])

# SEKME 1: HİSSE PORTFÖYÜ
with tab1:
    st.title("📈 Gerçekleşen Hisse Senedi İşlem Kaydı (BIST / Nasdaq / NYSE)")
    col_s1, col_s2 = st.columns([1, 1])
    with col_s1:
        secilen_symbol = st_searchbox(canlı_hisse_sorgula, key="hisse_searchbox", placeholder="ABD veya BIST Hisse Kodu (Örn: AAPL, NVDA, THYAO)...")
        girilen_hisse = secilen_symbol.strip().upper() if secilen_symbol else ""

    with col_s2:
        otomatik_kazan = "B Kazanı (%40 - Büyüme)"
        if girilen_hisse:
            tam_kod, canli_f, sirket_adi = hisse_fiyat_getir(girilen_hisse)
            otomatik_kazan = hisse_kazan_otomatik_belirle(girilen_hisse)
            if canli_f: st.success(f"✅ **{sirket_adi}** | Anlık: **{canli_f:,.2f}** | 🤖 **AI:** {otomatik_kazan}")

    with st.form("hisse_formu", clear_on_submit=True):
        col1, col2, col3, col4 = st.columns(4)
        with col1: tip = st.selectbox("İşlem Tipi", ["AL 🟢", "SAT 🔴", "TEMETTÜ 💰"], key="h_tip")
        with col2: para_birimi = st.selectbox("Para Birimi", ["USD ($)", "TRY (₺)", "EUR (€)", "GBP (£)"], key="h_pb")
        with col3: fiyat = st.number_input("İşlem Fiyatı / Tutar:", min_value=0.0, value=None, placeholder="Örn: 220.50", step=0.01, format="%.4f", key="h_f")
        with col4: adet = st.number_input("Adet:", min_value=1, value=1, step=1, key="h_a")
        c1, c2, c3 = st.checkbox("🛡️ Stratejime uygun.", key="h_c1"), st.checkbox("🧠 Duygusal değil.", key="h_c2"), st.checkbox("📱 Kurumda gerçekleşti.", key="h_c3")
        
        if st.form_submit_button("💾 Hisse İşlemini Kaydet"):
            if not girilen_hisse or not (c1 and c2 and c3) or fiyat is None or fiyat <= 0: st.error("Eksik bilgi!")
            else:
                df = veri_yukle(EXCEL_HISSE)
                yeni_veri = pd.DataFrame([{"Tarih": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "Hisse": girilen_hisse, "Kazan": otomatik_kazan, "Tip": tip, "Fiyat": fiyat, "Adet": adet, "Toplam": fiyat * adet, "Para_Birimi": para_birimi.split(" ")[0]}])
                veri_kaydet(pd.concat([df, yeni_veri], ignore_index=True), EXCEL_HISSE)
                st.success("✅ Kaydedildi!"); st.rerun()

    df_hisse = veri_yukle(EXCEL_HISSE)
    if not df_hisse.empty:
        st.markdown("---")
        st.subheader("📊 Canlı Hisse Portföy Durumu (Küresel)")
        portfoy_ozet, t_temettu, gerceklesen_kz = {}, 0.0, 0.0
        for _, row in df_hisse.iterrows():
            h, t, a, f, pb = row["Hisse"], row["Tip"], row["Adet"], row["Fiyat"], row.get("Para_Birimi", "USD")
            f_tl = f * kurlar.get(pb, 1.0)
            if "TEMETTÜ" in t: t_temettu += (a * f_tl); continue
            if h not in portfoy_ozet: portfoy_ozet[h] = {"Adet": 0, "Toplam_Maliyet_TL": 0.0, "Kazan": row.get("Kazan", ""), "Orijinal_PB": pb}
            if "AL" in t: portfoy_ozet[h]["Adet"] += a; portfoy_ozet[h]["Toplam_Maliyet_TL"] += (a * f_tl)
            elif "SAT" in t and portfoy_ozet[h]["Adet"] > 0:
                ort_tl = portfoy_ozet[h]["Toplam_Maliyet_TL"] / portfoy_ozet[h]["Adet"]
                gerceklesen_kz += (a * f_tl - a * ort_tl)
                portfoy_ozet[h]["Adet"] -= a; portfoy_ozet[h]["Toplam_Maliyet_TL"] -= (a * ort_tl)

        ozet_hisse, t_maliyet, t_deger = [], 0.0, 0.0
        for h, v in portfoy_ozet.items():
            if v["Adet"] > 0:
                m_usd = v["Toplam_Maliyet_TL"] / kurlar["USD"]
                kod, canli_f, _ = hisse_fiyat_getir(h)
                canli_usd = (canli_f * kurlar.get(v["Orijinal_PB"], 1.0)) / kurlar["USD"] if canli_f else (m_usd / v["Adet"])
                g_usd = v["Adet"] * canli_usd
                t_maliyet += m_usd; t_deger += g_usd
                ozet_hisse.append({"Hisse": h, "Kazan": v["Kazan"], "Adet": v["Adet"], "Ort. Maliyet ($)": round(m_usd/v["Adet"], 2), "Canlı Fiyat ($)": round(canli_usd, 2), "Toplam Maliyet ($)": round(m_usd, 2), "Güncel Değer ($)": round(g_usd, 2), "Kâr/Zarar ($)": round(g_usd - m_usd, 2)})

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Toplam Maliyet ($)", f"${t_maliyet:,.2f}")
        m2.metric("Güncel Değer ($)", f"${t_deger:,.2f}")
        m3.metric("Açık Pozisyon K/Z ($)", f"${t_deger - t_maliyet:,.2f}")
        m4.metric("Satış K/Z ($)", f"${gerceklesen_kz / kurlar['USD']:,.2f}")
        m5.metric("Toplam Temettü ($)", f"${t_temettu / kurlar['USD']:,.2f}")

        if ozet_hisse:
            df_ozet_h = pd.DataFrame(ozet_hisse)
            col_g1, col_g2 = st.columns([2, 1])
            with col_g1:
                st.dataframe(df_ozet_h, width='stretch')
            with col_g2:
                fig_kazan = px.pie(
                    df_ozet_h, 
                    names='Kazan', 
                    values='Güncel Değer ($)', 
                    title='🎨 Global Hisse 3 Kazan Dağılımı',
                    hole=0.4,
                    color_discrete_sequence=px.colors.qualitative.Pastel
                )
                fig_kazan.update_layout(margin=dict(t=30, b=0, l=0, r=0), height=250)
                st.plotly_chart(fig_kazan, use_container_width=True)

        st.markdown("---")
        st.subheader("📜 Tüm Geçmiş Hisse İşlem Kayıtları")
        st.caption("💡 İpucu: Silmek istediğiniz satırların en solundaki **Sil** kutucuğunu işaretleyin, ardından yukarıdaki kırmızı butona basın.")

        df_hisse_edit = df_hisse.copy()
        if "Sil" not in df_hisse_edit.columns:
            df_hisse_edit.insert(0, "Sil", False)

        edited_df_h = st.data_editor(
            df_hisse_edit, 
            column_config={
                "Sil": st.column_config.CheckboxColumn(
                    "Sil 🗑️",
                    help="Silinecek satırları seçin",
                    default=False,
                )
            },
            disabled=["Tarih", "Hisse", "Kazan", "Tip", "Fiyat", "Adet", "Toplam", "Para_Birimi"],
            hide_index=True,
            width='stretch',
            key="islem_editor_hisse"
        )

        silinecekler_h = edited_df_h[edited_df_h["Sil"] == True]
        if not silinecekler_h.empty:
            if st.button(f"🗑️ Seçilen {len(silinecekler_h)} Adet Hisse İşlemini Kalıcı Olarak Sil", type="primary", key="btn_sil_h_toplu"):
                kalan_df_h = edited_df_h[edited_df_h["Sil"] == False].drop(columns=["Sil"])
                veri_kaydet(kalan_df_h, EXCEL_HISSE)
                st.success(f"✅ Seçilen {len(silinecekler_h)} işlem başarıyla silindi!")
                st.rerun()

# SEKME 2: KRİPTO PORTFÖYÜ
with tab2:
    st.title("🪙 Gerçekleşen Kripto Varlık İşlem Kaydı")
    col_k1, col_k2 = st.columns([1, 1])
    with col_k1:
        secilen_kripto = st_searchbox(canlı_kripto_sorgula, key="kripto_searchbox", placeholder="Kripto Yazın...")
        girilen_kripto = secilen_kripto.strip().upper() if secilen_kripto else ""
    with col_k2:
        binance_fiyat = binance_fiyat_getir(girilen_kripto) if girilen_kripto else None
        if binance_fiyat: st.success(f"⚡ **Binance Canlı {girilen_kripto}:** **${binance_fiyat:,.4f}**")

    with st.form("kripto_formu", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1: k_tip = st.selectbox("İşlem Tipi", ["AL 🟢", "SAT 🔴", "STAKING 💰"], key="k_tip")
        with col2: k_fiyat = st.number_input("Fiyat ($ USDT):", min_value=0.0, value=binance_fiyat, format="%.4f", key="k_f")
        with col3: k_adet = st.number_input("Adet:", min_value=0.000001, value=1.0, step=0.1, format="%.6f", key="k_a")
        kc1, kc2, kc3 = st.checkbox("🛡️ Uygun.", key="k_c1"), st.checkbox("🧠 Soğukkanlı.", key="k_c2"), st.checkbox("📱 Gerçekleşti.", key="k_c3")
        if st.form_submit_button("💾 Kripto İşlemini Kaydet"):
            if not girilen_kripto or not (kc1 and kc2 and kc3) or k_fiyat is None or k_fiyat <= 0: st.error("Eksik bilgi!")
            else:
                df_k = veri_yukle(EXCEL_KRIPTO)
                kazan_k = "A Kazanı (%50 - Sakin Liman)" if girilen_kripto in ["BTC", "ETH"] else "C Kazanı (%10 - Agresif)"
                veri_kaydet(pd.concat([df_k, pd.DataFrame([{"Tarih": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "Hisse": girilen_kripto, "Kazan": kazan_k, "Tip": k_tip, "Fiyat": k_fiyat, "Adet": k_adet, "Toplam": k_fiyat * k_adet, "Para_Birimi": "USD"}])], ignore_index=True), EXCEL_KRIPTO)
                st.success("✅ Kaydedildi!"); st.rerun()

    df_kripto_data = veri_yukle(EXCEL_KRIPTO)
    if not df_kripto_data.empty:
        st.markdown("---")
        st.subheader("📜 Tüm Geçmiş Kripto İşlem Kayıtları")
        st.caption("💡 İpucu: Silmek istediğiniz satırların en solundaki **Sil** kutucuğunu işaretleyin, ardından yukarıdaki kırmızı butona basın.")
        
        df_kripto_edit = df_kripto_data.copy()
        if "Sil" not in df_kripto_edit.columns:
            df_kripto_edit.insert(0, "Sil", False)

        edited_df_k = st.data_editor(
            df_kripto_edit,
            column_config={
                "Sil": st.column_config.CheckboxColumn(
                    "Sil 🗑️",
                    help="Silinecek satırları seçin",
                    default=False,
                )
            },
            disabled=["Tarih", "Hisse", "Kazan", "Tip", "Fiyat", "Adet", "Toplam", "Para_Birimi"],
            hide_index=True,
            width='stretch',
            key="islem_editor_kripto"
        )

        silinecekler_k = edited_df_k[edited_df_k["Sil"] == True]
        if not silinecekler_k.empty:
            if st.button(f"🗑️ Seçilen {len(silinecekler_k)} Adet Kripto İşlemini Kalıcı Olarak Sil", type="primary", key="btn_sil_k_toplu"):
                kalan_df_k = edited_df_k[edited_df_k["Sil"] == False].drop(columns=["Sil"])
                veri_kaydet(kalan_df_k, EXCEL_KRIPTO)
                st.success(f"✅ Seçilen {len(silinecekler_k)} kripto işlemi başarıyla silindi!")
                st.rerun()

# SEKME 3: AI ARAŞTIRMACI
with tab3:
    st.title("🤖 AI Borsa & Kripto Araştırmacı Ajanı")
    col_a1, col_a2 = st.columns([2, 1])
    with col_a1: secilen_ajan = st_searchbox(canlı_hisse_sorgula, key="ajan_searchbox", placeholder="Grafiği Açılacak Hisse veya Kripto..."); ajan_kod = secilen_ajan.strip().upper() if secilen_ajan else "AAPL"
    with col_a2: varlik_turu = st.radio("Varlık Türü:", ["Hisse (BIST/US)", "Kripto (Binance)"], horizontal=True)
    if st.button("🔍 TradingView Grafiği Yükle"):
        tv_symbol = tv_sembol_donustur(ajan_kod, kripto_mu=("Kripto" in varlik_turu))
        components.html(tradingview_gelismis_widget(tv_symbol), height=620)

# SEKME 4: CANLI TAKİP RADARI
with tab4:
    st.title("⚡ Canlı Piyasa & Portföy Radarı")
    st.caption("Değerli Metaller, Döviz, S&P 500, Nasdaq, BIST, Kriptolar anlık takip edilir.")
    
    if st.button("🔄 Canlı Verileri Yenile", key="btn_radar_refresh"):
        st.rerun()
        
    rm1, rm2, rm3, rm4 = st.columns(4)
    try:
        r_data = yf.Tickers("GC=F USDTRY=X ^GSPC ^IXIC")
        r_ons = r_data.tickers["GC=F"].fast_info.get('lastPrice', 0)
        r_dolar = r_data.tickers["USDTRY=X"].fast_info.get('lastPrice', 0)
        r_spx = r_data.tickers["^GSPC"].fast_info.get('lastPrice', 0)
        r_ixic = r_data.tickers["^IXIC"].fast_info.get('lastPrice', 0)
        
        rm1.metric("Ons Altın ($)", f"${r_ons:,.2f}")
        rm2.metric("Dolar / TL", f"₺{r_dolar:,.2f}")
        rm3.metric("S&P 500 Index", f"{r_spx:,.2f}")
        rm4.metric("Nasdaq Index", f"{r_ixic:,.2f}")
    except Exception:
        st.warning("Makro piyasa verileri çekilirken anlık gecikme yaşandı.")
        
    st.markdown("---")
    st.subheader("📋 Portföydeki Varlıkların Anlık Canlı Fiyat Takibi")
    
    df_h_mevcut = veri_yukle(EXCEL_HISSE)
    df_k_mevcut = veri_yukle(EXCEL_KRIPTO)
    
    portfoy_varliklar = []
    if not df_h_mevcut.empty and "Hisse" in df_h_mevcut.columns:
        portfoy_varliklar.extend(df_h_mevcut["Hisse"].dropna().unique().tolist())
    if not df_k_mevcut.empty and "Hisse" in df_k_mevcut.columns:
        portfoy_varliklar.extend(df_k_mevcut["Hisse"].dropna().unique().tolist())
        
    if portfoy_varliklar:
        radar_tablosu = []
        for v in set(portfoy_varliklar):
            v_str = str(v).strip().upper()
            
            if v_str in ["BTC", "ETH", "SOL", "AVAX", "XRP", "ADA"] or "USDT" in v_str:
                sembol = f"{v_str.replace('USDT', '')}-USD"
                varlik_tipi = "Kripto"
            elif v_str in ["AAPL", "NVDA", "TSLA", "MSFT", "AMZN", "GOOGL", "META"]:
                sembol = v_str
                varlik_tipi = "ABD Borsası (Nasdaq/NYSE)"
            elif len(v_str) == 3 and v_str.isalpha() and not v_str.endswith(".IS"):
                sembol = f"{v_str}.IS"
                varlik_tipi = "TEFAS Fonu"
            else:
                sembol = f"{v_str.replace('.IS', '')}.IS"
                varlik_tipi = "BIST / Hisse"
                
            try:
                t_obj = yf.Ticker(sembol)
                fiyat = t_obj.fast_info.get('lastPrice', None)
                onceki = t_obj.fast_info.get('previousClose', None)
                degisim = ((fiyat - onceki) / onceki) * 100 if fiyat and onceki else 0.0
                
                radar_tablosu.append({
                    "Varlık Kodu": v_str,
                    "Kategori": varlik_tipi,
                    "Sistem Sembolü": sembol,
                    "Son Fiyat": f"{fiyat:,.2f}" if fiyat else "N/A",
                    "Günlük Değişim (%)": f"%{degisim:+.2f}"
                })
            except Exception:
                radar_tablosu.append({
                    "Varlık Kodu": v_str,
                    "Kategori": varlik_tipi,
                    "Sistem Sembolü": sembol,
                    "Son Fiyat": "N/A",
                    "Günlük Değişim (%)": "%0.00"
                })
                
        st.dataframe(pd.DataFrame(radar_tablosu), use_container_width=True)
    else:
        st.info("Portföyünüzde henüz kaydedilmiş bir varlık bulunmuyor. Sol taraftaki sekmelerden işlem ekleyebilirsiniz.")

# SEKME 5: SİSTEM & YAZILIM AR-GE AJANI (SKILL TABANLI)
with tab5:
    st.title("💻 Akıllı Yazılım & Ar-Ge Ajanı (Küresel Skill Entegreli)")
    st.caption("Ajan Skill'leri: Kod Denetimi, Global FinTek Kütüphane Araştırması ve Dinamik Sistem Mimarlığı.")
    
    # AJAN SKILL MODÜLLERİ
    def skill_code_audit():
        audit_results = []
        if os.path.exists(EXCEL_HISSE): audit_results.append("✅ **Hisse Veri Tabanı:** Aktif ve Erişilebilir.")
        else: audit_results.append("⚠️ **Hisse Veri Tabanı:** Eksik!")
        
        if os.path.exists(EXCEL_KRIPTO): audit_results.append("✅ **Kripto Veri Tabanı:** Aktif ve Erişilebilir.")
        else: audit_results.append("⚠️ **Kripto Veri Tabanı:** Eksik!")
        
        try:
            r = requests.get("https://api.binance.com/api/v3/ping", timeout=2)
            if r.status_code == 200: audit_results.append("✅ **Binance API Skill:** Aktif ve Canlı.")
        except: audit_results.append("❌ **Binance API Skill:** Kesinti!")
        
        return audit_results

    def skill_fintech_research(konu):
        if "küresel" in konu.lower() or "abd" in konu.lower():
            return [
                "🌐 **S&P 500 & Nasdaq Entegrasyonu:** Tamamlandı ✅ (Global hisselerAAPL, NVDA eklenebilir).",
                "💵 **Çoklu Para Birimi Otomasyonu:** ABD Hisseleri doğrudan USD cinsinden takip ediliyor.",
                "🏛️ **FED Faiz / Makro Takvim:** ABD Merkez Bankası faiz kararlarını takip eden widget."
            ]
        elif "indikatör" in konu.lower():
            return [
                "📊 **RSI (Relative Strength Index):** Aşırı alım/satım noktalarını tespit etmek için eklenmeli.",
                "📈 **MACD (Moving Average Convergence Divergence):** Trend dönüşüm sinyalleri için entegre edilmeli.",
                "🎯 **Bollinger Bantları:** Volatillik ve kırılım noktalarını ölçmek için koda işlenmeli."
            ]
        elif "arayüz" in konu.lower() or "görsel" in konu.lower():
            return [
                "🎨 **Portföy Pasta Grafiği:** 3 Kazan dağılımı görselleştirildi (Tamamlandı ✅).",
                "🔥 **Isı Haritası (Heatmap):** S&P 500 ve BIST için günlük kazandıran/kaybettiren Isı Haritası.",
                "📱 **Mobil Arayüz Kartları:** Tablo yerine mobilde kart görünümü entegre edilebilir."
            ]
        else:
            return [
                "📅 **Temettü Takvimi Sekmesi:** Global ve BIST hisselerinin temettü tarihlerini otomasyona bağlama.",
                "🔔 **Telegram / WhatsApp Bildirim Botu:** Fiyat kırılımlarında mesaj atacak bot Skill'i."
            ]

    st.subheader("🛠️ Ajan Skill Laboratuvarı")
    col_sk1, col_sk2 = st.columns(2)
    
    with col_sk1:
        st.markdown("### 🧪 1. Skill: Otonom Sistem & Kod Denetimi")
        if st.button("🔍 Kod Sağlığını ve Veri Yollarını Tara"):
            st.write("Ajan denetim fonksiyonunu çalıştırıyor...")
            results = skill_code_audit()
            for r in results:
                st.markdown(r)
                
    with col_sk2:
        st.markdown("### 🔎 2. Skill: Ar-Ge & FinTek Araştırmacısı")
        araştırma_konusu = st.selectbox(
            "Ajan Neyi Araştırsın?",
            ["Küresel Piyasalar & ABD Borsaları (NYSE/Nasdaq)", "Gelişmiş İndikatörler & Teknik Analiz", "Arayüz & Görsel Geliştirmeler", "Yeni Sekme & Otomasyon Fikirleri"]
        )
        if st.button("🚀 Ajan Araştırmasını Başlat"):
            st.info(f"🤖 **Ajan Araştırıyor:** *'{araştırma_konusu}'* alanı inceleniyor...")
            bulgular = skill_fintech_research(araştırma_konusu)
            for b in bulgular:
                st.write(b)

    st.markdown("---")
    st.subheader("📜 Ajanın Dinamik Gelişim Yol Haritası (Roadmap)")
    st.info("""
    **Sistem Mimarı Ajan Notu:** 
    Sistemimiz ABD Borsaları (Nasdaq / NYSE) ve S&P 500 küresel endeksleri ile genişletildi. 
    Bir sonraki Ar-Ge hedefimiz: **RSI ve MACD Teknik Göstergelerini** canlı verilere entegre etmek!
    """)