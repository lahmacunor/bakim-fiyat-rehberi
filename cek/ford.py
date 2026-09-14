"""Ford Turkiye periyodik bakim tavan fiyatlarini resmi hesaplayicidan ceker.

Kaynak: https://www.ford.com.tr/bakim-fiyati-hesapla
Fiyatlar KDV dahil ve **tavan fiyat** -- Hyundai'nin tavsiye fiyatiyla ayni sey
degil, sitede boyle etiketlenmeli.

Yontem: sayfanin kendi JSON ucları (/FWebApi/MaintenanceMenu/*) dogrudan
cagriliyor. Her istek `secret` alaninda taze bir reCAPTCHA v3 token'i istiyor,
o yuzden gercek tarayici sart -- ama form surulmuyor, token sayfa icinde
grecaptcha.execute ile uretilip fetch atiliyor. Ayrinti: cek/ford-api-notlari.md

Kullanim:
    python cek/ford.py                      # binek + ticari, hepsi
    python cek/ford.py --model CF7 --limit 2   # deneme
"""
import argparse
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

KAYNAK_URL = "https://www.ford.com.tr/bakim-fiyati-hesapla"
KAYNAK_TARIH = date.today().strftime("%Y-%m")
RECAPTCHA_KEY = "6Ld8cpIUAAAAAPHA_uBQTpDBsdd306tN-Eqf-gzQ"

KOK = Path(__file__).resolve().parent.parent
HEDEF = KOK / "veri" / "ford"

# "PUMA (2019- )" / "FOCUS (2015-2018)" -> "2019~" / "2015~2018"
MODEL_YILI = re.compile(r"\((\d{4})\s*-\s*(\d{4})?\s*\)")

TOKEN_JS = (
    "async key => await new Promise((res, rej) => grecaptcha.ready(() =>"
    " grecaptcha.execute(key, {action: 'submit'}).then(res, rej)))"
)

CAGIR_JS = """
async ([uc, govde, tok]) => {
  const r = await fetch('/FWebApi/MaintenanceMenu/' + uc, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(Object.assign({}, govde, {secret: tok}))});
  if (!r.ok) return {hata: 'HTTP ' + r.status};
  return await r.json();
}
"""

# Ford token'i geçersiz kılmıyor, ayni token defalarca kullanilabiliyor.
# Bu kritik: her istekte yeni token istenirse grecaptcha kendini kisiyor ve
# cagri basina ~30 sn'ye cikiyor (tam cekim 20 saat). Tekrar kullanimla ~0,6 sn.
TOKEN_OMRU = 90  # saniye


# Turkce noktali I tuzagi: "TDCİ".upper() yine "TDCİ"dir, "TDCI" ile eslesmez.
# Ayni sey TİVCT / BENZİN / DİZEL icin de gecerli -- once harfleri duzlestir.
_DUZLES = str.maketrans("İıĞğÜüŞşÖöÇç", "IiGgUuSsOoCc")

# Ford motoru yakit tipini adinda soylemiyor, motor *ailesi* adiyla soyluyor:
# PANTHER/LION/PUMA dizel aileler, FOX/DRAGON benzinli.
DIZEL = ("DIESEL", "DIZEL", "TDCI", "ECOBLUE", "PANTHER", "LION", "PUMA", "DSL", "HDT")
BENZIN = ("ECOBOOST", "GTDI", "TIVCT", "TI-VCT", "BENZIN", "FOX", "DRAGON", "SIGMA")


def yakit_bul(motor):
    m = motor.translate(_DUZLES).upper()
    if "BEV" in m or "ELEKTRIK" in m:
        return "elektrik"
    if "PHEV" in m:
        return "benzin-plug-in-hibrit"
    if "MHEV" in m or "HYBRID" in m:
        return "benzin-hibrit"
    if any(a in m for a in DIZEL):
        return "dizel"
    if any(a in m for a in BENZIN):
        return "benzin"
    # "1.6I" = enjeksiyonlu benzinli; "1.5L 75PS" gibi cikplak hacimler
    # tahmin edilmiyor -- yanlis yakit yazmaktansa bilinmiyor kalsin.
    if re.search(r"\d\.\dI\b", m):
        return "benzin"
    return "bilinmiyor"


def model_yili_ayikla(etiket):
    m = MODEL_YILI.search(etiket)
    return f"{m.group(1)}~{m.group(2) or ''}" if m else ""


def km_ayikla(bakim_adi):
    """'2.yıl/30.000 km' -> 30000 ; '1.yıl/Sınırsız Km' -> 0"""
    kuyruk = bakim_adi.split("/")[-1]
    rakam = re.sub(r"\D", "", kuyruk)
    return int(rakam) if rakam else 0


_token = {"deger": None, "zaman": 0.0}


def token_al(sayfa, zorla=False):
    if zorla or not _token["deger"] or time.time() - _token["zaman"] > TOKEN_OMRU:
        _token["deger"] = sayfa.evaluate(TOKEN_JS, RECAPTCHA_KEY)
        _token["zaman"] = time.time()
    return _token["deger"]


def cagir(sayfa, uc, istek):
    """Bir /FWebApi/MaintenanceMenu/<uc> cagrisi; ham yanit doner.

    Iki basarisizligi ayirir:
    - token/HTTP sorunu  -> taze token ile bir kez daha dene
    - "uygun kayit bulamadik" -> Ford o kombinasyona fiyat yayimlamiyor
      (or. Explorer PHEV). Tekrar denemek bosuna, ustelik her denemede token
      yenileyip cekimi yavaslatiyor.
    """
    for zorla in (False, True):
        yanit = sayfa.evaluate(CAGIR_JS, [uc, {"Request": istek}, token_al(sayfa, zorla)])
        if not yanit.get("hata") and yanit.get("isSuccess"):
            return yanit
        if yanit.get("errorMessage"):  # is kurali reddi, kimlik sorunu degil
            return None
    return None


def liste(sayfa, uc, istek):
    y = cagir(sayfa, uc, istek)
    return (y or {}).get("resultData") or []


def sayfa_ac(p, goster):
    tarayici = p.chromium.launch(headless=not goster)
    sayfa = tarayici.new_page(viewport={"width": 1920, "height": 1080})
    # Ford yavas (TTFB ~10 sn) ve ara sira hic commit etmiyor.
    for deneme in range(3):
        try:
            sayfa.goto(KAYNAK_URL, wait_until="commit", timeout=120000)
            sayfa.wait_for_selector("#CarType", timeout=60000, state="attached")
            break
        except Exception as e:
            print(f"acilis denemesi {deneme + 1} basarisiz: {e}")
            if deneme == 2:
                raise
    sayfa.wait_for_timeout(4000)  # grecaptcha yuklensin
    return tarayici, sayfa


def gez(sayfa, tip, sadece_model=None, limit=None, kaydet=None):
    kayitlar, icerik_onbellek = [], {}
    modeller = liste(sayfa, "GetPtvlListByPtvlType", {"ptvlType": tip})
    print(f"[{tip}] {len(modeller)} model")

    for m in modeller:
        ptvl, model_ad = m["ptvl"], m["ptvlDesc"].strip()
        if sadece_model and ptvl != sadece_model:
            continue
        for e in liste(sayfa, "GetEngineCode", {"ptvl": ptvl}):
            motor_kod, motor_ad = e["engineCode"], e["engineDescription"].strip()
            for t in liste(sayfa, "GetTransmissionCodes",
                           {"ptvl": ptvl, "engineCode": motor_kod}):
                sanz_kod = t["transmissionCode"]
                sanz_ad = t["transmissionDescription"].strip()
                bakimlar = liste(sayfa, "GetSortOfPeriod", {
                    "ptvl": ptvl, "engineCode": motor_kod,
                    "transmissionCode": sanz_kod})
                if limit:
                    bakimlar = bakimlar[:limit]
                for bak in bakimlar:
                    y = cagir(sayfa, "ListAvailableMtncMenu", {
                        "periodId": bak["value"], "ptvl": ptvl,
                        "engineCode": motor_kod, "engineCodeDesc": motor_ad,
                        "transmissionDesc": sanz_ad, "transmissionCode": sanz_kod})
                    sonuc = (y or {}).get("resultData") or {}
                    if not sonuc.get("maxPrice"):
                        print(f"  ATLANDI {model_ad} | {motor_ad} | {bak['name']}")
                        continue

                    menu_id = str(sonuc.get("menuId") or "")
                    if menu_id and menu_id not in icerik_onbellek:
                        icerik_onbellek[menu_id] = [
                            s["lineDescription"].strip()
                            for s in liste(sayfa, "ListMtncMenuLine", {"menuId": menu_id})
                        ]

                    kayitlar.append({
                        "marka": "Ford",
                        "model": model_ad,
                        "model_yili": model_yili_ayikla(model_ad),
                        "motor": motor_ad,
                        "sanziman": sanz_ad,
                        "yakit": yakit_bul(motor_ad),
                        "bakim_km": km_ayikla(bak["name"]),
                        "bakim_adi": bak["name"],
                        "fiyat_tl": int(sonuc["maxPrice"]),
                        "kdv_dahil": True,
                        "tavan_fiyat": True,
                        "icerik": icerik_onbellek.get(menu_id, []),
                        "aciklama": (sonuc.get("menuName") or "").strip(),
                        "arac_tipi": "binek" if tip == "B" else "ticari",
                        "kaynak_url": KAYNAK_URL,
                        "kaynak_tarih": KAYNAK_TARIH,
                    })
                    print(f"  {model_ad} | {motor_ad} | {sanz_ad} | "
                          f"{bak['name']} -> {int(sonuc['maxPrice'])} TL")
                    if kaydet and len(kayitlar) % 25 == 0:
                        kaydet(kayitlar)
    return kayitlar


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="tek model kodu ile dene (or. CF7)")
    ap.add_argument("--limit", type=int, help="varyant basina kac bakim araligi")
    ap.add_argument("--tip", default="BT", help="B=binek T=ticari, ikisi: BT")
    ap.add_argument("--goster", action="store_true", help="tarayiciyi gorunur ac")
    a = ap.parse_args()

    HEDEF.mkdir(parents=True, exist_ok=True)
    yol = HEDEF / f"{KAYNAK_TARIH}.json"

    def tekille(kayitlar):
        """Ford ayni sanzimani birden fazla kodla donebiliyor ('6 ILERI MANUEL'
        iki kez); ayni varyant+bakim icin tek satir birakilir."""
        gorulen, cikti = set(), []
        for k in kayitlar:
            anahtar = (k["model"], k["motor"], k["sanziman"], k["bakim_km"])
            if anahtar in gorulen:
                continue
            gorulen.add(anahtar)
            cikti.append(k)
        return cikti

    def yaz(kayitlar):
        yol.write_text(json.dumps(tekille(kayitlar), ensure_ascii=False, indent=1),
                       encoding="utf-8")

    hepsi = []
    with sync_playwright() as p:
        tarayici, sayfa = sayfa_ac(p, a.goster)
        try:
            for tip in a.tip:
                # ara kayit: onceki tiplerin kayitlari + su anki tipin birikeni
                hepsi += gez(sayfa, tip, a.model, a.limit,
                             kaydet=lambda k: yaz(hepsi + k))
        finally:
            tarayici.close()

    yaz(hepsi)
    son = tekille(hepsi)
    varyant = {(k["model"], k["motor"], k["sanziman"]) for k in son}
    print(f"\n{len(son)} fiyat satiri, {len(varyant)} varyant -> {yol}")


if __name__ == "__main__":
    main()
