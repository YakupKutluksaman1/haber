import requests
from bs4 import BeautifulSoup
import re
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'TEKHA sitesinin ana sayfasını ve yapısını analiz eder'

    def add_arguments(self, parser):
        parser.add_argument('url', type=str, nargs='?', default='https://www.tekha.com.tr/', help='Analiz edilecek URL (varsayılan: ana sayfa)')

    def handle(self, *args, **options):
        url = options['url']
        self.stdout.write(f"Analiz edilen URL: {url}")
        
        try:
            response = requests.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Ana sayfadaki taglerin analizini yap
            self.stdout.write("\n--- ANA SAYFA YAPISI ANALİZİ ---")
            
            # 1. Tüm makale ve div yapılarını bul
            articles = soup.find_all('article')
            self.stdout.write(f"\nToplam {len(articles)} makale (article tag) bulundu")
            
            # 2. İlk 3 article'ın sınıflarını ve link yapısını göster
            for i, article in enumerate(articles[:3]):
                self.stdout.write(f"\nMakale {i+1} detayları:")
                self.stdout.write(f"  CSS Sınıfları: {article.get('class', ['Sınıf yok'])}")
                
                # Makaledeki linkleri bul
                links = article.find_all('a', href=True)
                self.stdout.write(f"  Link sayısı: {len(links)}")
                
                for j, link in enumerate(links[:3]):
                    self.stdout.write(f"  Link {j+1}: {link['href']}")
                    self.stdout.write(f"    Link metni: {link.text.strip()[:50]}...")
                
                # Makale içindeki başlıkları bul
                titles = article.find_all(['h1', 'h2', 'h3', 'h4'])
                if titles:
                    self.stdout.write(f"  Başlıklar:")
                    for title in titles:
                        self.stdout.write(f"    {title.name}: {title.text.strip()[:50]}...")
            
            # 3. Ana sayfa yapısında kullanılan ana divleri analiz et
            main_divs = soup.find_all('div', class_=re.compile('content|container|main|wrapper|body'))
            self.stdout.write(f"\nAna sayfa yapısındaki önemli div sayısı: {len(main_divs)}")
            for i, div in enumerate(main_divs[:5]):
                self.stdout.write(f"  Div {i+1}: ID={div.get('id', 'ID yok')}, Sınıf={div.get('class', ['Sınıf yok'])}")
            
            # 4. Haber öğeleri için kullanılabilecek yapıları ara
            self.stdout.write("\n--- HABER ÖĞELERİ ARAŞTIRMASI ---")
            
            # a) Daha genel yapıdaki div'leri kontrol et 
            post_divs = soup.find_all(['div', 'article'], class_=re.compile('post|news|article|entry|item'))
            self.stdout.write(f"Haber içeriği olabilecek eleman sayısı: {len(post_divs)}")
            for i, div in enumerate(post_divs[:5]):
                self.stdout.write(f"  Eleman {i+1}: Tag={div.name}, Sınıf={div.get('class', ['Sınıf yok'])}")
                links = div.find_all('a', href=True)
                if links:
                    self.stdout.write(f"    İçindeki linkler: {len(links)}")
                    for link in links[:2]:
                        self.stdout.write(f"      Link: {link['href']}")
            
            # 5. Sitede yazar adı geçen elementleri ara
            self.stdout.write("\n--- YAZAR ADI İÇEREN ELEMENTLER ---")
            yazar_pattern = re.compile('ABDULLAH SOLMAZ', re.IGNORECASE)
            yazar_elements = soup.find_all(string=yazar_pattern)
            
            self.stdout.write(f"Yazar adı içeren element sayısı: {len(yazar_elements)}")
            for i, elem in enumerate(yazar_elements[:5]):
                parent = elem.parent
                self.stdout.write(f"  Element {i+1}: Parent tag={parent.name}, Parent sınıf={parent.get('class', ['Sınıf yok'])}")
                self.stdout.write(f"    İçerik: {elem.strip()[:100]}")
                
                # Bu elementin bulunduğu article veya div'i bul
                container = parent
                while container and container.name not in ['article', 'div', 'body', 'html']:
                    container = container.parent
                
                if container and container.name in ['article', 'div']:
                    self.stdout.write(f"    Konteyner: Tag={container.name}, Sınıf={container.get('class', ['Sınıf yok'])}")
                    
                    # Konteyner içindeki linkleri bul
                    container_links = container.find_all('a', href=True)
                    if container_links:
                        self.stdout.write(f"    Konteyner içindeki linkler:")
                        for link in container_links[:3]:
                            self.stdout.write(f"      {link['href']}")
            
            # 6. Kategori bilgilerini ara
            self.stdout.write("\n--- KATEGORİ BİLGİLERİNİ ANALİZ ET ---")
            
            # a) Kategori etiketleri (tag) için arama yap
            category_links = soup.find_all('a', class_=re.compile('cat|category|tag'))
            self.stdout.write(f"Kategori linki olabilecek eleman sayısı: {len(category_links)}")
            for i, link in enumerate(category_links[:10]):
                self.stdout.write(f"  Kategori link {i+1}: URL={link['href']}")
                self.stdout.write(f"    Metin: {link.text.strip()}")
                self.stdout.write(f"    Sınıf: {link.get('class', ['Sınıf yok'])}")
            
            # b) Haber detay sayfası için kategori analizi
            if "/category/" not in url and len(url) > 30:  # Detay sayfası olabilir
                self.stdout.write("\n--- HABER DETAY SAYFASI KATEGORİ ANALİZİ ---")
                
                # Kaynak bilgisi ve yanındaki kategori formatı
                kaynak_bilgisi = soup.find(string=re.compile('Kaynak:.*TEKHA'))
                if kaynak_bilgisi:
                    self.stdout.write(f"Kaynak bilgisi bulundu: {kaynak_bilgisi.strip()}")
                    parent_elem = kaynak_bilgisi.parent
                    
                    # Ebeveyn elementi bul
                    while parent_elem and parent_elem.name != 'div' and parent_elem.name != 'section':
                        parent_elem = parent_elem.parent
                    
                    if parent_elem:
                        self.stdout.write(f"Kaynak bilgisi konteyner: Tag={parent_elem.name}, Sınıf={parent_elem.get('class', ['Sınıf yok'])}")
                        
                        # "|" işareti içeren içeriği ara
                        pipe_content = None
                        for text in parent_elem.stripped_strings:
                            if "|" in text and "Kaynak:" not in text:
                                pipe_content = text.strip()
                                break
                        
                        if pipe_content:
                            self.stdout.write(f"Kategori bilgisi içeren metin bulundu: {pipe_content}")
                            # "Gaziantep | Gündem" şeklindeki metni işle
                            kategori_parcalari = [k.strip() for k in pipe_content.split('|')]
                            if len(kategori_parcalari) > 0:
                                self.stdout.write(f"Çıkarılan kategori parçaları: {kategori_parcalari}")
                else:
                    self.stdout.write("Kaynak bilgisi bulunamadı")
                
                # Meta bilgilerinde kategori ara
                category_meta = soup.find('meta', property='article:section')
                if category_meta:
                    self.stdout.write(f"Meta kategori bilgisi: {category_meta.get('content', 'Boş')}")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Hata: {str(e)}")) 