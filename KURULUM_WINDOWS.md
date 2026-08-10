# Windows'ta adım adım kurulum

Bu dosya, paneli kendi bilgisayarında ilk kez çalıştırmak içindir. Adımları
sırayla uygula; her adımın sonunda ne görmen gerektiği yazıyor.

**1–4. adımlar hiçbir ücret gerektirmez.** Panelin altı sekmesi (portföy,
işlem girişi, grafikler, temettü, anlık takip, denetim) bunlarla çalışır.
Sonundaki *Portföy asistanı* bölümü isteğe bağlıdır ve **ücretlidir** —
istemiyorsan hiç kurma.

Komutları **PowerShell**'de çalıştır. En kolay yol: VS Code'da klasörü açıp
**Terminal → New Terminal** demek; terminal doğru klasörde açılır. Alternatif:
`Windows tuşu` + `R` → `powershell` → Enter, sonra klasöre gir:

```powershell
cd $HOME\Desktop\borsa-portfoy-paneli
```

---

## 1. Güncel kodu al

```powershell
git pull
```

Beklenen: indirilen dosyaların listesi ya da "Already up to date".

> Git bir dosyayı silemediğini söylerse (`Deletion of directory ... failed`),
> o dosya VS Code'da açıktır. `n` yazıp Enter'a bas, **File → Close All
> Editors** yap, sonra `git pull` komutunu tekrarla.

## 2. Bağımlılıkları kur

```powershell
pip install -r requirements.txt
```

Beklenen: en sonda `Successfully installed ...` satırı. ("pip tanınmıyor"
derse `python -m pip install -r requirements.txt` kullan.)

## 3. Testleri çalıştır (kod sağlam mı)

```powershell
pytest -q
```

Beklenen: `73 passed`. Bu adım internet gerektirmez; geçerse kodun para
hesapları doğru çalışıyor demektir.

## 4. Paneli aç

```powershell
streamlit run app.py
```

Tarayıcıda panel açılır. Kapatmak için terminalde `Ctrl+C`.

Kurulum burada biter. Aşağısı yalnızca asistanı da istersen gereklidir.

---

# İsteğe bağlı: Portföy asistanı (ÜCRETLİDİR)

Sekme 5'teki asistan, portföyün hakkında serbest soru sormanı sağlar. Ama:

> **Bu bölüm Claude aboneliğinden çalışmaz.** Ayrı bir **Claude Console (API)**
> hesabı gerektirir ve kullandıkça ücretlendirilir. `ant auth login` de,
> `ANTHROPIC_API_KEY` de aynı faturaya gider — ücretsiz bir yolu yoktur.
>
> **Maliyet:** Claude Opus 5 için milyon girdi token'ı 5 $, milyon çıktı
> token'ı 25 $. Bu asistanda soru başına kabaca **0,10–0,15 $**.
> `ajan.py` içindeki `ETKI` sabitini `"medium"`/`"low"` yapmak veya `MODEL`'i
> `claude-sonnet-5` yapmak maliyeti belirgin biçimde düşürür.
>
> Ödeme yapmak istemiyorsan bu bölümü atla. Panelin geri kalanı asistan
> olmadan sorunsuz çalışır; Sekme 5'e girmediğin sürece hiçbir istek gitmez.

## A. Console hesabı aç ve kredi yükle

<https://platform.claude.com> → **Individual** → hesabı oluştur → faturalandırma
bölümünden kredi yükle (genelde en az 5 $).

## B. `ant` aracını indir

Terminalde (sürüm numarasını güncel sürümle değiştir):

```powershell
Invoke-WebRequest -Uri "https://github.com/anthropics/anthropic-cli/releases/download/v1.22.1/ant_1.22.1_windows_amd64.zip" -OutFile ant.zip
Expand-Archive ant.zip -DestinationPath . -Force
Remove-Item ant.zip, completions, man -Recurse -Force
```

Kontrol: `.\ant.exe --version` bir sürüm numarası yazmalı. `ant.exe` depoya
gitmez — `.gitignore` içinde `*.exe` var.

## C. Giriş yap

```powershell
.\ant.exe auth login
```

Tarayıcıda Console hesabınla onay verirsin.

## D. Terminalde dene

```powershell
python ajan.py "Portföyümde ne durumdayım?"
```

Terminalde denemenin sebebi: hata çıkarsa mesajı burada net görünür.

| Mesaj | Anlamı |
|---|---|
| `pip install anthropic` uyarısı | 2. adım eksik veya başka bir Python kullanılıyor |
| "Claude Console kimliği bulunamadı" | A veya C adımı tamamlanmamış |
| "Portföy boş" | Defter dosyaları henüz bu klasörde değil |
| "fiyat çekilemedi" | İnternet/sağlayıcı sorunu; rakam uydurulmaz, eksik olan söylenir |

---

## Bilinmesi gerekenler

**Vazgeçmek istersen.** `ant.exe` dosyasını sil ve Console hesabındaki kartı
kaldır. Panelin diğer sekmeleri etkilenmez.

**Veri nereye gidiyor?** Yalnızca asistana soru sorduğunda: portföy verilerin
(pozisyonlar, maliyetler, kâr/zarar) Anthropic API'sine gider. Asistanı
kullanmadığın sürece panel hiçbir veriyi dışarı göndermez.

**Asistan defteri değiştirebilir mi?** Hayır. Bütün araçları salt-okunurdur:
okur, yazamaz. İşlem giremez, kayıt silemez. Bu bir tasarım sınırıdır ve
`test_ajan.py` içindeki bir testle korunur.

**Claude Code de kurarsan.** Claude Code ile `ant` kimlik bilgilerini aynı yerde
saklar. İkisini birlikte kurarsan biri diğerinin oturumunu düşürebilir; böyle
bir uyarı görürsen hangisini tutacağına karar verip diğerinde yeniden giriş yap.
