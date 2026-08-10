"""İzleme listesi ve alarmlar — kalıcı JSON dosyaları.

İzleme listesi, elinde olmayan ama göstergelerine bakmak istediğin
sembollerdir. Deftere karışmaz: defter para hesabının kaynağıdır, izleme
listesi yalnızca bir görüntüleme tercihidir. İkisini karıştırmak, alınmamış
bir hissenin portföy değerine girmesi demek olurdu.

Alarm, bir sembole bağlanmış bir kuraldır (`indikator` kural motoru). Sinyal
tablosuyla aynı motoru kullanır; farkı, tetiklendiğinde tarih damgası
tutması ve aynı durumu her yenilemede yeniden bildirmemesidir.

Yazma atomiktir: geçici dosyaya yazılır, sonra `os.replace` ile yerine
konur. Yarıda kesilen bir yazma, listeyi bozuk JSON'a çevirmez.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
import uuid

import indikator as ind

kayitci = logging.getLogger(__name__)

IZLEME_DOSYA = "izleme_listesi.json"
ALARM_DOSYA = "alarmlar.json"

TURLER = ("hisse", "kripto")


# --- Ortak dosya işlemleri --------------------------------------------------

def _oku(dosya, varsayilan):
    """JSON okur. Dosya yoksa varsayılanı, bozuksa uyarı verip varsayılanı."""
    if not os.path.exists(dosya):
        return varsayilan
    try:
        with open(dosya, encoding="utf-8") as akis:
            return json.load(akis)
    except (json.JSONDecodeError, OSError) as hata:
        kayitci.error("%s okunamadı (%s); boş kabul ediliyor.", dosya, hata)
        return varsayilan


def _yaz(dosya, veri):
    """Atomik yazar: geçici dosya → os.replace."""
    gecici = f"{dosya}.tmp"
    with open(gecici, "w", encoding="utf-8") as akis:
        json.dump(veri, akis, ensure_ascii=False, indent=2)
    os.replace(gecici, dosya)


# --- İzleme listesi ---------------------------------------------------------

def liste_oku(dosya=IZLEME_DOSYA):
    """İzleme listesi: [{"sembol": ..., "tur": "hisse"|"kripto"}, ...]"""
    ham = _oku(dosya, [])
    if not isinstance(ham, list):
        return []
    return [k for k in ham
            if isinstance(k, dict) and k.get("sembol") and k.get("tur") in TURLER]


def sembol_ekle(sembol, tur, dosya=IZLEME_DOSYA):
    """Listeye sembol ekler. Hata mesajı veya None döner."""
    sembol = str(sembol).strip().upper()
    if not sembol:
        return "Sembol boş olamaz."
    if tur not in TURLER:
        return f"Tür 'hisse' veya 'kripto' olmalı, '{tur}' değil."

    liste = liste_oku(dosya)
    if any(k["sembol"] == sembol for k in liste):
        return f"{sembol} zaten listede."
    liste.append({"sembol": sembol, "tur": tur})
    _yaz(dosya, liste)
    return None


def sembol_sil(sembol, dosya=IZLEME_DOSYA):
    """Listeden siler. Bulunamazsa sessizce geçer."""
    sembol = str(sembol).strip().upper()
    liste = [k for k in liste_oku(dosya) if k["sembol"] != sembol]
    _yaz(dosya, liste)


def turlere_ayir(liste):
    """İzleme listesini (hisseler, kriptolar) demetine böler."""
    hisseler = [k["sembol"] for k in liste if k["tur"] == "hisse"]
    kriptolar = [k["sembol"] for k in liste if k["tur"] == "kripto"]
    return hisseler, kriptolar


# --- Alarmlar ---------------------------------------------------------------

def alarm_oku(dosya=ALARM_DOSYA):
    """Alarmlar: [{"id", "sembol", "kural", "aktif", "son_tetik"}, ...]"""
    ham = _oku(dosya, [])
    if not isinstance(ham, list):
        return []
    gecerli = []
    for alarm in ham:
        if not isinstance(alarm, dict) or "kural" not in alarm:
            continue
        if ind.kural_gecerli_mi(alarm["kural"]) is not None:
            kayitci.warning("Geçersiz alarm kuralı atlandı: %s", alarm.get("id"))
            continue
        gecerli.append(alarm)
    return gecerli


def alarm_ekle(sembol, kural, dosya=ALARM_DOSYA):
    """Alarm ekler. Hata mesajı veya None döner."""
    sembol = str(sembol).strip().upper()
    if not sembol:
        return "Sembol boş olamaz."
    sorun = ind.kural_gecerli_mi(kural)
    if sorun is not None:
        return sorun

    alarmlar = alarm_oku(dosya)
    alarmlar.append({
        "id": uuid.uuid4().hex[:8],
        "sembol": sembol,
        "kural": kural,
        "aktif": True,
        "son_tetik": None,
    })
    _yaz(dosya, alarmlar)
    return None


def alarm_sil(alarm_id, dosya=ALARM_DOSYA):
    _yaz(dosya, [a for a in alarm_oku(dosya) if a.get("id") != alarm_id])


def alarm_durum_degistir(alarm_id, aktif, dosya=ALARM_DOSYA):
    alarmlar = alarm_oku(dosya)
    for alarm in alarmlar:
        if alarm.get("id") == alarm_id:
            alarm["aktif"] = bool(aktif)
    _yaz(dosya, alarmlar)


def alarmlari_degerlendir(paket, dosya=ALARM_DOSYA, simdi=None):
    """Aktif alarmları gösterge paketine uygular; tetiklenenleri döndürür.

    `paket`: {sembol: indikator.gostergeler() çıktısı}

    Tetiklenen alarmın `son_tetik` damgası güncellenir. Damga yalnızca kayıt
    içindir; alarm koşul sağlandığı sürece her yenilemede bildirilir. Bir kez
    bildirip susmak, kullanıcı paneli o an açık değilse uyarıyı tamamen
    kaybettirirdi.
    """
    simdi = simdi or dt.datetime.now()
    alarmlar = alarm_oku(dosya)
    tetiklenen = []
    degisti = False

    for alarm in alarmlar:
        if not alarm.get("aktif", True):
            continue
        olculer = paket.get(alarm["sembol"])
        if olculer is None:
            continue
        if ind.kural_degerlendir(alarm["kural"], olculer) is True:
            alarm["son_tetik"] = simdi.strftime("%Y-%m-%d %H:%M")
            degisti = True
            tetiklenen.append({
                "id": alarm["id"],
                "sembol": alarm["sembol"],
                "kural_adi": alarm["kural"]["ad"],
                "yon": alarm["kural"]["yon"],
                "deger": olculer.get(alarm["kural"]["gosterge"]),
            })

    if degisti:
        _yaz(dosya, alarmlar)
    return tetiklenen


# --- Kendi kuralların -------------------------------------------------------
# Sinyal tablosu ve alarmlar bu listeyi kullanır. Varsayılan kurallar koda
# gömülüdür ve silinemez; ama `varsayilanlari_kullan` ile toptan kapatılabilir,
# böylece yalnızca kendi kurallarınla çalışabilirsin.

KURAL_DOSYA = "kurallar.json"


def _bos_kural_ayari():
    """Her çağrıda yeni sözlük + yeni liste.

    Modül düzeyinde sabit bir sözlük tutup `dict(...)` ile kopyalamak sığ
    kopya üretir: içindeki liste paylaşılır ve `kural_ekle` sabiti kalıcı
    olarak kirletir. Fabrika fonksiyonu bu tuzağı tamamen kapatır.
    """
    return {"varsayilanlari_kullan": True, "kurallar": []}


def kural_ayarlari_oku(dosya=KURAL_DOSYA):
    """{"varsayilanlari_kullan": bool, "kurallar": [...]} döndürür.

    Geçersiz kurallar sessizce elenmez, uyarı yazılır: kullanıcı kuralını
    tanımladığını sanıp sinyal beklerken hiç değerlendirilmemesi kötü olur.
    """
    ham = _oku(dosya, _bos_kural_ayari())
    if not isinstance(ham, dict):
        return _bos_kural_ayari()

    kurallar = []
    for kural in ham.get("kurallar", []) or []:
        sorun = ind.kural_gecerli_mi(kural)
        if sorun is None:
            kurallar.append(kural)
        else:
            kayitci.warning("Geçersiz kural atlandı (%s): %s",
                            (kural or {}).get("ad", "?") if isinstance(kural, dict) else "?", sorun)
    return {
        "varsayilanlari_kullan": bool(ham.get("varsayilanlari_kullan", True)),
        "kurallar": kurallar,
    }


def kural_oku(dosya=KURAL_DOSYA):
    """Yalnızca kullanıcının kendi tanımladığı kurallar."""
    return kural_ayarlari_oku(dosya)["kurallar"]


def kural_ekle(kural, dosya=KURAL_DOSYA):
    """Kural ekler. Hata mesajı veya None döner."""
    sorun = ind.kural_gecerli_mi(kural)
    if sorun is not None:
        return sorun

    ayarlar = kural_ayarlari_oku(dosya)
    mevcut_adlar = {k["ad"] for k in ayarlar["kurallar"]}
    mevcut_adlar |= {k["ad"] for k in ind.VARSAYILAN_KURALLAR}
    if kural["ad"] in mevcut_adlar:
        return f"'{kural['ad']}' adında bir kural zaten var."

    ayarlar["kurallar"].append(kural)
    _yaz(dosya, ayarlar)
    return None


def kural_sil(ad, dosya=KURAL_DOSYA):
    """Kendi kuralını siler. Varsayılan kurallar silinemez."""
    ayarlar = kural_ayarlari_oku(dosya)
    ayarlar["kurallar"] = [k for k in ayarlar["kurallar"] if k["ad"] != ad]
    _yaz(dosya, ayarlar)


def varsayilan_kullanimi_degistir(kullan, dosya=KURAL_DOSYA):
    """Varsayılan kural setini toptan açar/kapatır."""
    ayarlar = kural_ayarlari_oku(dosya)
    ayarlar["varsayilanlari_kullan"] = bool(kullan)
    _yaz(dosya, ayarlar)


def etkin_kurallar(dosya=KURAL_DOSYA):
    """Sinyal tablosunun ve alarm menüsünün kullandığı kural listesi.

    Hepsi kapatılmışsa boş liste döner; çağıran taraf bunu "kural yok" diye
    göstermelidir, "hiçbir sinyal yok" diye değil.
    """
    ayarlar = kural_ayarlari_oku(dosya)
    temel = list(ind.VARSAYILAN_KURALLAR) if ayarlar["varsayilanlari_kullan"] else []
    return temel + ayarlar["kurallar"]


# --- Toplu ekleme -----------------------------------------------------------
# Boş bir listeyi tek tek formla doldurmak yorucu; asıl engel bu. Toplu
# ekleme, mevcut tekil fonksiyonların üstüne kurulur — doğrulama tek yerde
# kalsın diye kendi kuralını yazmaz.

def sembol_toplu_ekle(metin, tur, dosya=IZLEME_DOSYA):
    """Virgül, boşluk veya satırla ayrılmış sembolleri ekler.

    Döner: {"eklenen": [...], "atlanan": {sembol: sebep}}
    Bir sembolün reddedilmesi diğerlerini durdurmaz; kullanıcı hangisinin
    neden girmediğini görmeli, hepsi birden sessizce kaybolmamalı.
    """
    parcalar = [p.strip().upper() for p in re.split(r"[,\s;]+", str(metin or "")) if p.strip()]
    eklenen, atlanan = [], {}
    for sembol in parcalar:
        if sembol in eklenen or sembol in atlanan:
            continue
        sorun = sembol_ekle(sembol, tur, dosya)
        if sorun:
            atlanan[sembol] = sorun
        else:
            eklenen.append(sembol)
    return {"eklenen": eklenen, "atlanan": atlanan}


def alarm_var_mi(sembol, kural_adi, dosya=ALARM_DOSYA):
    """Aynı sembol için aynı kural zaten tanımlı mı?"""
    sembol = str(sembol).strip().upper()
    return any(a["sembol"] == sembol and a["kural"]["ad"] == kural_adi
               for a in alarm_oku(dosya))


def alarm_toplu_ekle(semboller, kurallar, dosya=ALARM_DOSYA):
    """Her sembol × her kural için alarm kurar; var olanları atlar.

    Döner: {"eklenen": n, "atlanan": n}
    Aynı alarmın ikinci kez kurulması engellenir, yoksa düğmeye iki kez
    basmak uyarıları ikiye katlar.
    """
    eklenen = atlanan = 0
    for sembol in semboller:
        for kural in kurallar:
            if alarm_var_mi(sembol, kural["ad"], dosya):
                atlanan += 1
                continue
            if alarm_ekle(sembol, kural, dosya) is None:
                eklenen += 1
            else:
                atlanan += 1
    return {"eklenen": eklenen, "atlanan": atlanan}
