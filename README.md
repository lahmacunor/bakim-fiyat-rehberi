# Bakım Fiyat Rehberi

Türkiye'de periyodik bakım fiyatları — **tahmin değil**, markanın kendi
yayımladığı resmî tablodan. Her fiyat satırı kaynağını taşır.

Canlı: https://lahmacunor.github.io/bakim-fiyat-rehberi/

## Neden

Mevcut "araç masrafı hesaplama" siteleri bakımı tahmin ediyor ("ortalama
2.800–6.000 TL"). Oysa bazı markalar resmî fiyat tablolarını kendileri
yayımlıyor. Kimse bunları tek yerde birleştirmiyor — bu site onu yapıyor.

## Kullanım

```bash
python cek/hyundai.py   # resmi PDF'i indir, veri/hyundai/<tarih>.json uret
python cek/ford.py      # resmi hesaplayici API'sinden veri/ford/<tarih>.json uret
python test_parse.py    # parse dogrulugunu kontrol et
python uret.py          # docs/ altina statik siteyi uret
```

Aylık akış: markanın yeni tablosu çıkınca `cek/` script'indeki `KAYNAK_URL` ve
`KAYNAK_TARIH` güncellenir, üç komut sırayla çalıştırılır, commit + push.

## Kurallar

- **Yalnızca markanın kendi yayımladığı fiyat girer.** Bayi içi veri (BOS
  export'ları vb.) bu projeye **asla** girmez.
- Kaynağı olmayan sayı siteye girmez — `kaynak_url` + `kaynak_tarih` zorunlu.
- Marka logoları kullanılmaz, yalnızca marka adı.
- Her kaynağa ayda bir kez gidilir.
- Fiyat yayımlamayan marka için sayfa açılmaz (Fiat, Toyota, VW şu an kapsam dışı).

## Yapı

```
cek/<marka>.py    marka basina bagimsiz cekici, hepsi ayni JSON semasini uretir
veri/<marka>/     ham veri, tarihli
uret.py           veri -> statik HTML
sablon/           sayfa iskeleti + CSS
docs/             uretilen site (GitHub Pages buradan yayinlar)
```

Çekiciler kasıtlı olarak ortak bir arayüzle soyutlanmadı: her marka farklı
format veriyor (PDF, hesaplayıcı, HTML tablo). Sözleşme şema, sınıf değil.

Proje kararları ve gerekçeler: vault `🏰 300-Projects/Bakim-Fiyat-Rehberi/Project.md`
