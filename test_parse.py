"""Hyundai parse kontrolu.  Calistir:  python test_parse.py

Buradaki fiyatlar Mayis 2026 PDF'inden GOZLE okunup yazildi. Parse mantigi
bozulursa (sutun kaymasi, satir birlestirme hatasi) bu testler kirilir.
Fiyat verisi yanlissa sitenin tek degeri gider -- bu test o yuzden var.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

VERI = Path(__file__).parent / "veri" / "hyundai" / "2026-05.json"
kayitlar = json.loads(VERI.read_text(encoding="utf-8"))


def fiyat(model, motor, km):
    bulunan = [
        k for k in kayitlar
        if k["model"] == model and k["motor"] == motor and k["bakim_km"] == km
    ]
    assert len(bulunan) == 1, f"{model} / {motor} / {km}km -> {len(bulunan)} kayit bulundu"
    return bulunan[0]["fiyat_tl"]


# --- PDF'ten gozle dogrulanmis fiyatlar ---
assert fiyat("IONIQ5 NE PE", "125KW+160KW (63 KWH+84 KWH)", 15000) == 5642
assert fiyat("IONIQ5 NE PE", "125KW+160KW (63 KWH+84 KWH)", 30000) == 14081
assert fiyat("İ20 (BC3) FL", "1.0 T-GDI KAPPA", 15000) == 10472
assert fiyat("İ20 (BC3) FL", "1.0 T-GDI KAPPA", 30000) == 11888
assert fiyat("ELANTRA (CN7)", "1.6 SMARTSTREAM GAMMA II", 15000) == 15126
assert fiyat("ACCENT ERA (MCT)", "1.4&1.6", 15000) == 9072
assert fiyat("TUCSON (NX4E)", "1.6 T-GDI SMARTSTREAM GAMMA II", 15000) == 17697

# i20 N farkli sutun duzeninde (12 aralik, 10.000'lik adimlar)
assert fiyat("i20 N", "1.6 T-GDI 6MT", 10000) == 13016
assert fiyat("i20 N", "1.6 T-GDI 6MT", 70000) == 25570

# Satir sonunda tire ile bolunmus motor adi birlesmis olmali
assert any(
    k["motor"] == "1.6 T-GDI SMARTSTREAM GAMMA II" for k in kayitlar
), "tire ile bolunmus motor adi birlestirilememis"

# --- Sagilik kontrolleri ---
assert len(kayitlar) > 1000, f"cok az kayit: {len(kayitlar)}"
assert all(1_000 < k["fiyat_tl"] < 500_000 for k in kayitlar), "mantiksiz fiyat var"
assert all(k["bakim_km"] % 5000 == 0 for k in kayitlar), "bozuk km degeri"
assert all(k["model"] and k["motor"] and k["model_yili"] for k in kayitlar), "bos alan"
assert all(k["kaynak_url"].startswith("https://") for k in kayitlar), "kaynaksiz satir"

modeller = {(k["model"], k["motor"]) for k in kayitlar}
print(f"Hyundai OK — {len(kayitlar)} fiyat, {len(modeller)} model-motor")


# --- Ford: resmi hesaplayicidan gozle dogrulanmis fiyatlar ---
ford = json.loads(
    (Path(__file__).parent / "veri" / "ford" / "2026-09.json").read_text(encoding="utf-8")
)


def ford_fiyat(model, motor, km, sanziman=None):
    b = [
        k for k in ford
        if k["model"] == model and k["motor"] == motor and k["bakim_km"] == km
        and (sanziman is None or k["sanziman"] == sanziman)
    ]
    assert b, f"{model} / {motor} / {km}km bulunamadi"
    return b[0]["fiyat_tl"]


assert ford_fiyat("BRONCO SPORT (2024- )", "1.5 ECOBOOST", 15000) == 19533
# Ayni motor, farkli sanziman, farkli fiyat -- sutun ayrimi bunun icin var
assert ford_fiyat("FOCUS (2015-2018)", "1.5 TDCI 120PS", 45000, "MANUAL B6") == 14741
assert ford_fiyat("FOCUS (2015-2018)", "1.5 TDCI 120PS", 45000, "POWERSHIFT MPS6") == 32537

assert len(ford) > 1400, f"cok az Ford kaydi: {len(ford)}"
assert all(1_000 < k["fiyat_tl"] < 500_000 for k in ford), "mantiksiz Ford fiyati"
assert all(k["bakim_km"] % 5000 == 0 for k in ford), "bozuk Ford km degeri"
assert all(k["kaynak_url"].startswith("https://") for k in ford), "kaynaksiz Ford satiri"
print(f"Ford OK — {len(ford)} fiyat, {len({k['model'] for k in ford})} model")


# --- Uretim: tabloya girmeyen fiyat kalmamali ---
# Sutunlar motora gore acilip sanziman yok sayilirsa Ford'un 509 satiri sessizce
# dusuyordu. Bu kontrol o hatanin geri gelmesini yakalar.
import uret

hepsi = ford + kayitlar
for k in hepsi:
    k["model"] = uret.model_adi(k["model"])
gruplar = defaultdict(list)
for k in hepsi:
    gruplar[(k["marka"], k["model"], k["model_yili"], k["yakit"])].append(k)

for grup, gk in gruplar.items():
    kmler = sorted({x["bakim_km"] for x in gk})
    gosterilen = {
        (baslik.split(" · ")[0], km, f[km])
        for baslik, f in uret.sutunlastir(gk, kmler)
        for km in f
    }
    for k in gk:
        anahtar = (k["motor"], k["bakim_km"], k["fiyat_tl"])
        assert anahtar in gosterilen, f"{grup} icin tabloya girmeyen fiyat: {anahtar}"

print(f"Uretim OK — {len(hepsi)} fiyatin hepsi bir tablo hucresinde")


# --- Kumulatif maliyet: karsilastirmalarin dayandigi hesap ---
# Bu sayilar yanlissa karsilastirma sayfalari "su arac daha ucuz" diye
# yanlis hukum verir; testin asil isi o.
tucson = [k for k in kayitlar
          if k["model"] == "TUCSON (NX4E)" and k["yakit"] == "benzin"]
toplam = uret.kumulatif(tucson, 100_000)
assert toplam, "TUCSON (NX4E) benzin 100.000 km'ye ulasmali"
elle = sum(k["fiyat_tl"] for k in tucson if k["bakim_km"] <= 100_000)
assert sum(toplam.values()) == elle, f"{sum(toplam.values())} != {elle}"

# Verisi hedefe ulasmayan modelden "daha ucuz" sonucu cikmamali
kisa = [k for k in tucson if k["bakim_km"] <= 45_000]
assert uret.kumulatif(kisa, 100_000) is None, "eksik veri None donmeli"

# Elle yazilan rakip esleri gercekten var mi (model adi degisirse kirilsin)
mevcut = {(k["marka"], k["model"]) for k in hepsi}
for hyu, ford in uret.RAKIPLER:
    assert ("Hyundai", hyu) in mevcut, f"RAKIPLER'de olmayan model: {hyu}"
    assert ("Ford", ford) in mevcut, f"RAKIPLER'de olmayan model: {ford}"

print(f"Karsilastirma OK — {len(uret.RAKIPLER)} rakip esi, kumulatif hesap dogru")
