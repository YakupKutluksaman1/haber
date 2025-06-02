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
            
        # GELİŞTİRİLMİŞ yazar bilgilerini içerebilecek imza satırlarını temizle
        # Yaygın yazar imza kalıpları - derlenen regex objeleri
        author_patterns = [
            # Orijinal desenler
            re.compile(r'[A-Z][a-z]+\s+[A-Z][a-zÇçĞğİıÖöŞşÜü]+-[A-Z]+/TEKHA$', re.IGNORECASE),
            re.compile(r'[A-Z][a-z]+\s+[A-Z][a-zÇçĞğİıÖöŞşÜü]+/[A-Z]+$', re.IGNORECASE),
            re.compile(r'[A-Z][a-z]+\s+[A-Z][a-zÇçĞğİıÖöŞşÜü]+[-/][A-Z]+$', re.IGNORECASE),
            re.compile(r'[A-Z][a-z]+\s+[A-Z][a-zÇçĞğİıÖöŞşÜü]+\s+[A-Z]+$', re.IGNORECASE),
            re.compile(r'^Haber[:\s]+[A-Z][a-z]+\s+[A-Z][a-zÇçĞğİıÖöŞşÜü]+', re.IGNORECASE),
            re.compile(r'^Kaynak[:\s]+TEKHA', re.IGNORECASE),
            re.compile(r'^TEKHA\s+HABER\s+AJANSI', re.IGNORECASE),
            re.compile(r'[A-Z][A-ZÇĞİÖŞÜ]+\s+[A-Z][A-ZÇĞİÖŞÜ]+-[A-Z]+/[A-Z]+$', re.IGNORECASE),
            
            # YENİ: ABDULLAH SOLMAZ formatı için özel desenler
            re.compile(r'ABDULLAH\s+SOLMAZ[-\s/]*GAZİANTEP[-\s/]*TEKHA', re.IGNORECASE),
            re.compile(r'ABDULLAH\s+SOLMAZ[-\s]*GAZİANTEP[-\s/]*TEKHA', re.IGNORECASE),
            re.compile(r'ABDULLAH\s+SOLMAZ\s*-\s*GAZİANTEP\s*/?\s*TEKHA', re.IGNORECASE),
            
            # YENİ: Hüseyin ZORKUN için geliştirilmiş desenler
            re.compile(r'Hüseyin\s+ZORKUN\s*/\s*Hatay[-\s]*TEKHA', re.IGNORECASE),
            re.compile(r'HÜSEYIN\s+ZORKUN\s*/\s*HATAY[-\s]*TEKHA', re.IGNORECASE),
            re.compile(r'Hüseyin\s+ZORKUN\s*/\s*Hatay\s*-\s*TEKHA', re.IGNORECASE),
            re.compile(r'HÜSEYIN\s+ZORKUN\s*/\s*HATAY\s*-\s*TEKHA', re.IGNORECASE),
            re.compile(r'Hüseyin\s+ZORKUN\s*/\s*HATAY\s*–\s*TEKHA', re.IGNORECASE),  # uzun tire
            re.compile(r'HÜSEYIN\s+ZORKUN\s*/\s*HATAY\s*–\s*TEKHA', re.IGNORECASE),  # uzun tire
            
            # YENİ: Salih ÜSTÜNDAĞ için özel desenler
            re.compile(r'Salih\s+ÜSTÜNDAĞ[-\s]*TEKHA\s*/\s*ISPARTA', re.IGNORECASE),
            re.compile(r'SALİH\s+ÜSTÜNDAĞ[-\s]*TEKHA\s*/\s*ISPARTA', re.IGNORECASE),
            re.compile(r'Salih\s+ÜSTÜNDAĞ\s*-\s*TEKHA\s*/\s*ISPARTA', re.IGNORECASE),
            re.compile(r'SALİH\s+ÜSTÜNDAĞ\s*-\s*TEKHA\s*/\s*ISPARTA', re.IGNORECASE),
            re.compile(r'Salih\s+ÜSTÜNDAĞ[-\s/]*TEKHA[-\s/]*ISPARTA', re.IGNORECASE),
            re.compile(r'SALİH\s+ÜSTÜNDAĞ[-\s/]*TEKHA[-\s/]*ISPARTA', re.IGNORECASE),
            
            # YENİ: Halil Azizoğlu için özel desenler
            re.compile(r'Halil\s+Azizoğlu\s*-\s*TEKHA\s*-\s*Gazeteci\s*/\s*YAZar', re.IGNORECASE),
            re.compile(r'HALİL\s+AZİZOĞLU\s*-\s*TEKHA\s*-\s*GAZETECİ\s*/\s*YAZAR', re.IGNORECASE),
            re.compile(r'Halil\s+Azizoğlu\s*-\s*TEKHA\s*-\s*Gazeteci', re.IGNORECASE),
            re.compile(r'HALİL\s+AZİZOĞLU\s*-\s*TEKHA\s*-\s*GAZETECİ', re.IGNORECASE),
            re.compile(r'Halil\s+Azizoğlu[-\s]*TEKHA[-\s]*Gazeteci', re.IGNORECASE),
            re.compile(r'HALİL\s+AZİZOĞLU[-\s]*TEKHA[-\s]*GAZETECİ', re.IGNORECASE),
            
            # Diğer özel yazar formatları
            re.compile(r'Birol\s+Güngördü\s*/?\s*Çanakkale\s*[-/]?\s*TEKHA$', re.IGNORECASE),
            re.compile(r'Hüseyin\s+[zZ]orkun\s*[hH]atay\s*[-/]?\s*[tT][eE][kK][hH][aA]$', re.IGNORECASE),
            re.compile(r'Burak\s+Birol\s*[/-]?\s*[^/\n]*\s*[-/]?\s*TEKHA$', re.IGNORECASE),
            re.compile(r'BURAK\s+BIROL\s*[/-]?\s*[^/\n]*\s*[-/]?\s*TEKHA$', re.IGNORECASE),
            re.compile(r'Burak\s+BİROL\s*[–\-/]?\s*BURSA\s*[–\-/]?\s*TEKHA$', re.IGNORECASE),
            re.compile(r'BURAK\s+BİROL\s*[–\-/]?\s*BURSA\s*[–\-/]?\s*TEKHA$', re.IGNORECASE),
            re.compile(r'Burak\s+BİROL\s*–\s*BURSA\s*/\s*TEKHA$', re.IGNORECASE),
            re.compile(r'BURAK\s+BİROL\s*–\s*BURSA\s*/\s*TEKHA$', re.IGNORECASE),
            re.compile(r'HÜSEYIN\s+ZORKUN\s*[/-]?\s*HATAY\s*[-/]?\s*TEKHA$', re.IGNORECASE),
            re.compile(r'Hᴜ̈SᴇYİN\s+Zᴏʀᴋᴜɴ\s*[/\s-]*\s*HATAY\s*[-–/]?\s*TEKHA$', re.IGNORECASE),
            re.compile(r'HUSEYIN\s+ZORKUN\s*[/\s-]*\s*HATAY\s*[-–/]?\s*TEKHA$', re.IGNORECASE),
            re.compile(r'Hüseyin\s+Polattimur\s*[/-]?\s*Kocaeli\s*[-/]?\s*TEKHA$', re.IGNORECASE),
            re.compile(r'HÜSEYIN\s+POLATTIMUR\s*[/-]?\s*KOCAELI\s*[-/]?\s*TEKHA$', re.IGNORECASE),
            
            # Genel yazar formatları (en sonda)
            re.compile(r'[A-ZÇĞİÖŞÜ]+\s+[A-ZÇĞİÖŞÜ]+\s*[-/]?\s*[A-ZÇĞİÖŞÜ]+\s*[-/]?\s*TEKHA', re.IGNORECASE),
            re.compile(r'[A-Z][a-zÇçĞğİıÖöŞşÜü]+\s+[A-Z][a-zÇçĞğİıÖöŞşÜü]+\s*[-/]?\s*TEKHA$', re.IGNORECASE),
            
            # YENİ: Gazeteci/Yazar unvanları içeren formatlar
            re.compile(r'[A-Z][a-zÇçĞğİıÖöŞşÜü]+\s+[A-Z][a-zÇçĞğİıÖöŞşÜü]+\s*-\s*TEKHA\s*-\s*Gazeteci', re.IGNORECASE),
            re.compile(r'[A-Z][a-zÇçĞğİıÖöŞşÜü]+\s+[A-Z][a-zÇçĞğİıÖöŞşÜü]+\s*-\s*TEKHA\s*-\s*GAZETECİ', re.IGNORECASE),
            re.compile(r'[A-Z][a-zÇçĞğİıÖöŞşÜü]+\s+[A-Z][a-zÇçĞğİıÖöŞşÜü]+\s*-\s*TEKHA\s*-\s*Yazar', re.IGNORECASE),
            re.compile(r'[A-Z][a-zÇçĞğİıÖöŞşÜü]+\s+[A-Z][a-zÇçĞğİıÖöŞşÜü]+\s*-\s*TEKHA\s*-\s*YAZAR', re.IGNORECASE),
            re.compile(r'[A-Z][a-zÇçĞğİıÖöŞşÜü]+\s+[A-Z][a-zÇçĞğİıÖöŞşÜü]+\s*-\s*TEKHA\s*-\s*[A-Z][a-z]+\s*/\s*[A-Z][a-z]+', re.IGNORECASE),
            
            # YENİ: Şehir adı sonra TEKHA formatları
            re.compile(r'[A-Z][a-zÇçĞğİıÖöŞşÜü]+\s+[A-ZÇĞİÖŞÜ]+\s*/\s*[A-Z][a-zÇçĞğİıÖöŞşÜü]+[-\s]*TEKHA', re.IGNORECASE),
            re.compile(r'[A-Z][a-zÇçĞğİıÖöŞşÜü]+\s+[A-ZÇĞİÖŞÜ]+[-\s]*TEKHA\s*/\s*[A-Z][a-zÇçĞğİıÖöŞşÜü]+', re.IGNORECASE),
            
            # YENİ: Daha geniş formatlar
            re.compile(r'[A-Z][a-zÇçĞğİıÖöŞşÜü]+\s+[A-ZÇĞİÖŞÜa-zçğıöşü]+\s*[-/]\s*TEKHA\s*[-/]\s*[A-Z][a-zÇçĞğİıÖöŞşÜü]+', re.IGNORECASE),
            
            # YENİ: Birol Güngördü için geliştirilmiş desenler  
            re.compile(r'BİROL\s+GÜNGÖRDÜ\s*/\s*ÇANAKKALE\s*–\s*TEKHA', re.IGNORECASE),
            re.compile(r'BIROL\s+GUNGORDU\s*/\s*CANAKKALE\s*–\s*TEKHA', re.IGNORECASE),
            re.compile(r'Birol\s+Güngördü\s*/\s*Çanakkale\s*–\s*TEKHA', re.IGNORECASE),
            re.compile(r'BİROL\s+GÜNGÖRDÜ\s*/\s*ÇANAKKALE\s*-\s*TEKHA', re.IGNORECASE),
            re.compile(r'BIROL\s+GUNGORDU\s*/\s*CANAKKALE\s*-\s*TEKHA', re.IGNORECASE),
            
            # YENİ: Hüseyin Polattimur için geliştirilmiş desenler
            re.compile(r'Hüseyin\s+POLATTIMUR\s*–\s*TEKHA\s*/\s*KOCAELI', re.IGNORECASE),
            re.compile(r'HÜSEYIN\s+POLATTIMUR\s*–\s*TEKHA\s*/\s*KOCAELI', re.IGNORECASE),
            re.compile(r'Hüseyin\s+POLATTIMUR\s*-\s*TEKHA\s*/\s*KOCAELI', re.IGNORECASE),
            re.compile(r'HÜSEYIN\s+POLATTIMUR\s*-\s*TEKHA\s*/\s*KOCAELI', re.IGNORECASE),
            re.compile(r'Hüseyin\s+POLATTIMUR\s*–\s*TEKHA\s*/\s*KOCAELİ', re.IGNORECASE),
            re.compile(r'HÜSEYIN\s+POLATTIMUR\s*–\s*TEKHA\s*/\s*KOCAELİ', re.IGNORECASE),
        ]
        
        # Kesin yazar patternları - bunları satır içinde de arayacağız
        exact_author_patterns = [
            re.compile(r'Kaynak[:\s]+TEKHA', re.IGNORECASE),
            re.compile(r'TEKHA\s+HABER\s+AJANSI', re.IGNORECASE),
            
            # YENİ: Ekran görüntüsündeki spesifik formatlar
            re.compile(r'BİROL\s+GÜNGÖRDÜ\s*/\s*ÇANAKKALE\s*–\s*TEKHA', re.IGNORECASE),
            re.compile(r'Hüseyin\s+ZORKUN\s*/\s*HATAY\s*–\s*TEKHA', re.IGNORECASE),
            re.compile(r'Hüseyin\s+POLATTIMUR\s*–\s*TEKHA\s*/\s*KOCAELI', re.IGNORECASE),
            
            # Genel TEKHA pattern'leri
            re.compile(r'[A-ZÇĞİÖŞÜa-zçğıöşü\s]+\s*/\s*[A-ZÇĞİÖŞÜa-zçğıöşü\s]+\s*[–\-]\s*TEKHA', re.IGNORECASE),
            re.compile(r'[A-ZÇĞİÖŞÜa-zçğıöşü\s]+\s*[–\-]\s*TEKHA\s*/\s*[A-ZÇĞİÖŞÜa-zçğıöşü\s]+', re.IGNORECASE),
        ]

        # 4. YENİ: HTML string üzerinde güvenli yazar temizleme
        # Text element parent sorunlarını önlemek için HTML string üzerinde çalışalım
        html_string = str(cleaned_element)
        
        # Önce basit string temizleme - yazar bilgilerini içeren satırları kaldır
        lines = html_string.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line_text = BeautifulSoup(line, 'html.parser').get_text().strip()
            is_author_line = False
            
            # Kısa satırları kontrol et (yazar bilgisi genelde kısa olur) - limit artırıldı
            if line_text and len(line_text.split()) <= 25:  # 15'ten 25'e çıkarıldı
                for pattern in author_patterns + exact_author_patterns:
                    if pattern.search(line_text):
                        is_author_line = True
                        break
            
            # TEKHA içeren tüm kısa satırları da kontrol et
            if not is_author_line and line_text and 'TEKHA' in line_text:
                if len(line_text.split()) <= 30:  # TEKHA içeren satırlar için daha yüksek limit
                    is_author_line = True
            
            # Yazar satırı değilse ekle
            if not is_author_line:
                cleaned_lines.append(line)
        
        # Temizlenmiş HTML'i tekrar birleştir ve parse et
        html_string = '\n'.join(cleaned_lines)
        cleaned_element = BeautifulSoup(html_string, 'html.parser')
        
        # İkinci geçiş: Kalan yazar bilgilerini temizle
        # Paragraf bazında temizlik
        for p in cleaned_element.find_all(['p', 'div', 'span', 'strong', 'em']):
            if p.text:
                p_text = p.text.strip()
                if p_text and len(p_text.split()) <= 30:  # Daha yüksek limit
                    for pattern in author_patterns + exact_author_patterns:
                        if pattern.search(p_text):
                            p.decompose()
                            break
                    
                    # TEKHA içeren elementleri de temizle
                    if 'TEKHA' in p_text and len(p_text.split()) <= 35:
                        # Basit heuristic: TEKHA + şehir/isim kombinasyonları
                        tekha_patterns = [
                            r'[A-ZÇĞİÖŞÜa-zçğıöşü\s]+[-–/]\s*TEKHA',
                            r'TEKHA\s*[-–/]\s*[A-ZÇĞİÖŞÜa-zçğıöşü\s]+',
                            r'[A-ZÇĞİÖŞÜa-zçğıöşü\s]+\s*/\s*[A-ZÇĞİÖŞÜa-zçğıöşü\s]+[-–]\s*TEKHA'
                        ]
                        for tekha_pattern in tekha_patterns:
                            if re.search(tekha_pattern, p_text, re.IGNORECASE):
                                p.decompose()
                                break
        
        # Üçüncü geçiş: Kalan TEKHA imzalarını basit string replacement ile temizle
        html_string = str(cleaned_element)
        
        # Bilinen yazar imzalarını doğrudan kaldır
        known_signatures = [
            'BİROL GÜNGÖRDÜ / ÇANAKKALE – TEKHA',
            'Birol Güngördü / Çanakkale – TEKHA',
            'BIROL GUNGORDU / CANAKKALE – TEKHA',
            'Hüseyin ZORKUN / HATAY – TEKHA', 
            'HÜSEYIN ZORKUN / HATAY – TEKHA',
            'Hüseyin POLATTIMUR – TEKHA / KOCAELI',
            'HÜSEYIN POLATTIMUR – TEKHA / KOCAELI',
            'Hüseyin POLATTIMUR – TEKHA / KOCAELİ',
            'ABDULLAH SOLMAZ-GAZİANTEP/TEKHA',
            'Abdullah Solmaz-Gaziantep/TEKHA',
            'Salih ÜSTÜNDAĞ- TEKHA /ISPARTA',
            'SALİH ÜSTÜNDAĞ- TEKHA /ISPARTA',
            'Halil Azizoğlu - TEKHA - Gazeteci/YAZar',
            'HALİL AZİZOĞLU - TEKHA - GAZETECİ/YAZAR'
        ]
        
        for signature in known_signatures:
            # Hem orijinal hem de çeşitli varyasyonlarını kaldır
            html_string = html_string.replace(signature, '')
            html_string = html_string.replace(signature.upper(), '')
            html_string = html_string.replace(signature.lower(), '')
        
        # Temizlenmiş HTML'i final parse et
        cleaned_element = BeautifulSoup(html_string, 'html.parser')
        
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
            # 1. ANA SAYFA'DAN HABER LİNKLERİ ÇEK
            self.stdout.write("Ana sayfa kontrol ediliyor...")
            try:
                ana_sayfa_response = requests.get('https://www.tekha.com.tr', timeout=10)
                if ana_sayfa_response.status_code == 200:
                    ana_sayfa_soup = BeautifulSoup(ana_sayfa_response.content, 'html.parser')
                    
                    # Ana sayfadaki tüm haber linklerini bul
                    for link in ana_sayfa_soup.find_all('a', href=True):
                        url = link['href']
                        if url.startswith('https://www.tekha.com.tr') and not any(x in url for x in ['/category/', '/tag/', '/page/', '/etiket/', '/yazarlar', '/uye-giris', '/nobetci-eczaneler', '/hava-durumu', '/namaz-vakitleri', '/puan-durumlari']):
                            if url not in haber_linkleri and url != 'https://www.tekha.com.tr' and url != 'https://www.tekha.com.tr/':
                                haber_linkleri.append(url)
                    
                    self.stdout.write(f"Ana sayfadan {len(haber_linkleri)} haber bulundu")
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'Ana sayfa kontrol edilirken hata: {str(e)}'))
            
            # 2. RSS FEED'DEN HABER LİNKLERİ ÇEK
            self.stdout.write("RSS feed kontrol ediliyor...")
            rss_urls = [
                'https://www.tekha.com.tr/rss',
                'https://www.tekha.com.tr/feed',
                'https://www.tekha.com.tr/rss.xml',
                'https://www.tekha.com.tr/feed.xml'
            ]
            
            for rss_url in rss_urls:
                try:
                    rss_response = requests.get(rss_url, timeout=10)
                    if rss_response.status_code == 200:
                        try:
                            # XML parser ile dene
                            rss_soup = BeautifulSoup(rss_response.content, 'xml')
                        except:
                            # XML parser yoksa html.parser kullan
                            rss_soup = BeautifulSoup(rss_response.content, 'html.parser')
                        
                        # RSS'deki haber linklerini bul
                        for item in rss_soup.find_all(['item', 'entry']):
                            link_element = item.find(['link', 'guid'])
                            if link_element:
                                url = link_element.text.strip() if link_element.text else link_element.get('href', '')
                                if url and url.startswith('https://www.tekha.com.tr') and url not in haber_linkleri:
                                    haber_linkleri.append(url)
                        
                        self.stdout.write(f"RSS feed'den toplam {len(haber_linkleri)} haber bulundu")
                        break  # İlk başarılı RSS'i kullan
                except Exception as e:
                    continue  # Sonraki RSS URL'sini dene
            
            # 3. GÜNCEL HABER SEKSİYONLARI
            self.stdout.write("Güncel haber seksiyonları kontrol ediliyor...")
            guncel_seksiyonlar = [
                'https://www.tekha.com.tr/son-dakika',
                'https://www.tekha.com.tr/son-haberler',
                'https://www.tekha.com.tr/guncel',
                'https://www.tekha.com.tr/anasayfa'
            ]
            
            for seksiyon_url in guncel_seksiyonlar:
                try:
                    seksiyon_response = requests.get(seksiyon_url, timeout=10)
                    if seksiyon_response.status_code == 200:
                        seksiyon_soup = BeautifulSoup(seksiyon_response.content, 'html.parser')
                        
                        for link in seksiyon_soup.find_all('a', href=True):
                            url = link['href']
                            if url.startswith('https://www.tekha.com.tr') and not any(x in url for x in ['/category/', '/tag/', '/page/', '/etiket/']):
                                if url not in haber_linkleri:
                                    haber_linkleri.append(url)
                except Exception:
                    continue
            
            # 4. KATEGORİ SAYFALARINDAN HABER ÇEK (mevcut kod)
            kategoriler = ['gundem', 'asayis', 'siyaset', 'ekonomi', 'spor', 'genel', 'meteoroloji', 'politika', 'dunya', 'egitim', 'yasam', 'kultur-sanat', 'saglik', 'teknoloji', 'magazin']
            
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
                if any(x in url for x in ['/yazarlar', '/uye-giris', '/nobetci-eczaneler', '/hava-durumu', '/namaz-vakitleri', '/puan-durumlari', '/kunye', '/iletisim', '/yayinlar']):
                    continue
                # Ana sayfayı atla
                if url == 'https://www.tekha.com.tr' or url == 'https://www.tekha.com.tr/':
                    continue
                # Kategori sayfalarını atla
                if '/category/' in url or '/tag/' in url or '/page/' in url:
                    continue
                # Çok kısa URL'leri atla (muhtemelen haber değil)
                if len(url.split('/')[-1]) < 10:
                    continue
                # Geçerli haberleri ekle
                filtered_urls.append(url)
            
            # Benzersiz URL'leri al ve limit uygula
            unique_urls = list(dict.fromkeys(filtered_urls))  # Sırayı koruyarak benzersiz yap
            haber_linkleri = unique_urls[:limit]  # Sadece limit kadar al
            
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
                    
                    # İçeriğin son halini al - clean_html_content zaten yazar bilgilerini temizlemiştir
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