import schedule
import time
import pandas as pd
import yfinance as yf
import datetime
import os

EXCEL_ISLEMLER = "portfoy_defteri.xlsx"
EXCEL_GECMIS = "portfoy_gecmisi.xlsx"

def doviz_kurlari_getir():
    kurlar = {"USD": 34.0, "EUR": 37.0, "GBP": 44.0, "TRY": 1.0}
    try:
        tickers = yf.Tickers("USDTRY=X EURTRY=X GBPTRY=X")
        u_hist = tickers.tickers["USDTRY=X"].history(period="1d")
        if not u_hist.empty: kurlar["USD"] = float(u_hist['Close'].iloc[-1])
    except Exception:
        pass
    return kurlar

def gun_sonu_portfoy_kaydet():
    if not os.path.exists(EXCEL_ISLEMLER):
        print("İşlem defteri bulunamadı, kayıt atlanıyor.")
        return
        
    try:
        df_islem = pd.read_excel(EXCEL_ISLEMLER)
        if df_islem.empty:
            return
            
        kurlar = doviz_kurlari_getir()
        
        # Pozisyon Özeti Hesaplama
        portfoy_ozet = {}
        for _, row in df_islem.iterrows():
            h = row["Hisse"]
            t = row["Tip"]
            a = row["Adet"]
            f = row["Fiyat"]
            pb = row.get("Para_Birimi", "USD")
            
            fiyat_tl = f * kurlar.get(pb, 1.0)
            
            if "TEMETTÜ" in t:
                continue
                
            if h not in portfoy_ozet:
                portfoy_ozet[h] = {"Adet": 0, "Orijinal_PB": pb}
                
            if "AL" in t:
                portfoy_ozet[h]["Adet"] += a
            elif "SAT" in t:
                if portfoy_ozet[h]["Adet"] > 0:
                    portfoy_ozet[h]["Adet"] -= a

        # Güncel Varlık Değeri Hesaplama
        toplam_varlik_usd = 0.0
        for h, v in portfoy_ozet.items():
            if v["Adet"] > 0:
                kod = h if h.endswith(".IS") else f"{h}.IS" if len(h) <= 5 and not any(char.isdigit() for char in h) and h in ["THYAO", "GARAN", "KCHOL", "TUPRS", "SAHOL", "AKBNK", "YKBNK", "BIMAS", "SISE", "EREGL", "ASELS", "ISCTR"] else h
                try:
                    hist = yf.Ticker(kod).history(period="5d")
                    canli_f = float(hist['Close'].iloc[-1]) if not hist.empty else 0.0
                except:
                    canli_f = 0.0
                    
                fiyat_tl = canli_f * kurlar.get(v["Orijinal_PB"], 1.0)
                varlik_usd = (v["Adet"] * fiyat_tl) / kurlar.get("USD", 34.0)
                toplam_varlik_usd += varlik_usd

        bugun_str = datetime.datetime.now().strftime("%Y-%m-%d")
        
        # Gün Geçmişini Kaydetme
        if os.path.exists(EXCEL_GECMIS):
            df_gecmis = pd.read_excel(EXCEL_GECMIS)
        else:
            df_gecmis = pd.DataFrame(columns=["Tarih", "Toplam_Varlik_USD"])
            
        df_gecmis = df_gecmis[df_gecmis["Tarih"] != bugun_str]
        yeni_kayit = pd.DataFrame([{"Tarih": bugun_str, "Toplam_Varlik_USD": round(toplam_varlik_usd, 2)}])
        df_gecmis = pd.concat([df_gecmis, yeni_kayit], ignore_index=True)
        
        df_gecmis.to_excel(EXCEL_GECMIS, index=False)
        print(f"✅ {bugun_str} tarihi için portföy kapanış değeri kaydedildi: ${toplam_varlik_usd:,.2f}")
        
    except Exception as e:
        print(f"Hata oluştu: {e}")

# İlk çalıştırmada hemen bir kayıt alalım
gun_sonu_portfoy_kaydet()

# Hafta içi her gün saat 23:30'da otomatik çalışır
schedule.every().day.at("23:30").do(gun_sonu_portfoy_kaydet)

print("⏳ Otomatik Takip Arka Plan Ajanı Başlatıldı... (Çıkmak için Ctrl+C)")

while True:
    schedule.run_pending()
    time.sleep(60)