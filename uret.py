"""veri/ altindaki JSON'lardan statik site uretir.  Calistir:  python uret.py

Cikti site/ altina yazilir, GitHub Pages oradan yayinlar.
Framework yok, build step yok -- sablon doldurup dosya yaziyoruz.
"""
import html
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
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


def sanziman_kod(ham):
    """Ford ayni sanzimani birden cok yazimla donuyor ("8 ILERI OTOMATIK" /
    "8 İLERİ OTOMATİK ŞANZIMAN"). Karsilastirma icin tek bicime indiriyoruz."""
    s = re.sub(r"\b(SANZIMAN|TRANS|TRANSMISSION)\b", "", ham.translate(TR_ASCII).upper())
    return re.sub(r"\s+", " ", s).strip()


def sanziman_adi(kod):
    """Sutun basligi icin kisa ad. Ford'un ic kodlari (MT82, VMT6, 6R80)
    okuyucuya bir sey anlatmiyor; tur yeter."""
    if "POWERSHIFT" in kod or "DCT" in kod:
        return "PowerShift"
    if "MANUEL" in kod or "MANUAL" in kod or re.search(r"\bMAN\b", kod) or "VMT6" in kod:
        return "Manuel"
    if "OTOMATIK" in kod or "AUTO" in kod or "CVT" in kod:
        return "Otomatik"
    return kod.title()


def sutunlastir(kayitlar, kmler):
    """[(baslik, {km: fiyat})] uretir.

    Sutun yalnizca motora gore acilamaz: Ford'da ayni motorun manuel ve
    PowerShift'i farkli fiyatlanir (FOCUS 1.5 TDCI 45.000 km -> 14.741 / 32.537).
    Ama hesaplayici cogu zaman ayni fiyati birden cok sanziman secenegiyle
    donuyor; ayni fiyat dizisini veren secenekleri tek sutunda birlestiriyoruz.
    """
    hucre = defaultdict(dict)
    for k in kayitlar:
        hucre[(k["motor"], sanziman_kod(k.get("sanziman", "")))][k["bakim_km"]] = k["fiyat_tl"]

    sutunlar = []
    for motor in sorted({m for m, _ in hucre}):
        dizi = defaultdict(list)
        for m, kod in sorted(hucre):
            if m == motor:
                dizi[tuple(hucre[(m, kod)].get(km) for km in kmler)].append(kod)

        if len(dizi) == 1:
            sutunlar.append((motor, hucre[(motor, next(iter(dizi.values()))[0])]))
            continue

        adlar = [sanziman_adi(kodlar[0]) for kodlar in dizi.values()]
        if len(set(adlar)) < len(adlar):  # kisa ad ayirmiyorsa Ford'un yazimi
            adlar = [kodlar[0].title() for kodlar in dizi.values()]
        for ad, kodlar in zip(adlar, dizi.values()):
            sutunlar.append((f"{motor} · {ad}", hucre[(motor, kodlar[0])]))
    return sutunlar


def tablo(kayitlar):
    """Satirlar = bakim araligi, sutunlar = motor (gerekirse + sanziman)."""
    kmler = sorted({k["bakim_km"] for k in kayitlar})
    sutunlar = sutunlastir(kayitlar, kmler)

    bas = "".join(f"<th>{html.escape(b)}</th>" for b, _ in sutunlar)
    satirlar = []
    for km in kmler:
        hucre = "".join(
            f"<td>{tl(f[km]) if km in f else '—'}</td>" for _, f in sutunlar
        )
        km_yazi = f"{km:,}".replace(",", ".")
        satirlar.append(f"<tr><th>{km_yazi} km</th>{hucre}</tr>")

    toplam = "".join(f"<td>{tl(sum(f.values()))}</td>" for _, f in sutunlar)
    son_km = f"{max(kmler):,}".replace(",", ".")
    return (
        f'<div class="kaydir"><table><thead><tr><th>Bakım aralığı</th>{bas}</tr></thead>'
        f'<tbody>{"".join(satirlar)}</tbody>'
        f'<tfoot><tr><th>{son_km} km\'ye kadar toplam</th>{toplam}</tr></tfoot>'
        "</table></div>"
    )


KILOMETRE = 100_000       # Karsilastirmalarin ortak olcusu


def kumulatif(kayitlar, hedef_km=KILOMETRE):
    """Sutun -> hedef km'ye kadar odenecek toplam bakim bedeli.

    Modelin fiyat tablosu hedefe ulasmiyorsa None doner -- eksik veriden
    "daha ucuz" sonucu cikarmak en tehlikeli hata olurdu.
    """
    kmler = sorted({k["bakim_km"] for k in kayitlar})
    if not kmler or max(kmler) < hedef_km:
        return None
    return {
        baslik: sum(v for km, v in f.items() if km <= hedef_km)
        for baslik, f in sutunlastir(kayitlar, kmler)
    }


def km_basina(toplam):
    """Turkce ondalik ayraci virgul -- "1.38 TL" yanlis, "1,38 TL" dogru."""
    return f"{toplam / KILOMETRE:.2f}".replace(".", ",") + " TL"


def orta(sayilar):
    s = sorted(sayilar)
    return s[len(s) // 2] if s else 0


def maliyet_ozeti(mk):
    """Model sayfasindaki '100.000 km'ye kadar ne oder' bolumu.

    Ayri bir sayfa degil bolum: ayni model icin ikinci bir sayfa acmak
    kendi sayfanla ayni sorguda yarismak demek.
    """
    satirlar = []
    for yakit in sorted({k["yakit"] for k in mk}):
        yk = [k for k in mk if k["yakit"] == yakit]
        toplam = kumulatif(yk)
        if not toplam:
            continue
        for motor, tl_toplam in sorted(toplam.items(), key=lambda i: i[1]):
            satirlar.append(
                f"<tr><th>{html.escape(motor)}</th>"
                f"<td>{yakit}</td><td>{tl(tl_toplam)}</td>"
                f"<td>{km_basina(tl_toplam)}</td></tr>"
            )
    if not satirlar:
        return ""

    km_yazi = f"{KILOMETRE:,}".replace(",", ".")
    return (
        f"<h2>{km_yazi} km'ye kadar toplam bakım maliyeti</h2>"
        f"<p class='ozet'>Aşağıdaki tutar, aracın {km_yazi} km'ye ulaşana dek "
        f"yetkili serviste ödeyeceği <strong>tüm periyodik bakımların "
        f"toplamıdır</strong>. Kilometre başına maliyet, farklı motorları "
        f"karşılaştırmayı kolaylaştırır.</p>"
        f'<div class="kaydir"><table><thead><tr><th>Motor</th><th>Yakıt</th>'
        f"<th>{km_yazi} km toplam</th><th>km başına</th></tr></thead>"
        f"<tbody>{''.join(satirlar)}</tbody></table></div>"
    )


def kar_baglantilari(liste):
    if not liste:
        return ""
    ogeler = "".join(
        f"<li><a href='../../karsilastirma/{ad}/'>{html.escape(rakip)} ile "
        "karşılaştır</a></li>"
        for ad, rakip in sorted(liste, key=lambda x: x[1])
    )
    return f"<h2>Rakipleriyle bakım maliyeti</h2><ul class='liste'>{ogeler}</ul>"


def ozet_tablosu(o):
    satirlar = "".join(
        f"<tr><th>{html.escape(m)}</th><td>{tl(v)}</td></tr>"
        for m, v in sorted(o["toplam"].items(), key=lambda i: i[1])
    )
    km_yazi = f"{KILOMETRE:,}".replace(",", ".")
    return (
        f"<h3>{html.escape(o['marka'])} {html.escape(o['model'])}</h3>"
        f'<div class="kaydir"><table><thead><tr><th>Motor</th>'
        f"<th>{km_yazi} km toplam</th></tr></thead><tbody>{satirlar}</tbody>"
        f"<tfoot><tr><th>Ortanca</th><td>{tl(o['orta'])}</td></tr></tfoot>"
        "</table></div>"
    )


# Rakip esleri ELLE yazildi. Denendi ve birakildi: modelleri maliyete gore
# birbirine eslestirmek. Veride segment alani yok, maliyet de segmenti
# gostermiyor -- 1.5 motor hem Fiesta'da hem Bronco Sport'ta var. Otomatik
# esleme "Bronco Sport vs Atos" gibi kimsenin aramadigi 188 sayfa uretti.
# Az ve dogru cift, cok ve rastgele sayfadan iyidir.
RAKIPLER = [
    ("i20 / BAYON (BC3)", "FIESTA (2017- )"),
    ("i20 / BAYON (BC3)", "PUMA (2019- )"),
    ("i20 (BC3) FL", "FIESTA (2017- )"),
    ("i20 TROY (PBT)", "FIESTA (2017- )"),
    ("i30 (PDE)", "FOCUS (2018- )"),
    ("i30 (GDE)", "FOCUS (2015-2018)"),
    ("ELANTRA (CN7)", "FOCUS (2018- )"),
    ("ELANTRA (AD)", "FOCUS (2015-2018)"),
    ("TUCSON (NX4E)", "KUGA (2020- )"),
    ("TUCSON (TLE)", "KUGA (2013-2020)"),
    ("iX35 (EL)", "KUGA (2013-2020)"),
    ("KONA (SX2)", "PUMA (2019- )"),
    ("KONA (OS)", "ECOSPORT (2017- )"),
    ("i40 (VF)", "MONDEO (2014- )"),
    ("SONATA (NF)", "MONDEO (2014- )"),
    ("GRANDEUR (TG)", "MONDEO (2014- )"),
    ("SANTAFE (DM)", "EDGE (2015- )"),
    ("STARIA (US4)", "TRANSIT/TOURNEO CUSTOM (2023-)"),
    ("H1 VAN &KAMYONET (TQ)", "TRANSIT/TOURNEO CUSTOM (2012-2023)"),
    ("H100 KAMYONET EURO6", "TRANSIT (2014-2019)"),
]


def model_ozeti(kayitlar, marka, model, yakit):
    toplam = kumulatif([k for k in kayitlar if k["yakit"] == yakit])
    if not toplam:
        return None
    return {"marka": marka, "model": model, "yakit": yakit, "toplam": toplam,
            "orta": orta(list(toplam.values())),
            "yol": f"{slug(marka)}/{slug(model)}/"}


def rakip_ozeti(agac, hyu, ford):
    """Iki modeli ORTAK yakitta karsilastirir.

    Ortak yakit sarti onemli: benzinli bir modeli dizel bir modelle
    karsilastirmak fiyat farkini motor turune borclu kilar, modele degil.
    """
    a_kayit = agac.get("Hyundai", {}).get(hyu)
    b_kayit = agac.get("Ford", {}).get(ford)
    if not a_kayit or not b_kayit:
        print(f"  ! rakip eşi bulunamadı: {hyu} / {ford}", file=sys.stderr)
        return None

    ortak = ({k["yakit"] for k in a_kayit} & {k["yakit"] for k in b_kayit}) - {"bilinmiyor"}
    for yakit in sorted(ortak, key=lambda y: -sum(1 for k in a_kayit if k["yakit"] == y)):
        a = model_ozeti(a_kayit, "Hyundai", hyu, yakit)
        b = model_ozeti(b_kayit, "Ford", ford, yakit)
        if a and b:
            return tuple(sorted([a, b], key=lambda o: (o["marka"], o["model"])))
    return None


def karsilastirma(a, b):
    """Iki modelin ayni kilometreye kadar toplam bakim bedeli."""
    ucuz, pahali = (a, b) if a["orta"] <= b["orta"] else (b, a)
    fark = pahali["orta"] - ucuz["orta"]
    km_yazi = f"{KILOMETRE:,}".replace(",", ".")

    yuzde = fark / pahali["orta"] * 100 if pahali["orta"] else 0
    # %1'in altindaki fark, tavan fiyat listelerinde gurultu sayilir --
    # "%0 fark var" yazmak yerine esit oldugunu soylemek dogru olan.
    if yuzde < 1:
        hukum = (f"İki aracın {km_yazi} km'ye kadarki toplam bakım maliyeti "
                 f"<strong>neredeyse aynı</strong>: {tl(ucuz['orta'])} ve "
                 f"{tl(pahali['orta'])}. Aradaki {tl(fark)}'lik fark, bu "
                 f"büyüklükteki bir toplamda belirleyici değil.")
    else:
        hukum = (
            f"<strong>{html.escape(ucuz['marka'])} {html.escape(ucuz['model'])}</strong>, "
            f"{km_yazi} km'ye kadar <strong>{tl(fark)}</strong> daha ucuza bakım "
            f"yaptırıyor — {html.escape(pahali['marka'])} {html.escape(pahali['model'])} "
            f"ile arada %{yuzde:.0f} fark var."
        )

    return (
        f"<h1>{html.escape(a['marka'])} {html.escape(a['model'])} ile "
        f"{html.escape(b['marka'])} {html.escape(b['model'])} bakım maliyeti "
        f"karşılaştırması</h1>"
        f"<p class='ozet'>{hukum} Karşılaştırma, her iki markanın kendi yayımladığı "
        f"resmî periyodik bakım tablosundaki tutarların {km_yazi} km'ye kadar "
        f"toplanmasıyla yapıldı; ortanca, modelin motor seçenekleri arasındaki "
        f"orta değerdir. Her iki araç da <strong>{a['yakit']}</strong>.</p>"
        + ozet_tablosu(a) + ozet_tablosu(b)
        + '<div class="reklam-alani"></div>'
        + f"<p class='kaynak'>Ayrıntılı bakım aralığı tabloları: "
        f"<a href='../../{a['yol']}'>{html.escape(a['marka'])} "
        f"{html.escape(a['model'])}</a> · "
        f"<a href='../../{b['yol']}'>{html.escape(b['marka'])} "
        f"{html.escape(b['model'])}</a><br>Fiyatlar markaların yayımladığı tavsiye "
        f"niteliğindeki tavan fiyatlardır, teklif değildir.</p>"
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

    # Ciftler once hesaplaniyor: model sayfalari kendi karsilastirmalarina
    # link verecek, yoksa karsilastirma sayfalari siteden erisilemez kalir.
    ciftler = {}
    for hyu, ford in RAKIPLER:
        cift = rakip_ozeti(agac, hyu, ford)
        if cift:
            x, y = cift
            ciftler[(x["marka"], x["model"], y["marka"], y["model"])] = cift

    kar_yolu = defaultdict(list)
    for (m1, md1, m2, md2) in ciftler:
        ad = f"{slug(m1)}-{slug(md1)}-vs-{slug(m2)}-{slug(md2)}"
        kar_yolu[(m1, md1)].append((ad, f"{m2} {md2}"))
        kar_yolu[(m2, md2)].append((ad, f"{m1} {md1}"))

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
                    # Ford'da model adi zaten yil araligini tasiyor
                    # ("CONNECT (2022-)"); tek yil varsa basliga tekrar yazmiyoruz.
                    yil_yazi = f" {html.escape(yil)}" if len(yillar) > 1 else ""
                    bolumler.append(
                        f"<h2>{html.escape(model)}{yil_yazi}"
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
                + maliyet_ozeti(mk)
                + kar_baglantilari(kar_yolu.get((marka, model), []))
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

    # --- Karsilastirma sayfalari ---------------------------------------
    for (m1, md1, m2, md2), (x, y) in sorted(ciftler.items()):
        ad = f"{slug(m1)}-{slug(md1)}-vs-{slug(m2)}-{slug(md2)}"
        yol = f"karsilastirma/{ad}/index.html"
        yollar.append(yol)
        sayfa_yaz(
            yol,
            f"{m1} {md1} mi {m2} {md2} mi? Bakım Maliyeti Karşılaştırması",
            f"{m1} {md1} ve {m2} {md2} periyodik bakım maliyeti karşılaştırması — "
            f"100.000 km'ye kadar toplam tutar, markaların resmî tablolarından.",
            karsilastirma(x, y),
            2,
        )

    kar_liste = "".join(
        f"<li><a href='{slug(m1)}-{slug(md1)}-vs-{slug(m2)}-{slug(md2)}/'>"
        f"{html.escape(m1)} {html.escape(md1)} <span>vs</span> "
        f"{html.escape(m2)} {html.escape(md2)}</a></li>"
        for (m1, md1, m2, md2) in sorted(ciftler)
    )
    sayfa_yaz(
        "karsilastirma/index.html",
        "Bakım Maliyeti Karşılaştırmaları — Hangi Araç Daha Ucuza Bakılır",
        "İki aracın 100.000 km'ye kadarki toplam periyodik bakım maliyetini "
        "yan yana koyan karşılaştırmalar, markaların resmî fiyat tablolarından.",
        "<h1>Bakım maliyeti karşılaştırmaları</h1>"
        f"<p class='ozet'>{len(ciftler)} karşılaştırma. Her araç, diğer markanın "
        "aynı yakıtlı modelleri arasından maliyetçe kendisine en yakın olanlarla "
        "eşleştirildi. Ölçü her yerde aynı: <strong>100.000 km'ye kadar ödenen "
        "toplam periyodik bakım bedeli</strong>.</p>"
        f"<ul class='liste'>{kar_liste}</ul>",
        1,
    )
    yollar.append("karsilastirma/index.html")

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
        "<h2>Bakım maliyeti karşılaştırmaları</h2>"
        "<p class='ozet'>Aynı segmentteki iki aracın 100.000 km'ye kadar "
        "ödeyeceği toplam bakım bedeli yan yana.</p>"
        f"<ul class='liste'><li><a href='karsilastirma/'>"
        f"{len(ciftler)} karşılaştırmanın tamamı</a></li></ul>"
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
