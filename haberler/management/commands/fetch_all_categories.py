import requests
import logging
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.files.base import ContentFile
from django.contrib.auth.models import User
from django.utils.text import slugify
from haberler.models import Haber, Kategori, HaberKaynagi
from urllib.parse import urljoin
import re

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'TEKHA sitesinden tüm kategorilerdeki haberleri çeker'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=100,
            help='Çekilecek maksimum haber sayısı'
        )
        parser.add_argument(
            '--force-update',
            action='store_true',
            default=False,
            help='Varolan haberleri de kontrol et ve güncelle'
        )
        parser.add_argument(
            '--test',
            action='store_true',
            default=False,
            help='Test modu - haberleri kaydetme'
        )
        parser.add_argument(
            '--max-pages',
            type=int,
            default=5,
            help='Her kategoride aranacak maksimum sayfa sayısı'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            default=False,
            help='Daha fazla çıktı göster'
        )

    def clean_html_content(self, content_element):
        """
        HTML içeriğini temizler ve haber için uygun formata getirir
        İstenmeyen etiketleri, reklamları ve gereksiz öğeleri kaldırır
        """
        # Kopya üzerinde çalışalım, orijinali değiştirmeyelim
        if isinstance(content_element, str):
            cleaned_element = BeautifulSoup(content_element, 'html.parser')
        else:
            cleaned_element = BeautifulSoup(str(content_element), 'html.parser')
        
        # İstenmeyen elementleri temizle
        for unwanted in cleaned_element.find_all(['script', 'style', 'iframe', 'form', 'button', 'nav', 'footer', 'aside']):
            unwanted.decompose()
        
        # Reklamları ve gereksiz öğeleri kaldır
        ad_banner_pattern = re.compile(r'ad|banner|widget|comment|sidebar|footer|post-details-share')
        for div in cleaned_element.find_all(['div', 'section'], class_=lambda c: c and ad_banner_pattern.search(c)):
            div.decompose()
        
        # Sosyal medya butonlarını kaldır
        social_pattern = re.compile(r'social|share|facebook|twitter|instagram')
        for social in cleaned_element.find_all(['div', 'span', 'a'], class_=lambda c: c and social_pattern.search(c)):
            social.decompose()
        
        # İlgili haberler, benzer içerikler vb. kaldır
        related_pattern = re.compile(r'related|similar|more|post-nav|navigation')
        for related in cleaned_element.find_all(['div', 'section'], class_=lambda c: c and related_pattern.search(c)):
            related.decompose()
            
        # Yazar bilgilerini içerebilecek imza satırlarını temizle
        # Yaygın yazar imza kalıpları - derlenen regex objeleri
        author_patterns = [
            re.compile(r'[A-Z][a-z]+\s+[A-Z][a-zÇçĞğİıÖöŞşÜü]+-[A-Z]+/TEKHA$', re.IGNORECASE),  # Ad Soyad-ŞEHİR/TEKHA (satır sonu)
            re.compile(r'[A-Z][a-z]+\s+[A-Z][a-zÇçĞğİıÖöŞşÜü]+/[A-Z]+$', re.IGNORECASE),  # Ad Soyad/ŞEHİR (satır sonu)
            re.compile(r'[A-Z][a-z]+\s+[A-Z][a-zÇçĞğİıÖöŞşÜü]+[-/][A-Z]+$', re.IGNORECASE),  # Ad Soyad-ŞEHİR veya Ad Soyad/ŞEHİR (satır sonu)
            re.compile(r'[A-Z][a-z]+\s+[A-Z][a-zÇçĞğİıÖöŞşÜü]+\s+[A-Z]+$', re.IGNORECASE),  # Ad Soyad ŞEHİR (satır sonu)
            re.compile(r'^Haber[:\s]+[A-Z][a-z]+\s+[A-Z][a-zÇçĞğİıÖöŞşÜü]+', re.IGNORECASE),  # Haber: Ad Soyad (satır başı)
            re.compile(r'^Kaynak[:\s]+TEKHA', re.IGNORECASE),  # Kaynak: TEKHA (satır başı)
            re.compile(r'^TEKHA\s+HABER\s+AJANSI', re.IGNORECASE),  # TEKHA HABER AJANSI (satır başı)
            re.compile(r'[A-Z][A-ZÇĞİÖŞÜ]+\s+[A-Z][A-ZÇĞİÖŞÜ]+-[A-Z]+/[A-Z]+$', re.IGNORECASE),  # BÜYÜK AD SOYAD-ŞEHİR/AJANS (satır sonu)
            re.compile(r'Birol\s+Güngördü\s*/?\s*Çanakkale\s*[-/]?\s*TEKHA$', re.IGNORECASE),  # Birol Güngördü/Çanakkale TEKHA (satır sonu)
            re.compile(r'Hüseyin\s+[zZ]orkun\s*[hH]atay\s*[-/]?\s*[tT][eE][kK][hH][aA]$', re.IGNORECASE),  # Hüseyin Zorkun Hatay-TEKHA (satır sonu)
            # YENİ: Burak Birol için eklenen desenler
            re.compile(r'Burak\s+Birol\s*[/-]?\s*[^/\n]*\s*[-/]?\s*TEKHA$', re.IGNORECASE),  # Burak Birol
            re.compile(r'BURAK\s+BIROL\s*[/-]?\s*[^/\n]*\s*[-/]?\s*TEKHA$', re.IGNORECASE),  # BURAK BIROL
            re.compile(r'Burak\s+BİROL\s*[–\-/]?\s*BURSA\s*[–\-/]?\s*TEKHA$', re.IGNORECASE),  # Burak BİROL BURSA
            re.compile(r'BURAK\s+BİROL\s*[–\-/]?\s*BURSA\s*[–\-/]?\s*TEKHA$', re.IGNORECASE),  # BURAK BİROL BURSA
            re.compile(r'Burak\s+BİROL\s*–\s*BURSA\s*/\s*TEKHA$', re.IGNORECASE),  # Burak BİROL – BURSA / TEKHA
            re.compile(r'BURAK\s+BİROL\s*–\s*BURSA\s*/\s*TEKHA$', re.IGNORECASE),  # BURAK BİROL – BURSA / TEKHA
            # YENİ: Hüseyin Zorkun için geliştirilmiş desenler
            re.compile(r'HÜSEYIN\s+ZORKUN\s*[/-]?\s*HATAY\s*[-/]?\s*TEKHA$', re.IGNORECASE),  # HÜSEYIN ZORKUN HATAY
            re.compile(r'Hᴜ̈SᴇYİN\s+Zᴏʀᴋᴜɴ\s*[/\s-]*\s*HATAY\s*[-–/]?\s*TEKHA$', re.IGNORECASE),  # Özel karakter
            re.compile(r'HUSEYIN\s+ZORKUN\s*[/\s-]*\s*HATAY\s*[-–/]?\s*TEKHA$', re.IGNORECASE),  # Türkçe karakter olmadan
            # YENİ: Hüseyin Polattimur için eklenen desenler
            re.compile(r'Hüseyin\s+Polattimur\s*[/-]?\s*Kocaeli\s*[-/]?\s*TEKHA$', re.IGNORECASE),  # Hüseyin Polattimur Kocaeli
            re.compile(r'HÜSEYIN\s+POLATTIMUR\s*[/-]?\s*KOCAELI\s*[-/]?\s*TEKHA$', re.IGNORECASE),  # HÜSEYIN POLATTIMUR KOCAELI
            # YENİ: Abdullah Solmaz için eklenen desenler
            re.compile(r'ABDULLAH\s+SOLMAZ[-\s/]*GAZİANTEP/?TEKHA$', re.IGNORECASE),  # Abdullah Solmaz Gaziantep
            re.compile(r'[A-Z][a-zÇçĞğİıÖöŞşÜü]+\s+[A-Z][a-zÇçĞğİıÖöŞşÜü]+\s*[-/]?\s*TEKHA$', re.IGNORECASE)  # Herhangi bir Yazar TEKHA (satır sonu)
        ]
        
        # Kesin yazar patternları - bunları satır içinde de arayacağız
        exact_author_patterns = [
            re.compile(r'Kaynak[:\s]+TEKHA', re.IGNORECASE),  # Kaynak: TEKHA
            re.compile(r'TEKHA\s+HABER\s+AJANSI', re.IGNORECASE),  # TEKHA HABER AJANSI
        ]
        
        # HTML içeriğindeki imza satırlarını temizle
        # 0. YENİ: Başlık ve alt başlıklarda yazar bilgisi kontrolü - haber başlıklarında yazar bilgisi olabilir
        for header in cleaned_element.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            if header.text:
                header_text = header.text.strip()
                
                # Sadece yazar bilgisi içeren başlıkları temizle
                yazar_bulundu_baslik = False
                
                # Tüm yazar desenleri için kontrol et
                for pattern in author_patterns + exact_author_patterns:
                    if pattern.search(header_text):
                        # Başlık yazar bilgisi içeriyorsa ve çok uzun değilse temizle
                        if len(header_text.split()) <= 20:
                            header.decompose()
                            yazar_bulundu_baslik = True
                            break
                        else:
                            # Uzun başlıkta sadece yazar kısmını temizle
                            cleaned_header = pattern.sub('', header_text)
                            cleaned_header = re.sub(r'\s+', ' ', cleaned_header).strip()
                            # Başlık çok kısalırsa komple sil
                            if len(cleaned_header.split()) >= 3:
                                header.string = cleaned_header
                            else:
                                header.decompose()
                            yazar_bulundu_baslik = True
                            break
                
                if yazar_bulundu_baslik:
                    break
        
        # 1. Strong etiketleri kontrol et - yazarlar genelde strong içinde olur
        for strong in cleaned_element.find_all('strong'):
            if strong.text and len(strong.text.strip()) < 50:  # Uzun strong içerikleri atla, bunlar başlık olabilir
                # Strong içindeki metin tam bir satırsa - muhtemelen yazar bilgisidir
                if strong.text.strip() and not strong.find_all():  # Alt elemanı yoksa
                    for pattern in author_patterns:
                        if pattern.search(strong.text.strip()):
                            strong.decompose()
                            break
        
        # 2. Sadece belirli paragraflarda yazar bilgisi temizleme
        for p in cleaned_element.find_all(['p', 'div', 'span']):
            if p.text and len(p.text.strip()) < 100:  # Kısa paragraflar
                p_text = p.text.strip()
                
                # a) Yazar bilgisi genellikle tek satır olur ve paragraf başında veya sonunda olur
                if len(p_text.split('\n')) <= 2 and len(p_text.split()) <= 10:
                    for pattern in author_patterns:
                        if pattern.search(p_text):
                            p.decompose()
                            break
                
                # b) Kesin yazar patternlarını içeren herhangi bir paragrafı temizle
                for pattern in exact_author_patterns:
                    if pattern.search(p_text):
                        p.decompose()
                        break
        
        # 3. Son paragrafları özel olarak kontrol et (genellikle yazar imzası içerir)
        paragraphs = cleaned_element.find_all('p')
        if len(paragraphs) > 2:
            for p in paragraphs[-3:]:  # Son 3 paragrafı kontrol et
                if p.text and len(p.text.strip()) < 100:  # Kısa paragraflar
                    p_text = p.text.strip()
                    
                    # İmza satırı genellikle kısa olur ve özel karakterler içerir
                    if ('TEKHA' in p_text or '/' in p_text or '-' in p_text) and len(p_text.split()) <= 10:
                        # Tüm desenleri kontrol et
                        for pattern in author_patterns:
                            if pattern.search(p_text):
                                p.decompose()
                                break
        
        # Boş paragrafları temizle
        for p in cleaned_element.find_all('p'):
            if len(p.get_text(strip=True)) == 0 and not p.find_all(['img']):
                p.decompose()
        
        # Stil ve sınıf özelliklerini temizle, ancak img ve bağlantı etiketlerindeki stil ve sınıfları koru
        for tag in cleaned_element.find_all(True):
            if tag.name not in ['img', 'a']:
                if tag.has_attr('style'):
                    del tag['style']
                if tag.has_attr('class'):
                    del tag['class']
        
        # Sadece içerik divini döndür, diğer etiketleri atla
        if cleaned_element.body:
            return cleaned_element.body
        else:
            return cleaned_element

    def handle(self, *args, **options):
        # Parametreleri al
        limit = options['limit']
        test_mode = options['test']
        force_update = options['force_update']
        verbose = options.get('verbose', False)
        max_pages = options['max_pages']
        
        self.stdout.write(self.style.SUCCESS(f'TEKHA sitesinden tüm kategorilerdeki haberleri çekiliyor (limit: {limit})'))
        
        # Kaynak kontrol edilir veya oluşturulur
        kaynak, created = HaberKaynagi.objects.get_or_create(
            url='https://www.tekha.com.tr',
            defaults={
                'ad': 'Tek Haber Ajansı (TEKHA)',
                'aktif': True,
                'aranan_kelimeler': 'TEKHA, Haber',
            }
        )
        
        if created:
            self.stdout.write(self.style.SUCCESS('Yeni haber kaynağı oluşturuldu: TEKHA'))
        
        if not kaynak.aktif:
            self.stdout.write(self.style.WARNING('Bu kaynak pasif durumda. İşlem iptal edildi.'))
            return
        
        # Admin kullanıcısını bul veya oluştur (otomatik haberler için)
        try:
            admin_user = User.objects.get(username='admin')
        except User.DoesNotExist:
            admin_user = User.objects.filter(is_superuser=True).first()
            if not admin_user:
                self.stdout.write(self.style.ERROR('Sistemde admin kullanıcısı bulunamadı!'))
                return
        
        # Kategori kontrolü
        try:
            default_kategori = Kategori.objects.get(ad='Genel')
        except Kategori.DoesNotExist:
            default_kategori = Kategori.objects.create(ad='Genel', slug='genel')
            self.stdout.write(self.style.SUCCESS('Genel kategorisi oluşturuldu'))
        
        # Kategori eşleştirme sözlüğü
        kategori_eslesme = {
            'spor': 'Spor',
            'ekonomi': 'Ekonomi',
            'siyaset': 'Siyaset',
            'gündem': 'Gündem',
            'gundem': 'Gündem',
            'asayiş': 'Asayiş',
            'asayis': 'Asayiş',
            'eğitim': 'Eğitim', 
            'egitim': 'Eğitim',
            'yaşam': 'Yaşam',
            'yasam': 'Yaşam',
            'sağlık': 'Sağlık',
            'saglik': 'Sağlık',
            'teknoloji': 'Teknoloji',
            'bilim': 'Bilim & Teknoloji',
            'kültür': 'Kültür Sanat',
            'kultur': 'Kültür Sanat',
            'sanat': 'Kültür Sanat',
            'dünya': 'Dünya',
            'dunya': 'Dünya',
            'magazin': 'Magazin'
        }
        
        # Haberleri topla
        haber_linkleri = []
        
        try:
            # Tüm kategori sayfalarını tara
            kategoriler = ['gundem', 'asayis', 'siyaset', 'ekonomi', 'spor', 'genel', 'meteoroloji', 'politika', 'dunya', 'egitim', 'yasam', 'kultur-sanat']
            
            for kategori in kategoriler:  # Tüm kategorileri tara
                # Her kategori için son sayfaları kontrol et
                for page_num in range(1, max_pages + 1):
                    if page_num == 1:
                        kategori_url = f"https://www.tekha.com.tr/category/{kategori}/"
                    else:
                        kategori_url = f"https://www.tekha.com.tr/category/{kategori}/page/{page_num}/"
                    
                    self.stdout.write(f"Kategori sayfası kontrol ediliyor: {kategori_url}")
                    
                    try:
                        response = requests.get(kategori_url, timeout=10)
                        if response.status_code == 200:
                            soup = BeautifulSoup(response.content, 'html.parser')
                            
                            # Tüm haber linklerini bul
                            for link in soup.find_all('a', href=True):
                                url = link['href']
                                # Kategori, etiket ve sayfa bağlantılarını atla
                                if url.startswith('https://www.tekha.com.tr') and not any(x in url for x in ['/category/', '/tag/', '/page/', '/etiket/']):
                                    if url not in haber_linkleri:
                                        haber_linkleri.append(url)
                        elif response.status_code == 404:
                            # Bu kategori için daha fazla sayfa yok
                            self.stdout.write(f"{kategori} kategorisi için sayfa {page_num} bulunamadı, sonraki kategoriye geçiliyor")
                            break
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f'Kategori sayfası kontrol edilirken hata: {str(e)}'))
                    
                    # Her kategoride limit sayısına ulaştığımızda duralım
                    if len(haber_linkleri) >= limit:
                        break
                
                # Toplam limit sayısına ulaştığımızda duralım
                if len(haber_linkleri) >= limit:
                    break
            
            # Gereksiz sayfaları filtrele
            filtered_urls = []
            for url in haber_linkleri:
                # Gereksiz sayfaları atla (yazarlar, üye giriş vb.)
                if any(x in url for x in ['/yazarlar', '/uye-giris', '/nobetci-eczaneler', '/hava-durumu', '/namaz-vakitleri', '/puan-durumlari']):
                    continue
                # Ana sayfayı atla
                if url == 'https://www.tekha.com.tr' or url == 'https://www.tekha.com.tr/':
                    continue
                # Geçerli haberleri ekle
                filtered_urls.append(url)
            
            haber_linkleri = filtered_urls[:limit]  # Sadece limit kadar al
            
            self.stdout.write(self.style.SUCCESS(f'Toplam {len(haber_linkleri)} haber bağlantısı bulundu'))
            
            # Test modundaysa haberleri kaydetme
            if test_mode:
                self.stdout.write(self.style.WARNING('Test modu - Haberler kaydedilmedi.'))
                for url in haber_linkleri:
                    self.stdout.write(f'  - {url}')
                return
            
            # Veritabanında olmayan haberleri veya güncellenmesi gerekenleri işle
            islenecek_haberler = []
            for url in haber_linkleri:
                if force_update or not Haber.objects.filter(kaynak_url=url).exists():
                    islenecek_haberler.append(url)
            
            if not islenecek_haberler:
                self.stdout.write(self.style.WARNING('İşlenecek yeni haber bulunamadı.'))
                kaynak.son_kontrol = timezone.now()
                kaynak.save()
                return
            
            self.stdout.write(self.style.SUCCESS(f'Toplam {len(islenecek_haberler)} adet haber işlenecek.'))
            
            # Haberleri veritabanına kaydet
            for i, news_url in enumerate(islenecek_haberler, 1):
                try:
                    self.stdout.write(f'{i}/{len(islenecek_haberler)} - Haber çekiliyor: {news_url}')
                    
                    # Mevcut haberi kontrol et
                    existing_haber = None
                    if force_update:
                        existing_haber = Haber.objects.filter(kaynak_url=news_url).first()
                    
                    # Haber detayını çek
                    news_response = requests.get(news_url, timeout=15)
                    news_soup = BeautifulSoup(news_response.content, 'html.parser')
                    
                    # Başlık çek
                    title_element = news_soup.find('h1') or news_soup.find('h2')
                    if not title_element:
                        self.stdout.write(self.style.ERROR(f'Başlık bulunamadı: {news_url}'))
                        continue
                    
                    baslik = title_element.text.strip()
                    
                    # Yayın tarihini bul
                    yayin_tarihi = timezone.now()  # varsayılan değer
                    try:
                        # Meta bilgisinden yayın tarihi
                        published_meta = news_soup.find('meta', property='article:published_time')
                        if published_meta and published_meta.get('content'):
                            try:
                                yayin_tarihi = timezone.datetime.fromisoformat(published_meta.get('content').replace('Z', '+00:00'))
                            except ValueError:
                                pass
                    except Exception:
                        pass
                    
                    # İçerik çek
                    content_div = news_soup.find('div', class_='entry-content')
                    content_html = ""
                    
                    if content_div:
                        # İçeriği temizle
                        clean_content_div = self.clean_html_content(content_div)
                        content_html = str(clean_content_div)
                    else:
                        # Alternatif content arama
                        content_divs = news_soup.find_all('div', class_=lambda c: c and 'content' in c)
                        for div in content_divs:
                            if 'entry' in str(div.get('class', [])):
                                clean_div = self.clean_html_content(div)
                                content_html = str(clean_div)
                                break
                    
                    # İçerik bulunamadı: {news_url}
                    if not content_html:
                        self.stdout.write(self.style.ERROR(f'İçerik bulunamadı: {news_url}'))
                        continue
                    
                    # İçeriği işle
                    content_soup = BeautifulSoup(content_html, 'html.parser')
                    
                    # İçerik sonrası ek temizlik - yazar bilgilerini temizle
                    # Kısa paragrafları kontrol et
                    for p in content_soup.find_all(['p', 'div', 'span']):
                        if p.text and len(p.text.strip()) < 100:  # Kısa paragraflar
                            for pattern in author_patterns:
                                if pattern.search(p.text):
                                    p.decompose()
                                    break
                    
                    # Son paragrafları özel olarak kontrol et (genellikle yazar imzası içerir)
                    paragraphs = content_soup.find_all('p')
                    if len(paragraphs) > 2:
                        for p in paragraphs[-3:]:  # Son 3 paragrafı kontrol et
                            if p.text and len(p.text.strip()) < 100:  # Kısa paragraflar
                                if any('TEKHA' in p.text or 'kaynak' in p.text.lower() or '/' in p.text or '-' in p.text):
                                    for pattern in author_patterns:
                                        if pattern.search(p.text):
                                            p.decompose()
                                            break
                    
                    # İçeriğin son halini al
                    content_html = str(content_soup)
                    
                    # Özet oluştur
                    text_content = content_soup.get_text(strip=True)
                    ozet = text_content[:300] + '...' if len(text_content) > 300 else text_content
                    icerik = content_html
                    
                    # Resim URL'sini çek
                    resim_url = None
                    main_image = (news_soup.find('img', class_=lambda c: c and any(x in c for x in ['featured', 'main', 'post', 'thumbnail'])) or 
                                news_soup.find('meta', property='og:image'))
                    
                    if main_image:
                        if main_image.name == 'img':
                            resim_url = main_image.get('src')
                        else:  # meta tag
                            resim_url = main_image.get('content')
                    
                    if not resim_url:
                        # İçerikteki ilk resmi al
                        img = content_soup.find('img')
                        if img and img.get('src'):
                            resim_url = img.get('src')
                    
                    if resim_url and not resim_url.startswith('http'):
                        resim_url = urljoin('https://www.tekha.com.tr', resim_url)
                    
                    # Kategoriyi belirle
                    kategori = default_kategori
                    kategori_adi = None
                    
                    # URL'den kategori tahmini
                    if '/category/' in news_url:
                        kategori_path = news_url.split('/category/')[1].split('/')[0]
                        for key, value in kategori_eslesme.items():
                            if key in kategori_path:
                                kategori_adi = value
                                break
                    
                    # Meta etiketlerinden kategori
                    if not kategori_adi:
                        meta_category = news_soup.find('meta', property='article:section')
                        if meta_category and meta_category.get('content'):
                            meta_cat = meta_category.get('content').strip()
                            kategori_adi = meta_cat
                    
                    # Kategori sınıfından
                    if not kategori_adi:
                        category_element = news_soup.find('a', class_=lambda c: c and any(x in c for x in ['category', 'tag', 'section']))
                        if category_element:
                            kategori_adi = category_element.text.strip()
                    
                    # Kategori adını veritabanı için uygun formata çevir
                    if kategori_adi:
                        kategori_adi_lower = kategori_adi.lower()
                        final_kategori = None
                        
                        # Eşleşme ara
                        for key, value in kategori_eslesme.items():
                            if key == kategori_adi_lower or key in kategori_adi_lower:
                                final_kategori = value
                                break
                        
                        if not final_kategori:
                            final_kategori = "Genel"
                        
                        # Veritabanında kategoriyi oluştur veya al
                        kategori, _ = Kategori.objects.get_or_create(ad=final_kategori)
                    
                    # Varolan haberi güncelle
                    if existing_haber:
                        existing_haber.baslik = baslik
                        existing_haber.icerik = icerik
                        existing_haber.ozet = ozet
                        existing_haber.kategori = kategori
                        existing_haber.guncelleme_tarihi = timezone.now()
                        
                        # Resim varsa ve önceki resimden farklıysa güncelle
                        if resim_url:
                            try:
                                img_response = requests.get(resim_url, stream=True, timeout=10)
                                if img_response.status_code == 200:
                                    if existing_haber.resim:
                                        existing_haber.resim.delete(save=False)
                                    
                                    img_name = f"tekha_{existing_haber.slug}.jpg"
                                    existing_haber.resim.save(
                                        img_name, 
                                        ContentFile(img_response.content), 
                                        save=False
                                    )
                            except Exception as e:
                                self.stdout.write(self.style.WARNING(f'Resim güncelleme hatası: {str(e)}'))
                        
                        existing_haber.save()
                        self.stdout.write(self.style.SUCCESS(f'Haber güncellendi: {baslik}'))
                        
                    else:
                        # Yeni haber için slug oluştur
                        slug = slugify(baslik)
                        original_slug = slug
                        counter = 1
                        while Haber.objects.filter(slug=slug).exists():
                            slug = f"{original_slug}-{counter}"
                            counter += 1
                        
                        # Yeni haber nesnesi oluştur
                        haber = Haber(
                            baslik=baslik,
                            slug=slug,
                            icerik=icerik,
                            ozet=ozet,
                            yazar=admin_user,
                            kategori=kategori,
                            kaynak=kaynak,
                            kaynak_url=news_url,
                            otomatik_eklendi=True,
                            yayin_tarihi=yayin_tarihi
                        )
                        
                        # Resim varsa indir ve kaydet
                        if resim_url:
                            try:
                                img_response = requests.get(resim_url, stream=True, timeout=10)
                                if img_response.status_code == 200:
                                    img_name = f"tekha_{slug}.jpg"
                                    haber.resim.save(
                                        img_name, 
                                        ContentFile(img_response.content), 
                                        save=False
                                    )
                            except Exception as e:
                                self.stdout.write(self.style.WARNING(f'Resim indirme hatası: {str(e)}'))
                        
                        # Haberi kaydet
                        haber.save()
                        self.stdout.write(self.style.SUCCESS(f'Yeni haber kaydedildi: {baslik}'))
                        
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'Haber işleme hatası: {str(e)}'))
            
            # Son kontrol tarihini güncelle
            kaynak.son_kontrol = timezone.now()
            kaynak.save()
            
            self.stdout.write(self.style.SUCCESS('İşlem tamamlandı!'))
            
        except requests.RequestException as e:
            self.stdout.write(self.style.ERROR(f'Bağlantı hatası: {str(e)}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Beklenmeyen hata: {str(e)}')) 