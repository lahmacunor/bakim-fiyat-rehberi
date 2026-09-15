"""Kia periyodik bakim fiyat tablosunu resmi PDF'lerden cekip JSON'a cevirir.

Kaynak: Kia Turkiye'nin "Tavsiye Edilen Periyodik Bakim Fiyat Tablosu" PDF'leri.
Iki ayri dosya var: ICE (benzin/dizel/hibrit) ve EV (elektrikli). Dosya adi
yayin tarihini tasidigi icin (ICE-...-2026-09-15.pdf) baglantilar bakim
sayfasindan okunuyor; elle URL guncellemek gerekmiyor.

Fiyatlar KDV dahil, markanin kendi yayinladigi tavsiye fiyatlardir.

Kullanim:  python cek/kia.py
"""
import json
import re
import sys
import urllib.request

from pathlib import Path

import pdfplumber

sys.stdout.reconfigure(encoding="utf-8")

KAYNAK_SAYFA = "https://www.kia.com/tr/kia-sahipleri/servis-ve-bakim/bakim.html"
PDF_KOK = "https://www.kia.com"

KOK = Path(__file__).resolve().parent.parent
HEDEF = KOK / "veri" / "kia"

BASLIK = "/content/dam/kwcms/tr/tr/files/servis-merkezi/bakim/"
PDF_BAG = re.compile(
    re.escape(BASLIK) + r"(ICE|EV)-Periyodik-Bakim-Fiyat-Tablosu-(\d{4})-(\d{2})-\d{2}\.pdf"
)

# "17.375 ₺" -- binlik ayraci ve TL isareti zorunlu, motor hacmiyle (1.6)
# ve km basligiyla (15.000, isaretsiz) karismaz.
FIYAT = re.compile(r"^\d{1,3}(?:\.\d{3})+$")
KM = re.compile(r"^\d{2,3}\.000$")
# "2015 - 2020", "2023-…", "2024"
YIL = re.compile(r"((?:19|20)\d{2})\s*[-–]\s*((?:19|20)\d{2}|…|\.\.\.)|((?:19|20)\d{2})")

SATIR_TOL = 3.0  # ayni gorsel satir sayilan dikey sapma (satir araligi ~7.3 pt)


def yakit_bul(motor):
    """Yakit turu motor-vites hucresinde yaziyor ("2.0 DİZEL OTOMATİK").

    Turkce buyuk İ yuzunden upper()/lower() ile karsilastirma yapilmiyor;
    PDF bu kelimeleri her zaman buyuk harfle yaziyor, dogrudan araniyor.
    """
    elektrik = "ELEKTR" in motor
    dizel = "DİZEL" in motor or "DSL" in motor or "CRDI" in motor or "CRDİ" in motor
    hibrit = "HİBRİT" in motor or "HEV" in motor  # MHEV/PHEV de bunun icinde
    if elektrik and not hibrit:
        return "elektrik"
    if dizel:
        return "dizel-hibrit" if hibrit else "dizel"
    if hibrit:
        return "benzin-hibrit"
    if "BENZİN" in motor or "GDI" in motor or "GDİ" in motor:
        return "benzin"
    return "bilinmiyor"


def sanziman_bul(motor):
    if "DÜZ VİTES" in motor or "MANUEL" in motor:
        return "DÜZ VİTES"
    if "OTOMATİK" in motor or "DCT" in motor or "CVT" in motor:
        return "OTOMATİK"
    return ""


def yil_yaz(ham):
    """ "2015 - 2020" -> "2015~2020",  "2023-…" -> "2023~",  "2024" -> "2024" """
    m = YIL.search(ham)
    if not m:
        return ""
    bas, son, tek = m.groups()
    if tek:
        return tek
    return f"{bas}~" + (son if son and son[0].isdigit() else "")


def satirlara_bol(kelimeler):
    """Kelimeleri gorsel satirlara kumeler, yukaridan asagi siralar."""
    satirlar = []
    for k in sorted(kelimeler, key=lambda k: (k["top"], k["x0"])):
        if satirlar and abs(k["top"] - satirlar[-1][0]) <= SATIR_TOL:
            satirlar[-1][1].append(k)
        else:
            satirlar.append([k["top"], [k]])
    return [(y, sorted(ks, key=lambda k: k["x0"])) for y, ks in satirlar]


def sutunlar(baslik_kelimeleri):
    """Baslik satirindan sutun x sinirlarini ve km listesini cikarir.

    Baslik: "MODEL | MODEL YILI | MOTOR - VİTES KUTUSU | 15.000 | 30.000 | ..."
    ICE ve EV dosyalari farkli x ofsetleri kullandigi icin sinirlar sabit
    yazilmiyor, her sayfada basliktan okunuyor.
    """
    ks = baslik_kelimeleri
    metin = [k["text"] for k in ks]
    # Baslik satiri bazen model adiyla basliyor (" STINGER MODEL YILI ...").
    # "MODEL" sayisina bakilirsa boyle bir satir veri sanilip km basliklari
    # fiyat olarak okunuyordu; ayirt edici kelimeler YILI ve KUTUSU.
    if "YILI" not in metin or "KUTUSU" not in metin:
        return None
    motor = next((k for k in ks if k["text"] == "MOTOR"), None)
    kmler = [(k["x0"], int(k["text"].replace(".", ""))) for k in ks if KM.match(k["text"])]
    if motor is None or not kmler:
        return None
    onceki = ks[metin.index("YILI") - 1]  # "MODEL YILI" -- sutun MODEL'de basliyor
    return {
        "yil_x": onceki["x0"],
        "motor_x": motor["x0"],
        "km": kmler,
    }


def hucreler(kelimeler, s):
    """Satirdaki kelimeleri sutunlara dagitir."""
    model, yil, motor, fiyat = [], [], [], []
    for k in kelimeler:
        x, t = k["x0"], k["text"]
        if t == "₺":
            continue
        if x < s["yil_x"] - 5:
            model.append(t)
        elif x < s["motor_x"] - 5:
            yil.append(t)
        elif x < s["km"][0][0] - 8:
            motor.append(t)
        elif FIYAT.match(t):
            # Fiyati x'e en yakin km sutununa esle; eksik hucre kaymaya yol acmasin.
            km = min(s["km"], key=lambda c: abs(c[0] - x))[1]
            fiyat.append((km, int(t.replace(".", ""))))
    return " ".join(model), " ".join(yil), " ".join(motor), fiyat


def modelleri_dagit(bloklar):
    """Model adi birlestirilmis hucrede: grubun ortasina yazili, ustteki
    satirda degil.  Ornek (SPORTAGE SLE, 3 satir):

        y=180   2011 - 2016  1.6 BENZİNLİ DÜZ VİTES   ...
        y=187   SPORTAGE SLE
        y=188   2011 - 2016  1.6 BENZİNLİ OTOMATİK    ...
        y=195   2011 - 2016  2.0 DİZEL OTOMATİK       ...

    Etiket ortalandigi icin grubun son satiri  2*y_etiket - y_ilk  oluyor.
    Satir sayisindan (tek/cift) gitmek yetmiyor -- Ceed blogunda yaniltiyor --
    bu yuzden gercek y koordinati kullaniliyor.
    """
    for satirlar in bloklar:
        etiketler = [(y, ad) for y, ad, *_ in satirlar if ad]
        veri = [s for s in satirlar if s[4]]  # fiyati olan satirlar
        if not etiketler or not veri:
            continue
        i = 0
        for sira, (ey, ad) in enumerate(etiketler):
            if i >= len(veri):
                break
            bas = veri[i][0]
            son = 2 * ey - bas
            # Son etiket blogun kalanini alir: cift satirli grupta etiket iki
            # orta satirdan birine dusuyor, bu da yarim satirlik sapma yapiyor.
            kalan = sira == len(etiketler) - 1
            while i < len(veri) and (kalan or veri[i][0] <= son + SATIR_TOL):
                veri[i][1] = ad
                i += 1
        for s in veri:
            if not s[1]:
                print(f"  ! modelsiz satir: {s[2]} {s[3]}", file=sys.stderr)


def sayfayi_isle(sayfa, kaynak_url, kaynak_tarih):
    bloklar, blok, s = [], None, None
    for y, ks in satirlara_bol(sayfa.extract_words()):
        yeni = sutunlar(ks)
        if yeni:  # baslik satiri -> yeni blok
            s = yeni
            blok = []
            bloklar.append(blok)
            continue
        if s is None or blok is None:
            continue
        model, yil, motor, fiyat = hucreler(ks, s)
        if not fiyat and not model:
            continue  # dipnot / bilgi satiri
        blok.append([y, model, yil, motor, fiyat])

    modelleri_dagit(bloklar)

    kayitlar = []
    for blok in bloklar:
        for y, model, yil, motor, fiyat in blok:
            if not fiyat or not model or not motor:
                continue
            for km, tutar in fiyat:
                kayitlar.append({
                    "marka": "Kia",
                    "model": " ".join(model.split()),
                    "model_yili": yil_yaz(yil),
                    "motor": " ".join(motor.split()),
                    "sanziman": sanziman_bul(motor),
                    "yakit": yakit_bul(motor),
                    "bakim_km": km,
                    "fiyat_tl": tutar,
                    "kdv_dahil": True,
                    "kaynak_url": kaynak_url,
                    "kaynak_tarih": kaynak_tarih,
                })
    return kayitlar


def pdf_baglantilari():
    istek = urllib.request.Request(KAYNAK_SAYFA, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(istek, timeout=60) as yanit:
        sayfa = yanit.read().decode("utf-8", "replace")
    bulunan = {}
    for m in PDF_BAG.finditer(sayfa):
        bulunan[m.group(1)] = (PDF_KOK + m.group(0), f"{m.group(2)}-{m.group(3)}")
    if not bulunan:
        sys.exit(f"bakim sayfasinda PDF baglantisi bulunamadi: {KAYNAK_SAYFA}")
    return bulunan


def main():
    HEDEF.mkdir(parents=True, exist_ok=True)
    kayitlar, tarihler = [], []

    for tur, (url, tarih) in sorted(pdf_baglantilari().items()):
        tarihler.append(tarih)
        pdf_yolu = HEDEF / f"kaynak-{tur.lower()}-{tarih}.pdf"
        if not pdf_yolu.exists():
            print(f"indiriliyor: {url}")
            istek = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(istek, timeout=60) as yanit:
                pdf_yolu.write_bytes(yanit.read())
        with pdfplumber.open(str(pdf_yolu)) as pdf:
            for sayfa in pdf.pages:
                kayitlar += sayfayi_isle(sayfa, url, tarih)
        print(f"{tur}: {pdf_yolu.name} ({pdf_yolu.stat().st_size // 1024} KB)")

    json_yolu = HEDEF / f"{max(tarihler)}.json"
    json_yolu.write_text(
        json.dumps(kayitlar, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    modeller = {(k["model"], k["motor"]) for k in kayitlar}
    print(f"{len(kayitlar)} fiyat satiri, {len(modeller)} model-motor -> {json_yolu}")


if __name__ == "__main__":
    main()
