# Windows'ta adım adım kurulum

Bu dosya, paneli ve portföy asistanını kendi bilgisayarında ilk kez çalıştırmak
içindir. Adımları sırayla uygula; her adımın sonunda ne görmen gerektiği yazıyor.

Komutları **PowerShell**'de çalıştır (Başlat → "PowerShell" yaz → aç).
Önce proje klasörüne gir — klasör yolun farklıysa onu yaz:

```powershell
cd $HOME\Desktop\borsa-portfoy-paneli
```

---

## 1. Güncel kodu al

```powershell
git pull
```

Beklenen: `ajan.py`, `piyasa.py`, `KURULUM_WINDOWS.md` gibi dosyaların indiğini
gösteren bir liste. "Already up to date" görürsen de sorun yok.

## 2. Bağımlılıkları kur

```powershell
pip install -r requirements.txt
```

Yeni olan paket `anthropic` — asistanın Claude'a bağlanmasını sağlayan kütüphane.
Beklenen: en sonda `Successfully installed ...` satırı.

## 3. Testleri çalıştır (kod sağlam mı)

```powershell
pytest -q
```

Beklenen: `73 passed`. Bu adım internet gerektirmez; geçerse kodun kendi
matematiği doğru çalışıyor demektir.

## 4. `ant` aracını indir

Asistanın Claude hesabınla giriş yapabilmesi için gereken küçük bir program.

1. Tarayıcıda aç: <https://github.com/anthropics/anthropic-cli/releases>
2. En üstteki sürümün altındaki **Assets** listesinden
   `ant_<sürüm>_windows_amd64.zip` dosyasını indir.
3. Zip'i aç, içindeki `ant.exe` dosyasını **proje klasörüne** kopyala
   (yani `app.py` ile aynı yere).

`.gitignore` içinde `*.exe` olduğu için bu dosya depoya gitmez, merak etme.

Kontrol:

```powershell
.\ant.exe --version
```

Beklenen: bir sürüm numarası. "tanınmıyor" hatası alırsan `ant.exe` yanlış
klasörde demektir.

## 5. Claude hesabınla giriş yap

```powershell
.\ant.exe auth login
```

Tarayıcı açılır, Claude hesabınla onay verirsin. Kimlik bilgisi bilgisayarında
saklanır; kodun içine hiçbir şey yazılmaz.

## 6. API anahtarı değişkenini kontrol et

```powershell
echo $env:ANTHROPIC_API_KEY
```

Beklenen: **boş satır**. Eğer bir değer yazıyorsa, o değişken 5. adımdaki
profili ezer ve kullandıkça ücretlendirilen yola geçersin. Aboneliğinden
gitmesini istiyorsan o oturumda temizle:

```powershell
Remove-Item Env:\ANTHROPIC_API_KEY
```

## 7. Asistanı önce terminalde dene

```powershell
python ajan.py "Portföyümde ne durumdayım?"
```

Terminalde denemenin sebebi: hata çıkarsa mesajı burada net görünür, panelin
içinde kaybolmaz.

Beklenen: Türkçe bir özet ve en altta köşeli parantez içinde token sayısı ile
çağrılan araçların listesi.

Sık görülen çıktılar:

| Mesaj | Anlamı |
|---|---|
| `pip install anthropic` uyarısı | 2. adım eksik veya başka bir Python kullanılıyor |
| "Claude kimliği bulunamadı" | 5. adım tamamlanmamış |
| "Portföy boş" | Defter dosyaları henüz bu klasörde değil |
| "fiyat çekilemedi" | İnternet/sağlayıcı sorunu; rakam uydurulmaz, eksik olan söylenir |

## 8. Paneli aç

```powershell
streamlit run app.py
```

Tarayıcıda panel açılır. **Sekme 5 → Portföy Asistanı** altında aynı soruyu
kutuya yazıp sorabilirsin.

---

## Bilinmesi gerekenler

**Veri nereye gidiyor?** Asistana soru sorduğun anda portföy verilerin
(pozisyonlar, maliyetler, kâr/zarar) Anthropic API'sine gider. Soru sormadığın
sürece panel hiçbir veriyi dışarı göndermez.

**Asistan defteri değiştirebilir mi?** Hayır. Bütün araçları salt-okunurdur:
okur, yazamaz. İşlem giremez, kayıt silemez. Bu bir tasarım sınırıdır ve
`test_ajan.py` içindeki bir testle korunur.

**Maliyet.** `ant auth login` profiliyle ek ödeme çıkmaz; kullanım Claude
aboneliğinin kotasından düşer. Daha az token harcamak istersen `ajan.py`
içindeki `ETKI = "high"` satırını `"medium"` yap.

**Claude Code de kurarsan.** Claude Code ile `ant` kimlik bilgilerini aynı yerde
saklar. İkisini birlikte kurarsan biri diğerinin oturumunu düşürebilir; böyle
bir uyarı görürsen hangisini tutacağına karar verip diğerinde yeniden giriş yap.
