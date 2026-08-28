# FC26 Squad Sync - Public Website

Bu klasör, GitHub Pages üzerinde ücretsiz çalışan **FC26 Squad Sync** web uygulamasıdır.

Canlı adres: `https://BunyaminBayraktar.github.io/fc26-control/`

## Özellikler

- PS5 üzerinde takım takım hızlı transfer akışı
- `YAPILDI / ATLA` ilerlemesini kullanıcının kendi tarayıcısında saklama
- Takım bazında tamamlanma panosu
- Oyuncu, takım ve ilerleme durumuna göre arama/filtreleme
- Seçili takım veya filtreli görünüm için paylaşılabilir bağlantı
- Mobil ve masaüstü uyumlu arayüz

## 1. Site verisini üret

Proje kökünde:

```powershell
python .\build_web.py
```

Bu komut `output_final` CSV dosyalarından `docs/data.json` üretir.

## 2. GitHub'a gönder

Repository public olmalı.

Örnek:

```powershell
git init
git add .
git commit -m "FC26 Control public site"
git branch -M main
git remote add origin https://github.com/KULLANICI_ADIN/fc26-control.git
git push -u origin main
```

## 3. GitHub Pages aç

GitHub repository:

Settings → Pages

- Source: Deploy from a branch
- Branch: main
- Folder: /docs

Save.

Site birkaç dakika içinde GitHub Pages adresinde açılır.

adresinde açılır.

## Kullanıcı ilerlemesi

PS5 Hızlı Mod'daki "YAPILDI / ATLA" kayıtları sunucuya gönderilmez.

Her ziyaretçinin ilerlemesi kendi tarayıcısındaki `localStorage` içinde tutulur.
Bu yüzden kullanıcılar birbirinin ilerlemesini değiştirmez.

## Google AdSense

Auto Ads yayıncı kimliği: `ca-pub-9303540424921408`

- AdSense kodu `docs/index.html` ve `docs/privacy.html` içinde bulunur.
- Yetkili satıcı kaydı `docs/ads.txt` içindedir.
- Google AdSense panelinde Auto Ads ve Avrupa düzenlemeleri için Google CMP mesajı ayrıca etkinleştirilmelidir.
- GitHub Pages proje adresinde `ads.txt`, `/fc26-control/ads.txt` altında kalır. AdSense için dosyanın alan adı kökünde `/ads.txt` olarak sunulması gerekir; özel alan adı bağlandığında `docs/ads.txt` doğru kök konuma taşınmış olur.
