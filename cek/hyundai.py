"""Hyundai periyodik bakim fiyat tablosunu resmi PDF'ten cekip JSON'a cevirir.

Kaynak: Hyundai Turkiye'nin aylik yayinladigi "Periyodik Bakim Fiyat Tablosu" PDF'i.
Fiyatlar KDV dahil, markanin kendi yayinladigi tavsiye fiyatlardir.

Kullanim:  python cek/hyundai.py
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

from pypdf import PdfReader

sys.stdout.reconfigure(encoding="utf-8")

KAYNAK_URL = (
    "https://www.hyundai.com/content/dam/hyundai/downloads/tr/tr/"
    "periyodik-bakim-fiyatlari/periyodik-bakim-tablosu-eylul-2026.pdf"
)
KAYNAK_TARIH = "2026-09"

KOK = Path(__file__).resolve().parent.parent
HEDEF = KOK / "veri" / "hyundai"

# "10.472" / "1.234" bicimindeki TL tutari. Motor hacmi (1.6) ve km (15.000)
# ile karismasin diye binlik ayraci ZORUNLU ve tam 3 hane.
FIYAT = re.compile(r"\d{1,3}\.\d{3}")
# "2023~", "2015~2018", "2022" -- model yili.
# Bitis yili tildeye BITISIK olmali: "2021~ 1.6 ..." satirinda tilde sonrasi
# motor hacmidir, yil degil.
YIL = re.compile(r"(?:19|20)\d{2}~(?:(?:19|20)\d{2})?|\b(?:19|20)\d{2}\b")

# Sayfa basligindaki kategori -> yakit tipi
YAKIT = [
    ("elektrikli", "elektrik"),
    ("benzinli hibrit", "benzin-hibrit"),
    ("dizel hibrit", "dizel-hibrit"),
    ("dizel", "dizel"),
    ("benzinli", "benzin"),
]


def yakit_bul(baslik):
    b = baslik.lower()
    for anahtar, deger in YAKIT:
        if anahtar in b:
            return deger
    return "bilinmiyor"


def km_sutunlari(satir):
    """Baslik satirindan bakim araliklarini cikarir.

    "Model Model yili Motor 15.000 30.000 ..." -> [15000, 30000, ...]
    Sayfadan sayfaya degisiyor (8 veya 12 sutun, 10.000'lik veya 15.000'lik).
    """
    return [int(s.replace(".", "")) for s in FIYAT.findall(satir)]


def satirlari_birlestir(satirlar):
    """PDF'te model ve motor adlari satir sonunda kirilabiliyor:

        "1.6 T-GDI SMART-"
        "STREAM GAMMA II 17.697 19.485 ..."

    Hic fiyat tasimayan satiri sonrakiyle birlestirir. Olcut "sutun sayisi
    kadar fiyat" DEGIL: ticari arac tablosunda bazi satirlarda 5.000 km hucresi
    bos (13 sutun, 12 fiyat) ve o satirlar sonrakiyle birlestirilip veriyi
    bozuyordu. Satir sonundaki tire kirilma isaretidir, atilir ve bosluksuz eklenir.
    """
    cikti, tampon = [], ""
    for ham in satirlar:
        s = ham.strip()
        if not s:
            continue
        if tampon:
            s = tampon[:-1] + s if tampon.endswith("-") else tampon + " " + s
            tampon = ""
        if FIYAT.search(s):
            cikti.append(s)
        else:
            tampon = s
    if tampon:
        cikti.append(tampon)
    return cikti


def on_kismi_coz(on, baglam_model, baglam_yil):
    """Fiyatlardan onceki metni model / model yili / motor olarak ayirir.

    Uc bicim var:
      "ELANTRA (CN7) 2021~ 1.6 SMARTSTREAM"  -> model + yil + motor, hepsi burada
      "2015~2018 1.6 T-GDI"                  -> yil + motor, model ustteki basliktan
      "1.0 T-GDI KAPPA"                      -> sadece motor, model+yil basliktan
    """
    m = YIL.search(on)
    if m:
        model = on[: m.start()].strip(" -–") or baglam_model
        return model, m.group().replace(" ", ""), on[m.end():].strip()
    return baglam_model, baglam_yil, on.strip()


def sayfayi_isle(metin):
    satirlar = metin.splitlines()
    baslik = satirlar[0] if satirlar else ""
    if "periyodik bakım fiyatları" not in baslik.lower():
        return []

    # Sutun basligi: icinde "Model" gecen ve km listesi tasiyan satir
    basluk_idx = next(
        (i for i, s in enumerate(satirlar) if "Model" in s and len(FIYAT.findall(s)) >= 4),
        None,
    )
    if basluk_idx is None:
        return []

    kmler = km_sutunlari(satirlar[basluk_idx])
    yakit = yakit_bul(baslik)
    govde = [s for s in satirlar[basluk_idx + 1:] if "KDV" not in s]

    kayitlar = []
    baglam_model, baglam_yil = "", ""
    for satir in satirlari_birlestir(govde):
        bulunanlar = list(FIYAT.finditer(satir))
        if len(bulunanlar) < len(kmler) - 2:
            # Fiyatsiz satir = model basligi ("İ20 (BC3) FL 2023~")
            if bulunanlar:
                print(f"  ! eksik fiyatli satir atlandi: {satir[:70]}", file=sys.stderr)
            m = YIL.search(satir)
            if m:
                baglam_model = satir[: m.start()].strip() or baglam_model
                baglam_yil = m.group().replace(" ", "")
            else:
                baglam_model = satir.strip()
            continue

        # Fiyatlar satirin sonunda; sondan len(kmler) tanesini al.
        # Konumu eslesmeden okuyoruz -- ayni sayi on kisimda da gecebilir.
        alinan = bulunanlar[-len(kmler):]
        on = satir[: alinan[0].start()]

        model, yil, motor = on_kismi_coz(on, baglam_model, baglam_yil)
        if not model or not motor:
            continue
        baglam_model, baglam_yil = model, yil

        # Eksik hucre satirin BASINDA oluyor (5.000 km yalniz bazi modellerde
        # var), bu yuzden fiyatlar sona hizalanarak km ile eslestiriliyor.
        for km, eslesme in zip(kmler[-len(alinan):], alinan):
            tutar = eslesme.group()
            kayitlar.append({
                "marka": "Hyundai",
                "model": model.strip(),
                "model_yili": yil,
                "motor": " ".join(motor.split()),
                "yakit": yakit,
                "bakim_km": km,
                "fiyat_tl": int(tutar.replace(".", "")),
                "kdv_dahil": True,
                "kaynak_url": KAYNAK_URL,
                "kaynak_tarih": KAYNAK_TARIH,
            })
    return kayitlar


def main():
    HEDEF.mkdir(parents=True, exist_ok=True)
    pdf_yolu = HEDEF / f"kaynak-{KAYNAK_TARIH}.pdf"

    if not pdf_yolu.exists():
        print(f"indiriliyor: {KAYNAK_URL}")
        istek = urllib.request.Request(KAYNAK_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(istek, timeout=60) as yanit:
            pdf_yolu.write_bytes(yanit.read())
    print(f"pdf: {pdf_yolu} ({pdf_yolu.stat().st_size // 1024} KB)")

    kayitlar = []
    for sayfa in PdfReader(str(pdf_yolu)).pages:
        kayitlar += sayfayi_isle(sayfa.extract_text() or "")

    json_yolu = HEDEF / f"{KAYNAK_TARIH}.json"
    json_yolu.write_text(
        json.dumps(kayitlar, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    modeller = {(k["model"], k["motor"]) for k in kayitlar}
    print(f"{len(kayitlar)} fiyat satiri, {len(modeller)} model-motor -> {json_yolu}")


if __name__ == "__main__":
    main()
