# Global Ajan Portföy Paneli

Hisse senedi ve kripto portföyünü dolar bazında takip eden Streamlit paneli.

## Kurulum ve çalıştırma

```bash
pip install -r requirements.txt
streamlit run app.py
```

Testler:

```bash
pytest -q          # 60 test
```

Yardımcı betikler:

```bash
python otomatik_takip.py               # gün sonu değerini bir kez kaydet
python otomatik_takip.py --surekli     # her gün 23:30'da (yerel kullanım)
python anlik_takip_ajani.py            # anlık tabloyu bir kez yazdır
python anlik_takip_ajani.py --surekli --aralik 60
```

## Dosya düzeni

| Dosya | Sorumluluk |
|---|---|
| `portfoy_core.py` | Saf hesap katmanı: para çevrimi, pozisyon/K-Z hesabı, RSI, şema, dayanıklı dosya yazımı. Streamlit ve ağ erişimi içermez. |
| `app.py` | Arayüz, disk erişimi ve piyasa verisi çekimi. |
| `test_portfoy_core.py` | Çekirdeğin birim testleri. |
| `piyasa.py` | Ağ katmanı: kurlar, hisse/kripto fiyatları. Streamlit içermez. |
| `otomatik_takip.py` | Gün sonu portföy değerini `portfoy_gecmisi.xlsx`'e yazan bot. |
| `anlik_takip_ajani.py` | Terminal tabanlı anlık takip betiği. |
| `test_otomatik_takip.py` | Botun testleri (ağ erişimi olmadan). |

Ayrım kasıtlıdır: para hesaplarındaki hatalar panelde "makul görünen ama yanlış"
rakamlar olarak çıkar ve gözle fark edilmez. Bu yüzden hesabın tamamı ağ
erişimi olmadan test edilebilir bir modülde durur.

## Defter şeması ve geçiş

Defterler `portfoy_defteri_hisse.xlsx` ve `portfoy_defteri_kripto.xlsx`
dosyalarında tutulur. Şemaya üç sütun eklendi:

| Sütun | Anlamı |
|---|---|
| `Islem_Kuru` | İşlem anında, girilen para biriminin TL karşılığı |
| `Islem_USDTRY` | İşlem anındaki USD/TRY kuru |
| `Borsa_PB` / `Borsa` | Varlığın kote edildiği para birimi ve borsa |

**Geçiş otomatiktir**, dosyanızı elle düzenlemeniz gerekmez. Eski kayıtlarda:

- **Dolar cinsinden işlemler kesin kalır.** Dolar maliyeti kur gerektirmez.
- **TL/EUR/GBP cinsinden eski işlemler** için tarihsel kur kayıtta yoktur;
  bugünkü kurla yaklaşıklanır ve panelde *"N kayıtta işlem anındaki kur
  bulunamadı"* uyarısı gösterilir. Doğru rakam istiyorsanız o satırların
  `Islem_USDTRY` hücresine alım günündeki kuru yazmanız yeterlidir.

Excel'e kendi eklediğiniz sütunlar korunur.

## Bu sürümde düzeltilenler

**Para hesabı**

- Dolar maliyeti artık işlem anındaki kurla sabitlenir. Önceki sürüm tarihsel
  TL tutarı bugünkü kura bölüyordu; bu yüzden dolarla yapılmış bir alımın
  dolar maliyeti bile her gün değişiyordu.
- Canlı fiyat, varlığın kendi para biriminden dolara çevrilir (TRY, EUR, GBP
  ve diğerleri). Londra'nın pens (GBp) kotasyonu ayrıca 100'e bölünür.
- Borsa para birimi kayıt anında dondurulmaz; her açılışta canlı bilgiden
  çözülür. Eski davranışta, veri çekilemediği bir anda kaydedilen BIST
  hissesi kalıcı olarak `USD` işaretlenip pozisyonu ~34 kat şişiriyordu.
- Kur veya fiyat çekilemediğinde tahmini değer üretilmez; satır `N/A` kalır
  ve toplamlara girmez.

**Veri güvenliği**

- Yazma sırası: geçici dosyaya yaz → geri okuyup satır sayısını doğrula →
  mevcut dosyayı zaman damgalı yedeğe al → yerine taşı. Son 10 yedek tutulur.
- Okuma hatası alınan deftere yazma kilitlenir (aksi hâlde boş dönen bir
  okuma tüm geçmişi tek satırla silebiliyordu).
- Eşzamanlı yazımı engelleyen dosya kilidi; süreç çökerse 30 sn sonra düşer.

**İşlem mantığı**

- Satış, hem kayıt sırasında hem hesapta doğrulanır. Eşleşmeyen satışlar
  sessizce atlanmaz, sayılır ve kullanıcıya bildirilir.
- Kayıtlar tarihe göre sıralanarak işlenir; tarihi okunamayan satırlar
  raporlanır.
- Mükerrer kayıt koruması eklendi.
- Kripto tarafı da tam pozisyon özeti, K/Z ve RSI üretir; hisse ile birleşik
  toplam panelin üstünde gösterilir.

**Diğer**

- Temettü verimi `yıllık temettü ÷ fiyat` ile hesaplanır. Yalnızca ham
  `dividendYield` varsa ölçek tahmin edilmez; ham değer olduğu gibi gösterilir.
- RSI Wilder yumuşatmasıyla hesaplanır.
- Fiyatlar toplu çekilir ve önbelleklenir (kur 300 sn, hisse 180 sn, kripto 120 sn).
- Sistem sekmesi yalnızca gerçek ölçüm gösterir; sabit "başarılı" metni yoktur.
- TradingView sembolleri temizlenir ve borsa öneki uydurulmaz.
- İşlem saatleri `Europe/Istanbul` saat diliminde kaydedilir.

## Bilinen sınır: kalıcılık ve çok kullanıcı

Defterler sunucudaki Excel dosyalarında tutulur. Bu, **Streamlit Cloud gibi
ortamlarda iki soruna açıktır**:

1. Dosya sistemi geçicidir — yeniden dağıtımda defterler silinir.
2. Tüm ziyaretçiler aynı defteri paylaşır; birbirinin kayıtlarını görüp
   silebilir.

Dosya kilidi yalnızca tek makinedeki eşzamanlı yazımı çözer, bu iki sorunu
çözmez. Kişisel veya çok kullanıcılı gerçek kullanım için kimlik doğrulamalı
bir veritabanına (ör. kullanıcı bazlı SQLite veya harici DB) geçilmelidir.
O zamana kadar yan menüdeki **Excel indir** düğmelerini düzenli kullanın.

## Yardımcı betikler

Her ikisi de artık `portfoy_core` üzerinden hesap yapar ve kendi kur
matematiğini taşımaz. Varsayılan olarak **bir kez çalışıp çıkarlar**;
sürekli çalışma `--surekli` ile açılır.

`otomatik_takip.py`, USD/TRY kuru çekilemediğinde **hiçbir şey kaydetmez**.
Önceki sürüm bu durumda sabit `34.0` varsayıp yanlış bir geçmiş yazıyordu;
eksik gün, yanlış günden iyidir. Fiyatı alınamayan varlıklar `Fiyatsiz_Varlik`
ve `Not` sütunlarına yazılır, böylece geçmişteki her satırın ne kadar eksik
olduğu sonradan görülebilir.

## GitHub Actions

`.github/workflows/testler.yml` her push'ta testleri ve `pyflakes` taramasını
çalıştırır.

Gecelik bot bilerek CI'dan çıkarıldı. Sebebi teknik bir tercih değil, veriyle
ilgili: defterler `.gitignore` ile hariç tutulduğu için CI checkout'unda
**hiçbir portföy verisi yoktur** — bot orada hesaplayacak bir şey bulamaz.
Verinin depoya konması ise portföy geçmişini depoyu görebilen herkese açardı.
Bot bu yüzden yerelde (veya verinin bulunduğu özel bir makinede)
`--surekli` ile çalıştırılmalıdır.

## Yatırım tavsiyesi değildir

Panel yalnızca kayıt ve görselleştirme aracıdır. Fiyatlar gecikmeli olabilir.
