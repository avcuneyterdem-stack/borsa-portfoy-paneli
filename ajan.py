#!/usr/bin/env python3
"""Portföy analisti ajanı.

Claude'a portföyü okuyabileceği araçlar verir ve açık uçlu soruları
yanıtlatır. Paneldeki diğer "ajan" adlı bölümlerden farkı: bu gerçekten
bir ajan — model hangi aracı ne zaman çağıracağına kendisi karar verir.

Güvenlik sınırı: BÜTÜN ARAÇLAR SALT-OKUNURDUR. Ajan defteri okuyabilir,
yazamaz; işlem giremez, silemez, düzeltemez. Bir dil modeline finansal
kayıt emanet etmemenin tek doğru yolu, yazma yolunu hiç açmamaktır.

ÜCRETLİDİR. Bu ajan Claude aboneliğinden değil, ayrı bir Claude Console
(API) hesabından çalışır ve kullandıkça ücretlendirilir. Kimlik doğrulama
`ant auth login` (Console hesabıyla giriş) veya ANTHROPIC_API_KEY ile
yapılır; ikisi de aynı faturaya gider. Yaklaşık maliyet için README'ye bakın.

Kullanım:
    python ajan.py "Portföyümde ne durumdayım?"
"""

from __future__ import annotations

import json
import logging
import sys

import pandas as pd

import piyasa
import portfoy_core as pc

kayitci = logging.getLogger(__name__)

EXCEL_HISSE = "portfoy_defteri_hisse.xlsx"
EXCEL_KRIPTO = "portfoy_defteri_kripto.xlsx"

MODEL = "claude-opus-5"
# Etki seviyesi maliyet/kota ile kalite arasındaki ana kol. "high" iyi bir
# başlangıç; bu iş yükünde "medium" ve "low" da şaşırtıcı derecede iyi
# sonuç veriyor ve belirgin biçimde daha az token harcıyor. Kendi
# sorularınızla deneyip düşürün.
ETKI = "high"
AZAMI_TOKEN = 16000

SISTEM_PROMPTU = """Kullanıcının kendi portföyünü analiz etmesine yardım eden bir asistansın.

Sayılar hakkında tek kuralın var: yalnızca araçlardan gelen rakamları kullan.
Bir sayıyı araçtan almadıysan söyleme — tahmin etme, hatırladığını sanma,
makul görünen bir değer uydurma. Veri gelmediyse "bu veri çekilemedi" de ve
neyin eksik olduğunu belirt.

Araç çıktılarındaki şu alanlara dikkat et ve kullanıcıya aktar:
- `fiyatsiz`: fiyatı çekilemeyen varlıklar. Bunlar toplamlara DAHİL DEĞİLDİR,
  yani toplam değer olduğundan düşük görünür. Varsa mutlaka söyle.
- `kur_eksik`: döviz kuru alınamadı. Bu durumda dolar bazlı rakamlar eksiktir.
- `uyarilar`: eşleşmeyen satış, tarihsel kuru olmayan satır gibi veri sorunları.

Yatırım tavsiyesi verme. Ne alınmalı, ne satılmalı, fiyat nereye gider gibi
sorulara "bu konuda tavsiye veremem" de; bunun yerine kullanıcının kendi
verisinde ne gördüğünü anlat ve kararı ona bırak.

Türkçe, kısa ve doğrudan yaz. Sorulmayan tabloları dökme."""


# ===========================================================================
# ARAÇLARIN ÇEKİRDEĞİ — saf Python, test edilebilir
# ===========================================================================

def _defterler():
    return pc.defter_oku(EXCEL_HISSE), pc.defter_oku(EXCEL_KRIPTO)


def portfoy_verisi():
    """Her iki defteri canlı fiyatlarla değerler."""
    hisse, kripto = _defterler()
    if hisse.empty and kripto.empty:
        return {"durum": "Portföy boş — henüz hiç işlem kaydedilmemiş."}
    return piyasa.portfoy_degerle(hisse, kripto)


def varlik_verisi(sembol):
    """Tek bir varlığın canlı fiyatı, günlük değişimi ve RSI'ı."""
    sembol = str(sembol).strip().upper()
    _, kripto = _defterler()
    kripto_mu = sembol in set(kripto["Hisse"]) if not kripto.empty else False

    if kripto_mu:
        veri = piyasa.kripto_fiyatlari([sembol]).get(sembol)
        if not veri:
            return {"sembol": sembol, "hata": "Binance fiyatı çekilemedi."}
        return {"sembol": sembol, "para_birimi": "USDT",
                "rsi_14": piyasa.kripto_rsi(sembol), **veri}

    kod = pc.sembol_normalize(sembol)
    veri = piyasa.hisse_fiyatlari([kod]).get(kod)
    if not veri:
        return {"sembol": kod, "hata": "Fiyat çekilemedi (sembol yanlış olabilir)."}
    return {"sembol": kod, "para_birimi": piyasa.sembol_meta(kod)["borsa_pb"], **veri}


def gecmis_verisi(sembol=None, tip=None, limit=50):
    """Defterlerden işlem kayıtları; en yeniden eskiye."""
    hisse, kripto = _defterler()
    defter = pd.concat([hisse, kripto], ignore_index=True)
    if defter.empty:
        return {"kayit_sayisi": 0, "kayitlar": []}

    if sembol:
        defter = defter[defter["Hisse"] == str(sembol).strip().upper()]
    if tip:
        hedef = {"AL": pc.AL, "SAT": pc.SAT, "GELIR": pc.GELIR}.get(str(tip).strip().upper())
        if hedef:
            defter = defter[defter["Tip"].map(pc.islem_tipi) == hedef]

    sirali, _ = pc.tarihe_gore_sirala(defter)
    sutunlar = ["Tarih", "Hisse", "Tip", "Fiyat", "Adet", "Para_Birimi"]
    kayitlar = sirali[sutunlar].iloc[::-1].head(max(1, int(limit)))
    return {"kayit_sayisi": len(sirali),
            "kayitlar": kayitlar.to_dict(orient="records")}


def kur_verisi():
    """Güncel döviz kurları (1 birimin TL karşılığı)."""
    return piyasa.kurlari_getir()


# ===========================================================================
# ARAÇ TANIMLARI — docstring'ler modelin okuduğu sözleşmedir
# ===========================================================================

def _araclari_kur():
    """Araçları geç bağlar; anthropic paketi yoksa modül yine de import edilir."""
    from anthropic import beta_tool

    @beta_tool
    def portfoy_ozeti() -> str:
        """Kullanıcının tüm portföyünü değerler ve tek seferde döndürür.

        Hisse ve kripto defterlerinin ikisini de kapsar. Dönen alanlar:
        maliyet_usd (tarihsel kurla sabitlenmiş dolar maliyeti), deger_usd
        (güncel piyasa değeri), gerceklesen_kz_usd (satışlardan realize kâr),
        gelir_usd (temettü + staking), kurlar, fiyatsiz (fiyatı çekilemeyen
        varlıklar — TOPLAMLARA DAHİL DEĞİL), kur_eksik, uyarilar.

        Portföy hakkındaki hemen her soru için önce bunu çağır.
        """
        return json.dumps(portfoy_verisi(), ensure_ascii=False, default=str)

    @beta_tool
    def varlik_detayi(sembol: str) -> str:
        """Tek bir varlığın canlı fiyatını, günlük değişimini ve RSI(14) değerini verir.

        Args:
            sembol: Hisse kodu (AAPL, THYAO, THYAO.IS) veya kripto sembolü (BTC, ETH).
                    Kripto defterinde kayıtlıysa Binance'ten, değilse Yahoo'dan çekilir.
        """
        return json.dumps(varlik_verisi(sembol), ensure_ascii=False, default=str)

    @beta_tool
    def islem_gecmisi(sembol: str = "", tip: str = "", limit: int = 50) -> str:
        """Defterlerdeki ham işlem kayıtlarını en yeniden eskiye döndürür.

        "Ne zaman aldım", "kaç kere işlem yaptım", "ortalama maliyetim nasıl
        oluştu" gibi sorular için kullan.

        Args:
            sembol: Tek bir varlıkla sınırlamak için kod. Boş bırakılırsa hepsi.
            tip: "AL", "SAT" veya "GELIR" (temettü/staking). Boş bırakılırsa hepsi.
            limit: Döndürülecek azami kayıt sayısı. Varsayılan 50.
        """
        return json.dumps(gecmis_verisi(sembol or None, tip or None, limit),
                          ensure_ascii=False, default=str)

    @beta_tool
    def kurlar() -> str:
        """Güncel döviz kurlarını döndürür: 1 birimin kaç TL ettiği.

        Değeri None olan para birimi çekilememiş demektir; o para birimini
        içeren hesaplar eksiktir.
        """
        return json.dumps(kur_verisi(), ensure_ascii=False, default=str)

    return [portfoy_ozeti, varlik_detayi, islem_gecmisi, kurlar]


# ===========================================================================
# AJAN DÖNGÜSÜ
# ===========================================================================

def sor(soru, model=MODEL, etki=ETKI):
    """Ajana bir soru sorar ve cevabı kullanım bilgisiyle birlikte döndürür.

    Döndürülen sözlük: cevap, girdi_token, cikti_token, arac_cagrilari, hata.
    İstisna fırlatmaz — hata durumunda `hata` alanı dolar, böylece panel
    çökmez.
    """
    sonuc = {"cevap": "", "girdi_token": 0, "cikti_token": 0,
             "arac_cagrilari": [], "hata": None}
    try:
        import anthropic
    except ImportError:
        sonuc["hata"] = ("`anthropic` paketi kurulu değil. Kurmak için: "
                         "pip install anthropic")
        return sonuc

    try:
        istemci = anthropic.Anthropic()
        calistirici = istemci.beta.messages.tool_runner(
            model=model,
            max_tokens=AZAMI_TOKEN,
            system=SISTEM_PROMPTU,
            output_config={"effort": etki},
            tools=_araclari_kur(),
            messages=[{"role": "user", "content": str(soru)}],
        )

        son_mesaj = None
        for mesaj in calistirici:
            son_mesaj = mesaj
            sonuc["girdi_token"] += mesaj.usage.input_tokens
            sonuc["cikti_token"] += mesaj.usage.output_tokens
            sonuc["arac_cagrilari"] += [
                blok.name for blok in mesaj.content if blok.type == "tool_use"
            ]

        if son_mesaj is None:
            sonuc["hata"] = "Modelden yanıt alınamadı."
        elif son_mesaj.stop_reason == "refusal":
            sonuc["hata"] = "Model bu isteği yanıtlamayı reddetti."
        else:
            sonuc["cevap"] = "".join(
                blok.text for blok in son_mesaj.content if blok.type == "text"
            )
    except anthropic.AuthenticationError:
        sonuc["hata"] = ("Claude Console kimliği bulunamadı. Bu bölüm ücretlidir: "
                         "platform.claude.com üzerinden kredi yüklü bir API hesabı "
                         "gerekir. Sonra `ant auth login` çalıştırın veya "
                         "ANTHROPIC_API_KEY tanımlayın.")
    except anthropic.RateLimitError:
        sonuc["hata"] = "Kullanım limitine takıldınız. Biraz bekleyip tekrar deneyin."
    except Exception as hata:  # noqa: BLE001 - kullanıcıya gösterilecek
        kayitci.exception("Ajan çağrısı başarısız")
        sonuc["hata"] = f"Beklenmeyen hata: {hata}"
    return sonuc


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cikti = sor(" ".join(sys.argv[1:]))
    if cikti["hata"]:
        print(f"HATA: {cikti['hata']}")
        return 1
    print(cikti["cevap"])
    print(f"\n[{cikti['girdi_token']:,} girdi + {cikti['cikti_token']:,} çıktı token"
          f" · araçlar: {', '.join(cikti['arac_cagrilari']) or 'yok'}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
