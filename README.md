# Global Ajan Portföy Paneli

Hisse senedi ve kripto portföyünü dolar bazında takip eden Streamlit paneli.

## Kurulum ve çalıştırma

Windows'ta ilk kez kuruyorsan adım adım anlatım: [KURULUM_WINDOWS.md](KURULUM_WINDOWS.md).

```bash
pip install -r requirements.txt
streamlit run app.py
```

Testler:

```bash
pytest -q          # 73 test
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
| `piyasa.py` | Ağ katmanı: kurlar, hisse/kripto fiyatları, gösterge geçmişi. Streamlit içermez. |
| `indikator.py` | Teknik göstergeler (RSI, MACD, SMA, Bollinger) ve kural motoru. Saf matematik: ağ, dosya, streamlit yok. |
| `izleme.py` | İzleme listesi ve alarmların kalıcılığı (JSON, atomik yazım). |
| `test_indikator.py` | Gösterge matematiğinin testleri. |
| `test_izleme.py` | İzleme listesi ve alarm testleri. |
| `pine/portfoy_sinyal_motoru.pine` | Kural motorunun TradingView karşılığı (bkz. `pine/README.md`). |
| `test_pine_uyum.py` | Pine betiği ile Python motorunun aynı eşikleri kullandığını doğrular. |
| `otomatik_takip.py` | Gün sonu portföy değerini `portfoy_gecmisi.xlsx`'e yazan bot. |
| `anlik_takip_ajani.py` | Terminal tabanlı anlık takip betiği. |
| `ajan.py` | Portföy asistanı: Claude'a salt-okunur araçlar verip serbest soru yanıtlatır. |
| `test_otomatik_takip.py` | Botun testleri (ağ erişimi olmadan). |
| `test_ajan.py` | Asistanın testleri (API çağrısı olmadan). |

Ayrım kasıtlıdır: para hesaplarındaki hatalar panelde "makul görünen ama yanlış"
rakamlar olarak çıkar ve gözle fark edilmez. Bu yüzden hesabın tamamı ağ
erişimi olmadan test edilebilir bir modülde durur.

## İndikatörler (Sekme 7)

Panelin yedinci sekmesi portföyündeki ve izleme listendeki varlıklar için
teknik göstergeleri tek tabloda toplar. Tamamı ücretsizdir — veri Yahoo
Finance ve Binance'ten gelir, hesap kendi bilgisayarında yapılır.

| Gösterge | Ayar | Not |
|---|---|---|
| RSI | Wilder(14) | TradingView ile aynı yöntem (basit ortalama değil) |
| MACD | 12 / 26 / 9 | Çizgi, sinyal, histogram ve son 5 bardaki kesişim |
| Hareketli ortalama | SMA 50 ve 200 | Altın/ölüm kesişimi ve fiyatın SMA200'e göre yeri |
| Bollinger | 20 bar, 2σ | %B: fiyatın bantlar içindeki göreli yeri (0 alt, 1 üst) |

**Veri yetmezse gösterge boş kalır.** 200 günlük ortalama 200 kapanış ister;
yeni listelenen bir hissede bu sütun `N/A` görünür. 150 barlık veriyi "200
günlük ortalama" diye sunmak sessizce yanlış sinyal üretirdi.

### Sinyal tablosu ve kural motoru

Sekmedeki **Sinyal** sütunu, `indikator.VARSAYILAN_KURALLAR` içindeki sekiz
kuralın kaçının tetiklendiğini sayar (RSI eşikleri, MACD kesişimi, altın/ölüm
kesişimi, Bollinger uçları). **Puan** = tetiklenen AL sayısı − tetiklenen SAT
sayısı.

Kuralların ağırlığı yoktur ve hiçbiri diğerinden değerli sayılmaz. Bu bir
tavsiye değil, kendi kurallarının sayımıdır — bilinçli olarak böyle sade
tutuldu, çünkü ağırlıklı bir skor "sistem biliyor" hissi verir ama dayanağı
olmaz.

### Kendi kuralların

Sekmedeki **Kendi kuralların** bölümünden kendi eşiklerini tanımlayabilirsin:
bir gösterge, bir karşılaştırma, bir eşik ve bir yön. Kural adı otomatik
türetilir (`RSI(14) < 40 → AL`), hem sinyal tablosunda hem alarm menüsünde
belirir ve `kurallar.json` içinde saklanır.

Arayüz göstergenin türüne uyar: kesişim göstergesine yön (`▲ yukarı` /
`▼ aşağı`), mantıksal göstergeye doğru/yanlış, sayısal göstergeye eşik sorar.
Anlamsız birleşimler kurulamaz — `SMA50/SMA200 kesişimi > 1` gibi bir kural
motor tarafından reddedilir, çünkü kesişim bir sayı değildir.

Varsayılan 8 kural koda gömülüdür ve silinemez, ama bir onay kutusuyla toptan
kapatılabilir; o zaman yalnızca kendi kuralların değerlendirilir.

| Gösterge | Tür | Kurulabilecek kural |
|---|---|---|
| RSI(14), Fiyat, SMA50, SMA200, MACD çizgisi, MACD histogramı, Bollinger %B | sayı | `< eşik` veya `> eşik` |
| MACD kesişimi, SMA50/SMA200 kesişimi | kesişim | `▲ yukarı` veya `▼ aşağı` |
| Fiyat SMA200 üzerinde | doğru/yanlış | `= doğru` veya `= yanlış` |

### İzleme listesi

Elinde olmayan ama takip ettiğin semboller `izleme_listesi.json` içinde
tutulur ve deftere karışmaz — portföy değerine, maliyete, K/Z hesabına
girmez. Panelden eklenip silinir.

### Alarmlar

Bir varlık seçtiğin koşula geldiğinde uyarı çıkar. Alarmlar
`alarmlar.json` içinde tutulur ve sinyal tablosuyla **aynı kural motorunu**
kullanır — alarm, bir sembole bağlanmış bir kuraldır, ayrı bir mekanizma
değildir.

Alarm iki yerde çalışır:

```bash
streamlit run app.py                     # panel açıkken sekmenin üstünde
python anlik_takip_ajani.py --surekli    # panel kapalıyken terminalde
```

Terminal betiği göstergeleri 15 dakikada bir tazeler (günlük mumla çalışır,
her 60 saniyede 1 yıllık geçmiş indirmenin anlamı yok) ve yalnızca alarmı olan
sembollerin geçmişini indirir. `--alarmsiz` ile kapatılabilir.

Koşul sağlandığı sürece her yenilemede bildirilir; bir kez uyarıp susmaz.
Susmak, o an ekrana bakmıyorsan uyarıyı tamamen kaybettirirdi.

### TradingView (Pine) tarafı

`pine/portfoy_sinyal_motoru.pine`, bu kural motorunun TradingView karşılığıdır:
aynı göstergeler, aynı varsayılan eşikler, aynı puanlama. Kurulum ve alarm
adımları `pine/README.md` içinde.

Tek sebebi var: **panelin alarmı ancak panel açıkken çalışır.** Pine alarmı
TradingView'in sunucusunda çalıştığı için bilgisayarın kapalıyken de bildirim
gelir. Buna karşılık Pine portföyünü görmez — hangi varlıktan kaça aldığını
yalnızca panel bilir.

`test_pine_uyum.py` iki tarafın eşiklerini karşılaştırır; birinde değiştirip
diğerinde unutursan test düşer. İki sistemin sessizce ayrışması, grafikte AL
panelde nötr görmek demektir.

> **Yatırım tavsiyesi değildir.** Teknik göstergeler geçmiş fiyat hareketinin
> matematiksel özetidir; geleceği bilmezler.

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

## Kullanım biçimi: tek kullanıcı, yerel

Bu panel **tek kişinin kendi bilgisayarında** çalışması için tasarlanmıştır.
Bu varsayım altında Excel dosyaları yeterlidir: kalıcıdırlar, kimse
paylaşmaz, eşzamanlı yazan ikinci bir oturum yoktur.

Yedek sizin sorumluluğunuzdadır. Panel her kayıtta son 10 sürümü yedekler,
ama hepsi aynı klasörde durur — disk giderse hepsi gider. Yan menüdeki
**Excel indir** düğmelerini ara sıra kullanıp dosyaları başka bir yere kopyalayın.

**Streamlit Cloud'a koymayın.** Orada iki sorun doğar: dosya sistemi
geçicidir (yeniden dağıtımda defterler silinir) ve tüm ziyaretçiler aynı
defteri paylaşır. Buluta taşımak gerekirse önce kimlik doğrulamalı bir
veritabanına (kullanıcı bazlı SQLite veya harici DB) geçilmelidir; asistan da
o durumda `ant` profiliyle değil, API anahtarıyla çalışmak zorundadır.

## Portföy asistanı (isteğe bağlı — ÜCRETLİDİR)

Sekme 5'teki asistana portföyünüz hakkında serbest soru sorabilirsiniz —
"ne durumdayım", "en çok nerede zarardayım", "THYAO'yu ne zaman aldım" gibi.
Komut satırından da çalışır:

```bash
python ajan.py "Portföyümde ne durumdayım?"
```

> **Ücret uyarısı.** Bu bölüm **Claude aboneliğinden çalışmaz.** Ayrı bir
> **Claude Console (API)** hesabı gerektirir ve kullandıkça ücretlendirilir —
> `ant auth login` de, `ANTHROPIC_API_KEY` de aynı faturaya gider.
> Ödeme yapmak istemiyorsanız bu bölümü kurmayın: panelin diğer altı sekmesi
> asistan olmadan sorunsuz çalışır ve hiçbir ücret gerektirmez.

**Kurulum — bir kez.** <https://platform.claude.com> üzerinde bir Console
hesabı açıp kredi yükleyin. Sonra
[anthropic-cli](https://github.com/anthropics/anthropic-cli/releases)
sayfasından `ant` dosyasını indirip:

```bash
ant auth login
```

Tarayıcı açılır, Console hesabınızla giriş yaparsınız. Kimlik bilgisi
bilgisayarınızda saklanır; kodda API anahtarı tutulmaz.

**Maliyet.** Claude Opus 5 için milyon girdi token'ı 5 $, milyon çıktı token'ı
25 $. Bu asistanda bir soru sistem promptu, araç tanımları, portföy verisi ve
modelin düşünmesiyle birlikte kabaca 15.000 girdi + 2.000 çıktı token tüketir —
**soru başına yaklaşık 0,10–0,15 $**. İki ayar kolu var, ikisi de `ajan.py`
içinde: `ETKI` sabitini `"medium"` veya `"low"` yapmak, ve `MODEL`'i
`claude-sonnet-5` yapmak (3 $ / 15 $ — kabaca yarı fiyat). Bu iş yükünde her
ikisi de kaliteyi belirgin biçimde düşürmez.

**Gizlilik.** Soru sorduğunuzda portföy verileriniz Anthropic API'sine gider.
Soru sormadığınız sürece panel hiçbir veriyi dışarı göndermez.

**Güvenlik sınırı.** Asistanın bütün araçları salt-okunurdur: defteri okur,
yazamaz. İşlem giremez, kayıt silemez, düzeltemez. Bu bir tasarım kararıdır ve
`test_ajan.py` içindeki bir testle korunur.

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
