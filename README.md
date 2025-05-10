# Haber Sitesi Projesi

Bu proje, modern bir haber sitesi oluşturmak için tasarlanmış bir Django uygulamasıdır.

## Özellikler

- Kategori bazlı haber yönetimi
- Manşet haberleri
- Son dakika haber bandı
- Reklam yönetimi (banner, sidebar vb.)
- İlan vitrini
- Hava durumu ve ekonomik göstergelerin takibi
- Otomatik haber çekme (Web Scraping)
- Arama fonksiyonu
- Yorumlar
- Responsive tasarım

## Kurulum

1. Repoyu klonlayın:
```
git clone https://github.com/yourusername/haber.git
cd haber
```

2. Sanal ortam oluşturun ve aktif edin:
```
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate  # Windows
```

3. Gerekli paketleri yükleyin:
```
pip install -r requirements.txt
```

4. Veritabanı migrasyonlarını uygulayın:
```
python manage.py migrate
```

5. Admin kullanıcısı oluşturun:
```
python manage.py createsuperuser
```

6. Geliştirme sunucusunu başlatın:
```
python manage.py runserver
```

## Otomatik Haber Çekme Sistemi

Proje, çeşitli haber kaynaklarından otomatik olarak haber çekme özelliğine sahiptir. Şu anda aşağıdaki kaynaklar desteklenmektedir:

### TEKHA (Tek Haber Ajansı)

TEKHA sitesinden Abdullah Solmaz ve diğer ilgili haberler otomatik olarak çekilip siteye eklenebilir.

#### Kullanım:

```bash
# Test modu (haberleri veritabanına kaydetmez)
python manage.py fetch_tekha_news --test

# Maksimum 5 haber çek ve kaydet
python manage.py fetch_tekha_news --limit=5

# Var olan haberleri de güncelle
python manage.py fetch_tekha_news --force-update
```

#### Otomatik Çalıştırma (Cron Job):

Tüm haber kaynaklarından düzenli olarak haber çekmek için:

```bash
# Tüm aktif kaynakları kontrol et
python manage.py fetch_tekha_cron --all

# Belirli sayıda haber çek
python manage.py fetch_tekha_cron --limit=10

# Log dosyasına kaydet
python manage.py fetch_tekha_cron --log-file=logs/haberler.log
```

Windows için Task Scheduler veya Linux için crontab kullanarak bu komutu otomatik çalıştırabilirsiniz.

#### Windows Task Scheduler Örneği (3 saatte bir çalıştırma):

```
powershell -command "cd C:\path\to\project && C:\path\to\venv\python.exe manage.py fetch_tekha_cron --all --log-file=logs/haberler.log"
```

#### Linux Crontab Örneği (3 saatte bir çalıştırma):

```
0 */3 * * * cd /path/to/project && /path/to/venv/bin/python manage.py fetch_tekha_cron --all --log-file=logs/haberler.log
```

## Yönetim Paneli

Admin paneline `/admin` adresinden erişebilirsiniz. Burada haberler, kategoriler, yorumlar, reklamlar ve haber kaynaklarını yönetebilirsiniz.

## Lisans

Bu proje MIT lisansı altında lisanslanmıştır. Detaylar için LICENSE dosyasına bakın. 