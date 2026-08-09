import time
import os
import pandas as pd
import yfinance as yf
from datetime import datetime

# ==========================================
# 📂 PORTFÖY EXCEL DOSYASINI OKUMA VE DİNANİK LİSTE
# ==========================================
EXCEL_PATH = "portfoy_defteri_hisse.xlsx"

def portfoyden_varliklari_al():
    """Excel defterinden eldeki mevcut tüm varlıkları ve tiplerini tespit eder."""
    if not os.path.exists(EXCEL_PATH):
        print(f"⚠️ Hata: {EXCEL_PATH} bulunamadı!")
        return {}

    try:
        df = pd.read_excel(EXCEL_PATH, sheet_name="İşlemler")
        varliklar = df["Hisse Kodu"].dropna().unique().tolist()
        
        dinamik_takip = {
            "Altın (Ons)": {"sembol": "GC=F", "tip": "METALS"},
            "Dolar / TL": {"sembol": "USDTRY=X", "tip": "FOREX"},
            "Gram Altın (TL)": {"sembol": "HESAPLAMA", "tip": "HESAP"}
        }

        for v in varliklar:
            v_str = str(v).strip().upper()
            
            # Kripto tespiti
            if v_str in ["BTC", "ETH", "SOL", "AVAX", "XRP", "ADA"]:
                dinamik_takip[f"{v_str} (Kripto)"] = {"sembol": f"{v_str}-USD", "tip": "CRYPTO"}
            
            # TEFAS Fon tespiti (3 harfli ve .IS içermeyen özel fon kodları - Örn: TI2, MAC, TCD)
            elif len(v_str) == 3 and v_str.isalpha() and not v_str.endswith(".IS"):
                dinamik_takip[f"{v_str} (Yatırım Fonu)"] = {"sembol": f"{v_str}.IS", "tip": "FON"}
                
            # ABD Hisse tespiti (Örn: AAPL, NVDA, TSLA)
            elif len(v_str) <= 4 and not v_str.endswith(".IS") and not v_str.isalpha():
                dinamik_takip[f"{v_str} (ABD)"] = {"sembol": v_str, "tip": "US_STOCK"}
                
            # Borsa İstanbul Hisse tespiti (Örn: THYAO, EREGL)
            else:
                sadelestirilmis = v_str.replace(".IS", "")
                dinamik_takip[f"{sadelestirilmis} (BIST)"] = {"sembol": f"{sadelestirilmis}.IS", "tip": "BIST"}

        return dinamik_takip
    except Exception as e:
        print(f"⚠️ Excel okuma hatası: {e}")
        return {}

def anlik_fiyatlari_cek(takip_listesi):
    """Tüm varlık tiplerini uygun yöntemle canlı takibe alır."""
    yf_sembolleri = [v["sembol"] for v in takip_listesi.values() if v["sembol"] != "HESAPLAMA"]
    
    data = yf.Tickers(" ".join(yf_sembolleri))
    fiyat_tablosu = []
    
    ons_altin = None
    usd_try = None
    
    for etiket, detay in takip_listesi.items():
        sembol = detay["sembol"]
        varlik_tipi = detay["tip"]
        
        if sembol == "HESAPLAMA":
            continue
            
        try:
            ticker_obj = data.tickers[sembol]
            fiyat = ticker_obj.fast_info.get('lastPrice', None)
            onceki_kapanis = ticker_obj.fast_info.get('previousClose', None)
            
            if sembol == "GC=F": ons_altin = fiyat
            if sembol == "USDTRY=X": usd_try = fiyat
            
            if fiyat and onceki_kapanis:
                degisim = ((fiyat - onceki_kapanis) / onceki_kapanis) * 100
            else:
                degisim = 0.0
            
            # Etiket güncelleme (Fonlar için bilgi ekleme)
            durum_notu = f"%{degisim:+.2f}"
            if varlik_tipi == "FON":
                durum_notu += " (TEFAS Gün Sonu)"
                
            fiyat_tablosu.append({
                "Portföydeki Varlık": etiket,
                "Sembol / Kod": sembol,
                "Son Fiyat": round(fiyat, 2) if fiyat else "N/A",
                "Değişim / Durum": durum_notu
            })
        except Exception:
            fiyat_tablosu.append({
                "Portföydeki Varlık": etiket,
                "Sembol / Kod": sembol,
                "Son Fiyat": "N/A",
                "Değişim / Durum": "%0.00"
            })
            
    # Gram Altın Canlı Hesabı
    if ons_altin and usd_try:
        gram_altin = (ons_altin * usd_try) / 31.1035
        fiyat_tablosu.insert(0, {
            "Portföydeki Varlık": "Gram Altın (TL)",
            "Sembol / Kod": "CANLI HESAP",
            "Son Fiyat": round(gram_altin, 2),
            "Değişim / Durum": "Anlık Canlı"
        })
            
    return pd.DataFrame(fiyat_tablosu)

if __name__ == "__main__":
    print("🚀 Tam Teşekküllü Portföy Takip Ajanı (BIST, Kripto, Döviz, Fonlar)...")
    print("=" * 70)
    
    while True:
        takip_listesi = portfoyden_varliklari_al()
        zaman_damgasi = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        df = anlik_fiyatlari_cek(takip_listesi)
        
        print(f"\n⏱️  Son Güncelleme: {zaman_damgasi} | Takip Edilen Varlık Sayısı: {len(df)}")
        print("-" * 70)
        print(df.to_string(index=False))
        print("=" * 70)
        
        time.sleep(5)