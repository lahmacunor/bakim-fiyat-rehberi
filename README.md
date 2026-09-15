# Bakım Fiyat Rehberi

Türkiye'de periyodik bakım fiyatları — **tahmin değil**, markanın kendi
yayımladığı resmî tablodan. Her fiyat satırı kaynağını taşır.

Canlı: https://lahmacunor.github.io/bakim-fiyat-rehberi/

> ⚪ **Hat donduruldu (2026-09-15).** Kapsam dar: Türkiye'de resmî bakım fiyatı
> yayımlayan üç marka var (Hyundai, Ford, Kia) ve üçü de eklendi; park listesinin
> başındaki Renault/Fiat/VW/Toyota yayımlamıyor. Kod çalışır durumda, site canlı.
> Gerekçe ve geri açma adımları: vault `🏰 300-Projects/Bakim-Fiyat-Rehberi/Project.md`.

## Neden

Mevcut "araç masrafı hesaplama" siteleri bakımı tahmin ediyor ("ortalama
2.800–6.000 TL"). Oysa bazı markalar resmî fiyat tablolarını kendileri
yayımlıyor. Kimse bunları tek yerde birleştirmiyor — bu site onu yapıyor.

## Kullanım

```bash
python cek/hyundai.py   # resmi PDF'i indir, veri/hyundai/<tarih>.json uret
python cek/ford.py      # resmi hesaplayici API'sinden veri/ford/<tarih>.json uret
python cek/kia.py       # ICE + EV PDF'lerini bakim sayfasindan bulup cek
python test_parse.py    # parse dogrulugunu kontrol et
python uret.py          # docs/ altina statik siteyi uret
```

Aylık akış: markanın yeni tablosu çıkınca `cek/` script'indeki `KAYNAK_URL` ve
`KAYNAK_TARIH` güncellenir, komutlar sırayla çalıştırılır, commit + push.
Kia'da bu adım yok — PDF bağlantıları her çalıştırmada bakım sayfasından okunur.

Gerekenler: `pip install pypdf pdfplumber`.

## Kurallar

- **Yalnızca markanın kendi yayımladığı fiyat girer.** Bayi içi veri (BOS
  export'ları vb.) bu projeye **asla** girmez.
- Kaynağı olmayan sayı siteye girmez — `kaynak_url` + `kaynak_tarih` zorunlu.
- Marka logoları kullanılmaz, yalnızca marka adı.
- Her kaynağa ayda bir kez gidilir.
- Fiyat yayımlamayan marka için sayfa açılmaz (Fiat, Toyota, VW şu an kapsam dışı).

Kapsamdaki markalar: Hyundai (aylık PDF), Ford (resmî hesaplayıcı API),
Kia (aylık ICE + EV PDF).

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
