# Ford Türkiye — resmî bakım fiyatı çekim notları

Kaynak sayfa: https://www.ford.com.tr/bakim-fiyati-hesapla
Keşif tarihi: 2026-09-14

## Akış

Sayfada "Aracınızın şasi ya da plaka numarasını biliyor musunuz?" sorusu var.
**Hayır** seçilince VIN gerekmeden model ağacı açılıyor. (Radyoyu fare ile
tıklamak tutmuyor; `input#no` üzerinde `.click()` gerekiyor.)

Beş kademeli cascade, her kademe bir POST ile doluyor:

```
#CarType            B=Binek, T=Ticari
#carModel           GetModel
#carEngineType      /FWebApi/MaintenanceMenu/GetEngineCode
#carTransmissionType
#carMaintenanceType 6018..6027  = 1..10. yıl / 15.000..150.000 km
```

Sorgula → `/FWebApi/MaintenanceMenu/ListAvailableMtncMenu`
ve `/FWebApi/MaintenanceMenu/ListMtncMenuLine`

## İstek gövdesi

```json
{"Request":{"periodId":"6019","ptvl":"CF7","engineCode":"EN Q0",
            "engineCodeDesc":"1.0L ECOBOOST MHEV 160 PS",
            "transmissionDesc":"7 İLERİ OTOMATİK","transmissionCode":"TR GH"},
 "secret":"<reCAPTCHA v3 token>"}
```

## ⚠ Ana kısıt

`secret` alanı reCAPTCHA v3 token'ı. **Düz HTTP çekici (requests) çalışmaz** —
Hyundai'deki PDF indirme yaklaşımı burada geçerli değil. Ford hattı gerçek
tarayıcı sürerek koşmalı (Playwright / Chrome). Ayda bir koşacağı için kabul
edilebilir, ama Hyundai'den pahalı bir hat.

## Örnek çıktı (doğrulandı)

```
Açıklama : PUMA (2024-) 1.0L ECOBOOST 155PS AT 2.YIL BAKIM
Fiyat    : 25.009 TL
İçerik   : HAVA FİLTRESİ, KABİN FİLTRESİ, TEMİZLEME SPREYİ, FREN HİDROLİĞİ,
           0W/20 MOTOR YAĞI, KARTER TAPASI, İŞÇİLİK, YAĞ FİLTRESİ
```

Fiyatlar KDV dahil ve **tavan fiyat** — sitede böyle etiketlenmeli, Hyundai
verisiyle aynı kefeye konmamalı.

## Kapsam

- Binek 13 model: Explorer PHEV, Bronco Sport, Capri/Explorer, EcoSport, Edge,
  Fiesta, Focus (2015-2018), Focus (2018-), Kuga (2013-2020), Kuga (2020-),
  Mondeo, Mustang Mach-E, Puma
- Ticari 12 model: Connect ×3, Courier ×2, F-150, Ranger ×2, Transit ×2,
  Transit/Tourneo Custom ×2

Kaba tahmin: ~25 model × ~4 motor × ~2 şanzıman × 10 bakım = **~1.000 sorgu**.
Model başına motor/şanzıman sayısı değişken, gerçek sayı ilk tam gezinmede çıkar.
