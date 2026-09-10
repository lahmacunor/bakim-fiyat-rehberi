"""Hyundai parse kontrolu.  Calistir:  python test_parse.py

Buradaki fiyatlar Mayis 2026 PDF'inden GOZLE okunup yazildi. Parse mantigi
bozulursa (sutun kaymasi, satir birlestirme hatasi) bu testler kirilir.
Fiyat verisi yanlissa sitenin tek degeri gider -- bu test o yuzden var.
"""
import json
import sys
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
print(f"OK — {len(kayitlar)} fiyat, {len(modeller)} model-motor, tum kontroller gecti")
