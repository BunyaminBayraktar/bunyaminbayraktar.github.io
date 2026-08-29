# Günlük Transfermarkt yenilemesi

GitHub Actions her gün yalnızca herkese açık Transfermarkt kulüp kadrolarını
kontrol eder. Güvenli biçimde FC26 oyuncusuyla eşleşen yeni kulüp değişiklikleri
`docs/data.json` dosyasına eklenir. Yaygın ağ, engelleme veya ayrıştırma hatasında
mevcut yayın verisi korunur.

Elle kontrol:

```bash
python automation/daily_refresh.py --validate-only
```

GitHub üzerinden elle çalıştırma:

`Actions` → `FC26 günlük kadro kontrolü` → `Run workflow`
