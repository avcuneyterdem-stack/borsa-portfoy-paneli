# TradingView Pine betiği

`portfoy_sinyal_motoru.pine`, panelin `indikator.py` dosyasındaki kural
motorunun TradingView karşılığıdır. Aynı göstergeler, aynı varsayılan eşikler,
aynı puanlama.

## Neden ikisi birden?

Panel ve Pine farklı şeyleri biliyor; biri diğerinin yerine geçmiyor.

| | Panel | Pine |
|---|---|---|
| Portföyünü bilir (maliyet, adet, K/Z) | ✅ | ❌ yalnızca grafikteki sembolü görür |
| Tüm varlıkların tek tabloda | ✅ | ❌ grafik başına tek sembol |
| Mumların üstüne çizer | ❌ | ✅ |
| **Bilgisayar kapalıyken alarm** | ❌ | ✅ TradingView sunucusunda çalışır |
| Geçmişe dönük görsel inceleme | ❌ | ✅ |
| Ücret | tamamen ücretsiz | ücretsiz katmanda indikatör ve alarm sayısı sınırlı |

Kalın satır önemli: panelin alarmı ancak panel veya `anlik_takip_ajani.py`
açıkken çalışır. Kendi bilgisayarında çalışan bir program, bilgisayar
kapalıyken çalışamaz. Pine bu boşluğu kapatır.

## Kurulum

1. <https://tradingview.com> adresinde bir grafik aç (ücretsiz hesap yeter).
2. Ekranın altındaki **Pine Editor** sekmesine tıkla.
3. Editördeki örnek kodu sil, `portfoy_sinyal_motoru.pine` içeriğini yapıştır.
4. **Save** → bir ad ver.
5. **Add to chart**.

Grafikte belirenler: kısa/uzun SMA çizgileri, Bollinger bantları, yön
değişiminde AL/SAT üçgenleri ve sağ üstte özet tablosu (RSI, MACD histogramı,
%B, AL/SAT sayısı, puan).

Ayarları değiştirmek için indikatör adının yanındaki dişli simgesine tıkla.

## Alarm kurma

1. Grafiğe sağ tık → **Alarm ekle** (veya üstteki saat simgesi).
2. **Koşul** bölümünde betiğin adını seç.
3. Alt menüden hangi olayı istediğini seç:
   - `Puan AL yönüne geçti` / `Puan SAT yönüne geçti` — birleşik sinyal
   - `RSI aşırı satım` / `RSI aşırı alım`
   - `MACD yukarı kesişim` / `MACD aşağı kesişim`
   - `Altın kesişim` / `Ölüm kesişimi`
   - `Alt Bollinger bandı` / `Üst Bollinger bandı`
4. Bildirim yolunu seç (uygulama bildirimi, e-posta) ve kaydet.

Alarm TradingView'in sunucusunda çalışır — bilgisayarın kapalı olsa da gelir.
Ücretsiz hesapta aynı anda tutulabilecek alarm sayısı sınırlıdır.

## Panelle aynı kalması

`test_pine_uyum.py` bu dosyayı metin olarak okuyup varsayılanlarını Python
tarafındakilerle karşılaştırır: RSI eşikleri, MACD periyotları, Bollinger
ayarları, kesişim penceresi, kural sayısı ve puan formülü.

Birinde eşik değiştirip diğerinde unutursan test düşer. Bu bilinçli: iki
sistemin sessizce ayrışması, grafikte AL panelde nötr görmek demektir ve o
noktada ikisine de güvenemezsin.

Eşik değiştirmek istersen ikisini birlikte değiştir:

| Değer | Python | Pine |
|---|---|---|
| RSI eşikleri | `indikator.VARSAYILAN_KURALLAR` | `rsiAsiriSat` / `rsiAsiriAl` |
| RSI periyodu | `portfoy_core.wilder_rsi(periyot=…)` | `rsiPeriyot` |
| MACD | `indikator.macd(hizli, yavas, sinyal_periyot)` | `macdHizli` / `macdYavas` / `macdSinyalLen` |
| Bollinger | `indikator.bollinger(periyot, sapma)` | `bbPeriyot` / `bbSapma` |
| Kesişim penceresi | `indikator.kesisim(bakilacak_bar=…)` | `bakilacakBar` |

## Bilinen sınırlar

- **Paneldeki gömülü TradingView grafiği bu betiği çalıştıramaz.** Sekme 3'teki
  widget, TradingView'in genel gömme aracıdır ve kullanıcıya ait Pine
  betiklerini yükleyemez. Pine'ı tradingview.com'da kendi hesabında kullan.
- Pine portföyünü görmez. "En çok nerede zarardayım" gibi sorular panelin işi.
- Betik tek indikatör yuvası kullanır (ücretsiz hesapta yuva sınırlıdır); bu
  yüzden RSI ve MACD ayrı pencerelere çizilmez, değerleri tabloda okunur.
- Sürüm satırı `//@version=6`. TradingView eski bir sürüm isterse bu satırı
  `//@version=5` yapmak yeterlidir; kullanılan fonksiyonların tamamı iki
  sürümde de aynıdır.

> **Yatırım tavsiyesi değildir.** Puan, senin tanımladığın kuralların
> sayımıdır; ağırlıkları yoktur ve geleceği bilmez.
