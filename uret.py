"""veri/ altindaki JSON'lardan statik site uretir.  Calistir:  python uret.py

Cikti site/ altina yazilir, GitHub Pages oradan yayinlar.
Framework yok, build step yok -- sablon doldurup dosya yaziyoruz.
"""
import html
import json
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from string import Template

sys.stdout.reconfigure(encoding="utf-8")

KOK = Path(__file__).resolve().parent
# GitHub Pages yalnizca depo kokunu veya docs/ klasorunu yayinliyor,
# keyfi bir alt klasoru (site/) yayinlayamiyor -- cikti bu yuzden docs/.
CIKTI = KOK / "docs"
SABLON = Template((KOK / "sablon" / "sayfa.html").read_text(encoding="utf-8"))

TR_ASCII = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")

# GitHub Pages proje adresi. Domain alinirsa burasi degisir.
SITE_ADRES = "https://lahmacunor.github.io/bakim-fiyat-rehberi/"

AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
         "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def tarih_yaz(kod):
    """"2026-05" -> "Mayıs 2026" """
    yil, ay = kod.split("-")
    return f"{AYLAR[int(ay) - 1]} {yil}"


def slug(metin):
    m = metin.translate(TR_ASCII).lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", m)).strip("-")


def model_adi(ham):
    """PDF'te ayni model bazen "İ20", bazen "i20" yaziliyor. Hyundai'nin resmi
    yazimi kucuk i ile ("i20", "ix35"); bastaki İ'yi ona ceviriyoruz ki ayni
    arac iki ayri sayfaya bolunmesin."""
    return re.sub(r"^İ(?=\d|[xX]\d)", "i", ham.strip())


def tl(sayi):
    return f"{sayi:,}".replace(",", ".") + " TL"


def tablo(kayitlar):
    """Satirlar = bakim araligi, sutunlar = motor secenekleri."""
    motorlar = sorted({k["motor"] for k in kayitlar})
    kmler = sorted({k["bakim_km"] for k in kayitlar})
    fiyatlar = {(k["motor"], k["bakim_km"]): k["fiyat_tl"] for k in kayitlar}

    bas = "".join(f"<th>{html.escape(m)}</th>" for m in motorlar)
    satirlar = []
    for km in kmler:
        hucre = "".join(
            f"<td>{tl(fiyatlar[(m, km)]) if (m, km) in fiyatlar else '—'}</td>"
            for m in motorlar
        )
        km_yazi = f"{km:,}".replace(",", ".")
        satirlar.append(f"<tr><th>{km_yazi} km</th>{hucre}</tr>")

    toplam = "".join(
        f"<td>{tl(sum(fiyatlar[(m, k)] for k in kmler if (m, k) in fiyatlar))}</td>"
        for m in motorlar
    )
    son_km = f"{max(kmler):,}".replace(",", ".")
    return (
        f'<div class="kaydir"><table><thead><tr><th>Bakım aralığı</th>{bas}</tr></thead>'
        f'<tbody>{"".join(satirlar)}</tbody>'
        f'<tfoot><tr><th>{son_km} km\'ye kadar toplam</th>{toplam}</tr></tfoot>'
        "</table></div>"
    )


def sayfa_yaz(yol, baslik, aciklama, icerik, derinlik):
    hedef = CIKTI / yol
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(
        SABLON.substitute(
            baslik=html.escape(baslik),
            aciklama=html.escape(aciklama),
            icerik=icerik,
            kok="../" * derinlik or "./",
        ),
        encoding="utf-8",
    )


def main():
    kayitlar = []
    for dosya in sorted((KOK / "veri").glob("*/[0-9]*.json")):
        kayitlar += json.loads(dosya.read_text(encoding="utf-8"))
    for k in kayitlar:
        k["model"] = model_adi(k["model"])
    print(f"{len(kayitlar)} fiyat satiri okundu")

    if CIKTI.exists():
        shutil.rmtree(CIKTI)
    CIKTI.mkdir()
    shutil.copy(KOK / "sablon" / "stil.css", CIKTI / "stil.css")

    # marka -> model -> kayitlar
    agac = defaultdict(lambda: defaultdict(list))
    for k in kayitlar:
        agac[k["marka"]][k["model"]].append(k)

    yollar = []
    for marka, modeller in sorted(agac.items()):
        ms = slug(marka)
        for model, mk in sorted(modeller.items()):
            yol = f"{ms}/{slug(model)}/index.html"
            yollar.append(yol)
            kaynak = mk[0]
            yillar = sorted({k["model_yili"] for k in mk})
            yakitlar = sorted({k["yakit"] for k in mk})

            bolumler = []
            for yil in yillar:
                yk = [k for k in mk if k["model_yili"] == yil]
                for yakit in sorted({k["yakit"] for k in yk}):
                    yyk = [k for k in yk if k["yakit"] == yakit]
                    bolumler.append(
                        f"<h2>{html.escape(model)} {html.escape(yil)}"
                        f" <span class='etiket'>{yakit}</span></h2>{tablo(yyk)}"
                    )

            sayfa_yaz(
                yol,
                f"{marka} {model} Bakım Fiyatları — {tarih_yaz(kaynak['kaynak_tarih'])}",
                f"{marka} {model} periyodik bakım fiyatları — {', '.join(yillar)} "
                f"model, {', '.join(yakitlar)}. {marka}'nin resmi fiyat tablosundan.",
                f"<h1>{html.escape(marka)} {html.escape(model)} bakım fiyatları</h1>"
                f"<p class='ozet'>Aşağıdaki fiyatlar <strong>{html.escape(marka)}</strong>"
                f" tarafından yayımlanan resmî periyodik bakım tablosundan alınmıştır."
                f" KDV dâhildir.</p>"
                + "".join(bolumler)
                + '<div class="reklam-alani"></div>'
                + f"<p class='kaynak'>Kaynak: <a href='{kaynak['kaynak_url']}' rel='nofollow'>"
                f"{html.escape(marka)} resmî bakım fiyat tablosu</a> · "
                f"{tarih_yaz(kaynak['kaynak_tarih'])}<br>Fiyatlar markanın yayımladığı tavsiye "
                f"niteliğindeki tavan fiyatlardır, teklif değildir. Kesin fiyat için "
                f"yetkili servise başvurun.</p>",
                2,
            )

        # Marka sayfasi
        liste = "".join(
            f"<li><a href='{slug(m)}/'>{html.escape(m)}</a></li>"
            for m in sorted(modeller)
        )
        sayfa_yaz(
            f"{ms}/index.html",
            f"{marka} Bakım Fiyatları — Tüm Modeller",
            f"{marka} periyodik bakım fiyatları, model model, markanın resmi tablosundan.",
            f"<h1>{html.escape(marka)} bakım fiyatları</h1>"
            f"<p class='ozet'>{len(modeller)} model. Fiyatlar {marka}'nin yayımladığı "
            f"resmî tablodan.</p><ul class='liste'>{liste}</ul>",
            1,
        )
        yollar.append(f"{ms}/index.html")

    # Ana sayfa
    kartlar = "".join(
        f"<li><a href='{slug(m)}/'><strong>{html.escape(m)}</strong>"
        f"<span>{len(md)} model</span></a></li>"
        for m, md in sorted(agac.items())
    )
    sayfa_yaz(
        "index.html",
        "Bakım Fiyat Rehberi — Markaların Resmî Periyodik Bakım Fiyatları",
        "Periyodik bakım fiyatları, tahmin değil markanın kendi yayımladığı resmî "
        "tablodan. Model model, kaynağıyla birlikte.",
        "<h1>Bakım fiyat rehberi</h1>"
        "<p class='ozet'>Periyodik bakım fiyatları <strong>tahmin değil</strong> — "
        "her fiyat markanın kendi yayımladığı resmî tablodan alınır ve kaynağı "
        "sayfada gösterilir.</p>"
        f"<ul class='markalar'>{kartlar}</ul>"
        "<p class='kaynak'>Kapsam yalnızca resmî fiyat tablosu yayımlayan markalarla "
        "sınırlıdır. Fiyat yayımlamayan markalar için sayfa açılmaz.</p>",
        0,
    )
    yollar.append("index.html")

    (CIKTI / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(
            f"<url><loc>{SITE_ADRES}{y.removesuffix('index.html')}</loc></url>"
            for y in yollar
        )
        + "</urlset>",
        encoding="utf-8",
    )
    print(f"{len(yollar)} sayfa uretildi -> {CIKTI}")


if __name__ == "__main__":
    main()
