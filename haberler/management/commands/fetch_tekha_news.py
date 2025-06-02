import os
import re
import requests
import logging
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.files.base import ContentFile
from django.contrib.auth.models import User
from django.utils.text import slugify
from haberler.models import Haber, Kategori, HaberKaynagi
from django.conf import settings
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'TEKHA sitesinden tüm kategorileri tarayarak Abdullah Solmaz haberlerini çeker'

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

    def clean_html_content(self, content_element, remove_author=False):
        """
        HTML içeriğini temizler ve haber için uygun formata getirir
        İstenmeyen etiketleri, reklamları ve gereksiz öğeleri kaldırır
        remove_author=True ise içerikten Abdullah Solmaz ve imza satırını kaldırır
        """
        # Kopya üzerinde çalışalım, orijinali değiştirmeyelim
        if isinstance(content_element, str):
            cleaned_element = BeautifulSoup(content_element, 'html.parser')
        else:
            cleaned_element = BeautifulSoup(str(content_element), 'html.parser')
        
        # Yazar pattern'larını başta tanımla - tüm fonksiyon boyunca kullanılabilecek
        author_patterns = [
            re.compile(r'ABDULLAH\s+SOLMAZ[-\s/]*GAZİANTEP/?TEKHA', re.IGNORECASE),  # Abdullah Solmaz
            re.compile(r'Birol\s+Güngördü\s*/?\s*Çanakkale\s*[-/]?\s*TEKHA', re.IGNORECASE),  # Birol Güngördü
            re.compile(r'Burak\s+Birol\s*[/-]?\s*[^/\n]*\s*[-/]?\s*TEKHA', re.IGNORECASE),  # Burak Birol
            re.compile(r'Burak\s+BİROL\s*[–\-/]?\s*BURSA\s*[–\-/]?\s*TEKHA', re.IGNORECASE),  # Burak BİROL BURSA formatı
            re.compile(r'BURAK\s+BİROL\s*[–\-/]?\s*BURSA\s*[–\-/]?\s*TEKHA', re.IGNORECASE),  # BURAK BİROL BURSA formatı
            re.compile(r'Hüseyin\s+Polattimur\s*[/-]?\s*Kocaeli\s*[-/]?\s*TEKHA', re.IGNORECASE),  # Hüseyin Polattimur
            
            # Hüseyin Zorkun için genişletilmiş desenler
            re.compile(r'Hüseyin\s+[zZ]orkun\s*[/-]?\s*[hH]atay\s*[-/]?\s*[tT][eE][kK][hH][aA]', re.IGNORECASE),  # Normal yazım
            re.compile(r'HÜSEYIN\s+ZORKUN\s*[/-]?\s*HATAY\s*[-/]?\s*TEKHA', re.IGNORECASE),  # Tamamen büyük harf
            re.compile(r'Hᴜ̈SᴇYİN\s+Zᴏʀᴋᴜɴ\s*[/\s-]*\s*HATAY\s*[-–/]?\s*TEKHA', re.IGNORECASE),  # Özel karakter formatı
            re.compile(r'H[ᴜüÜ][^\s]*S[ᴇeE][^\s]*Y[İiI][^\s]*N\s+Z[ᴏoO]R[ᴋkK][ᴜuU][ɴnN]\s*[/\s-]*\s*HATAY\s*[-–/]?\s*TEKHA', re.IGNORECASE),  # Unicode ve karışık karakterler
            re.compile(r'HUSEYIN\s+ZORKUN\s*[/\s-]*\s*HATAY\s*[-–/]?\s*TEKHA', re.IGNORECASE),  # Türkçe karakter olmadan
            
            # Genel yazar ve kaynak desenleri
            re.compile(r'[A-Z][a-z]+\s+[A-Z][a-zÇçĞğİıÖöŞşÜü]+-[A-Z]+/TEKHA', re.IGNORECASE),  # Ad Soyad-ŞEHİR/TEKHA
            re.compile(r'[A-Z][a-z]+\s+[A-Z][a-zÇçĞğİıÖöŞşÜü]+/[A-Z]+', re.IGNORECASE),  # Ad Soyad/ŞEHİR
            re.compile(r'[A-Z][a-z]+\s+[A-Z][a-zÇçĞğİıÖöŞşÜü]+[-/][A-Z]+', re.IGNORECASE),  # Ad Soyad-ŞEHİR veya Ad Soyad/ŞEHİR
            re.compile(r'[A-Z][a-z]+\s+[A-Z][a-zÇçĞğİıÖöŞşÜü]+\s+[A-Z]+', re.IGNORECASE),  # Ad Soyad ŞEHİR
            re.compile(r'Haber[:\s]+[A-Z][a-z]+\s+[A-Z][a-zÇçĞğİıÖöŞşÜü]+', re.IGNORECASE),  # Haber: Ad Soyad
            re.compile(r'Kaynak[:\s]+TEKHA', re.IGNORECASE),  # Kaynak: TEKHA
            re.compile(r'TEKHA\s+HABER\s+AJANSI', re.IGNORECASE),  # TEKHA HABER AJANSI
            re.compile(r'[A-Z][A-ZÇĞİÖŞÜ]+\s+[A-Z][A-ZÇĞİÖŞÜ]+-[A-Z]+/[A-Z]+', re.IGNORECASE),  # BÜYÜK AD SOYAD-ŞEHİR/AJANS
            re.compile(r'[A-Z][a-zÇçĞğİıÖöŞşÜü]+\s+[A-Z][a-zÇçĞğİıÖöŞşÜü]+\s*[-/]?\s*TEKHA', re.IGNORECASE),  # Herhangi bir Yazar TEKHA
        ]
        
        # Abdullah Solmaz ve diğer yazarlara özel patternlar
        abdullah_solmaz_patterns = [
            re.compile(r'ABDULLAH\s+SOLMAZ[-\s]*GAZİANTEP/TEKHA', re.IGNORECASE),  # Tam imza formatı
            re.compile(r'ABDULLAH\s+SOLMAZ', re.IGNORECASE),  # Sadece isim  
        ]
        
        # Hüseyin Zorkun özel patternları
        huseyin_zorkun_patterns = [
            re.compile(r'Hüseyin\s+[zZ]orkun\s*[/-]?\s*[hH]atay\s*[-/]?\s*[tT][eE][kK][hH][aA]', re.IGNORECASE),  # Normal yazım
            re.compile(r'HÜSEYIN\s+ZORKUN\s*[/-]?\s*HATAY\s*[-/]?\s*TEKHA', re.IGNORECASE),  # Tamamen büyük harf
            re.compile(r'Hᴜ̈SᴇYİN\s+Zᴏʀᴋᴜɴ\s*[/\s-]*\s*HATAY\s*[-–/]?\s*TEKHA', re.IGNORECASE),  # Özel karakter formatı
            re.compile(r'H[ᴜüÜ][^\s]*S[ᴇeE][^\s]*Y[İiI][^\s]*N\s+Z[ᴏoO]R[ᴋkK][ᴜuU][ɴnN]\s*[/\s-]*\s*HATAY\s*[-–/]?\s*TEKHA', re.IGNORECASE),  # Unicode ve karışık karakterler
            re.compile(r'HUSEYIN\s+ZORKUN\s*[/\s-]*\s*HATAY\s*[-–/]?\s*TEKHA', re.IGNORECASE),  # Türkçe karakter olmadan
            re.compile(r'Hüseyin\s+Zorkun', re.IGNORECASE),  # Sadece isim
            re.compile(r'HÜSEYIN\s+ZORKUN', re.IGNORECASE),  # Sadece isim büyük harfle
            re.compile(r'Hᴜ̈SᴇYİN\s+Zᴏʀᴋᴜɴ', re.IGNORECASE),  # Sadece isim özel karakterle
        ]
        
        # Burak Birol özel patternları
        burak_birol_patterns = [
            re.compile(r'Burak\s+Birol\s*[/-]?\s*[^/\n]*\s*[-/]?\s*TEKHA', re.IGNORECASE),  # Normal yazım
            re.compile(r'BURAK\s+BIROL\s*[/-]?\s*[^/\n]*\s*[-/]?\s*TEKHA', re.IGNORECASE),  # Tamamen büyük harf
            re.compile(r'Burak\s+BİROL\s*[–\-/]?\s*BURSA\s*[–\-/]?\s*TEKHA', re.IGNORECASE),  # Türkçe karakter formatı
            re.compile(r'BURAK\s+BİROL\s*[–\-/]?\s*BURSA\s*[–\-/]?\s*TEKHA', re.IGNORECASE),  # Tamamen büyük harf Türkçe
            re.compile(r'Burak\s+BİROL\s*–\s*BURSA\s*/\s*TEKHA', re.IGNORECASE),  # Tam format eşleşmesi
            re.compile(r'BURAK\s+BİROL\s*–\s*BURSA\s*/\s*TEKHA', re.IGNORECASE),  # Tam format büyük harf
            re.compile(r'Burak\s+B[İiI]ROL\s*[–\-/]?\s*[A-ZÇĞİÖŞÜa-zçğıöşü]+\s*[–\-/]?\s*TEKHA', re.IGNORECASE),  # Esnek karakter eşleşmesi
            re.compile(r'BURAK\s+B[İiI]ROL\s*[–\-/]?\s*[A-ZÇĞİÖŞÜa-zçğıöşü]+\s*[–\-/]?\s*TEKHA', re.IGNORECASE),  # Esnek büyük harf
            re.compile(r'Burak\s+Birol', re.IGNORECASE),  # Sadece isim
            re.compile(r'Burak\s+BİROL', re.IGNORECASE),  # Sadece isim Türkçe karakter
            re.compile(r'BURAK\s+BİROL', re.IGNORECASE),  # Sadece isim büyük harf Türkçe
        ]
        
        # Hüseyin Polattimur özel patternları
        huseyin_polattimur_patterns = [
            re.compile(r'Hüseyin\s+Polattimur\s*[/-]?\s*Kocaeli\s*[-/]?\s*TEKHA', re.IGNORECASE),  # Normal yazım
            re.compile(r'HÜSEYIN\s+POLATTIMUR\s*[/-]?\s*KOCAELI\s*[-/]?\s*TEKHA', re.IGNORECASE),  # Tamamen büyük harf
            re.compile(r'Hüseyin\s+Polattimur', re.IGNORECASE),  # Sadece isim
            re.compile(r'HÜSEYIN\s+POLATTIMUR', re.IGNORECASE),  # Sadece isim büyük harfle
        ]
        
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
            
        # Belirli ID'lere sahip gereksiz içerikleri temizle
        id_pattern = re.compile(r'comment|sidebar|widget|ad|banner|related')
        for div_id in cleaned_element.find_all(id=lambda i: i and id_pattern.search(i)):
            div_id.decompose()
        
        # Belirli metinleri içeren h3 başlıklarını ve sonrasını temizle
        for h3 in cleaned_element.find_all('h3'):
            h3_text = h3.get_text().lower()
            if 'ilginizi çekebilir' in h3_text or 'diğer haberler' in h3_text or 'yorumlar' in h3_text:
                # Bu başlıktan sonraki tüm kardeş etiketleri sil
                current = h3.next_sibling
                while current:
                    next_element = current.next_sibling
                    current.decompose()
                    current = next_element
                # Başlığın kendisini de sil
                h3.decompose()
        
        # <i> etiketini <em> etiketine çevir
        for i_tag in cleaned_element.find_all('i'):
            i_tag.name = 'em'
        
        # <b> etiketini <strong> etiketine çevir
        for b_tag in cleaned_element.find_all('b'):
            b_tag.name = 'strong'
        
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
        
        # Yazar bilgilerini temizle
        if remove_author:
            # 0. YENİ: Başlık ve alt başlıklarda yazar bilgisi kontrolü - haber başlıklarında yazar bilgisi olabilir
            for header in cleaned_element.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                if header.text:
                    header_text = header.text.strip()
                    
                    # Sadece yazar bilgisi içeren başlıkları temizle
                    yazar_bulundu_baslik = False
                    
                    # Tüm yazar desenleri için kontrol et
                    for pattern in (
                        abdullah_solmaz_patterns + 
                        huseyin_zorkun_patterns + 
                        burak_birol_patterns + 
                        huseyin_polattimur_patterns + 
                        author_patterns
                    ):
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
            
            # 1. İlk olarak strong etiketlerinde ara - yazarlar genelde strong içinde olur
            for strong in cleaned_element.find_all('strong'):
                if strong.text and len(strong.text.strip()) < 50:  # Uzun strong içerikleri atla, bunlar başlık olabilir
                    # Strong içindeki metin tam bir satırsa - muhtemelen yazar bilgisidir
                    strong_text = strong.text.strip()
                    
                    # Abdullah Solmaz özel kontrolü
                    for pattern in abdullah_solmaz_patterns:
                        if pattern.search(strong_text):
                            strong.decompose()
                            break
                    else:  # Abdullah Solmaz değilse Hüseyin Zorkun'u kontrol et
                        for pattern in huseyin_zorkun_patterns:
                            if pattern.search(strong_text):
                                strong.decompose()
                                break
                        else:  # Hüseyin Zorkun da değilse Burak Birol'u kontrol et
                            for pattern in burak_birol_patterns:
                                if pattern.search(strong_text):
                                    strong.decompose()
                                    break
                            else:  # Burak Birol da değilse Hüseyin Polattimur'u kontrol et
                                for pattern in huseyin_polattimur_patterns:
                                    if pattern.search(strong_text):
                                        strong.decompose()
                                        break
            
            # 2. Text düğümlerini kontrol et - tüm yazarlar için özel olarak
            # Abdullah Solmaz için
            for pattern in abdullah_solmaz_patterns:
                for text in cleaned_element.find_all(string=pattern):
                    # İmza satırını boş string ile değiştir
                    text.replace_with('')
            
            # Hüseyin Zorkun için
            for pattern in huseyin_zorkun_patterns:
                for text in cleaned_element.find_all(string=pattern):
                    # İmza satırını boş string ile değiştir
                    text.replace_with('')
                    
            # Burak Birol için
            for pattern in burak_birol_patterns:
                for text in cleaned_element.find_all(string=pattern):
                    # İmza satırını boş string ile değiştir
                    text.replace_with('')
                    
            # Hüseyin Polattimur için
            for pattern in huseyin_polattimur_patterns:
                for text in cleaned_element.find_all(string=pattern):
                    # İmza satırını boş string ile değiştir
                    text.replace_with('')
            
            # 3. YENİ: İlk paragrafta yazar bilgisini kontrol et - haber içeriğinin ilk bölümünde yazar bilgisi olabilir
            # Özellikle haberin ilk p etiketinde veya ilk satırlarında yazar bilgisi olabilir
            first_elements = []
            
            # İlk p etiketini bul
            first_p = cleaned_element.find('p')
            if first_p:
                first_elements.append(first_p)
            
            # div veya başka bir konteynerdeki ilk metin düğümünü kontrol et
            for container in cleaned_element.find_all(['div', 'section', 'article']):
                text_nodes = list(container.find_all(string=True, recursive=False))
                if text_nodes:
                    for text_node in text_nodes[:2]:  # İlk iki metin düğümünü kontrol et
                        if text_node.strip():
                            # BeautifulSoup string nesneleri parent elementlerine erişebilir
                            parent_element = text_node.parent
                            if parent_element and parent_element not in first_elements:
                                first_elements.append(parent_element)
            
            # İlk elementleri kontrol et
            for element in first_elements:
                element_text = element.get_text().strip()
                
                # Kısa bir paragraf mı?
                if len(element_text) < 150:  # 150 karakterden kısa paragraflar
                    
                    # Bütün yazar desenleri için kontrol et
                    yazar_bulundu = False
                    
                    # Abdullah Solmaz
                    for pattern in abdullah_solmaz_patterns:
                        if pattern.search(element_text):
                            # Eğer paragraf sadece yazar bilgisi içeriyorsa komple sil
                            if len(element_text.split()) <= 15:
                                element.decompose()
                            else:
                                # Paragrafta başka içerik de varsa sadece yazarı kaldır
                                cleaned_text = pattern.sub('', element_text)
                                cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
                                if cleaned_text:
                                    element.string = cleaned_text
                                else:
                                    element.decompose()
                            yazar_bulundu = True
                            break
                    
                    # Hüseyin Zorkun
                    if not yazar_bulundu:
                        for pattern in huseyin_zorkun_patterns:
                            if pattern.search(element_text):
                                # Eğer paragraf sadece yazar bilgisi içeriyorsa komple sil
                                if len(element_text.split()) <= 15:
                                    element.decompose()
                                else:
                                    # Paragrafta başka içerik de varsa sadece yazarı kaldır
                                    cleaned_text = pattern.sub('', element_text)
                                    cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
                                    if cleaned_text:
                                        element.string = cleaned_text
                                    else:
                                        element.decompose()
                                yazar_bulundu = True
                                break
                    
                    # Burak Birol
                    if not yazar_bulundu:
                        for pattern in burak_birol_patterns:
                            if pattern.search(element_text):
                                # Eğer paragraf sadece yazar bilgisi içeriyorsa komple sil
                                if len(element_text.split()) <= 15:
                                    element.decompose()
                                else:
                                    # Paragrafta başka içerik de varsa sadece yazarı kaldır
                                    cleaned_text = pattern.sub('', element_text)
                                    cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
                                    if cleaned_text:
                                        element.string = cleaned_text
                                    else:
                                        element.decompose()
                                yazar_bulundu = True
                                break
                    
                    # Hüseyin Polattimur
                    if not yazar_bulundu:
                        for pattern in huseyin_polattimur_patterns:
                            if pattern.search(element_text):
                                # Eğer paragraf sadece yazar bilgisi içeriyorsa komple sil
                                if len(element_text.split()) <= 15:
                                    element.decompose()
                                else:
                                    # Paragrafta başka içerik de varsa sadece yazarı kaldır
                                    cleaned_text = pattern.sub('', element_text)
                                    cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
                                    if cleaned_text:
                                        element.string = cleaned_text
                                    else:
                                        element.decompose()
                                yazar_bulundu = True
                                break
                    
                    # Genel yazarlar
                    if not yazar_bulundu:
                        for pattern in author_patterns:
                            if pattern.search(element_text):
                                # Eğer paragraf sadece yazar bilgisi içeriyorsa komple sil
                                if len(element_text.split()) <= 15:
                                    element.decompose()
                                else:
                                    # Paragrafta başka içerik de varsa sadece yazarı kaldır
                                    cleaned_text = pattern.sub('', element_text)
                                    cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
                                    if cleaned_text:
                                        element.string = cleaned_text
                                    else:
                                        element.decompose()
                                break
            
            # 4. YENİ: Haber içeriğindeki ilk metni özel olarak kontrol et - bazı yazar bilgileri metin düğümlerinde olabilir
            all_text_nodes = cleaned_element.find_all(string=lambda text: text and text.strip())
            if all_text_nodes:
                for text_node in all_text_nodes[:5]:  # İlk 5 metin düğümünü kontrol et
                    if not text_node.parent.name in ['script', 'style', 'meta', 'link']:
                        text_content = text_node.strip()
                        if text_content:
                            # TEKHA formatı mı?
                            tekha_format = False
                            
                            # Tüm yazar desenleri için kontrol
                            for pattern in (
                                abdullah_solmaz_patterns + 
                                huseyin_zorkun_patterns + 
                                burak_birol_patterns + 
                                huseyin_polattimur_patterns + 
                                author_patterns
                            ):
                                if pattern.search(text_content):
                                    # Eğer metin kısa ve sadece yazar bilgisi içeriyorsa
                                    if len(text_content.split()) <= 10 and ('/' in text_content or '-' in text_content):
                                        text_node.replace_with('')
                                        tekha_format = True
                                        break
                                    # Uzun bir metin ama başında yazar bilgisi varsa
                                    elif pattern.search(text_content[:50]):
                                        cleaned_text = pattern.sub('', text_content)
                                        cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
                                        if cleaned_text:
                                            text_node.replace_with(cleaned_text)
                                        else:
                                            text_node.replace_with('')
                                        tekha_format = True
                                        break
                            
                            if tekha_format:
                                break
            
            # 5. Tüm paragrafları kontrol et
            for p in cleaned_element.find_all('p'):
                if p.text and len(p.text.strip()) < 100:  # Kısa paragraflar
                    p_text = p.text.strip()
                    
                    # a) Abdullah Solmaz için özel kontrol
                    for pattern in abdullah_solmaz_patterns:
                        if pattern.search(p_text):
                            if len(p_text.split()) <= 5:  # Kısa bir paragrafsa, muhtemelen sadece imza
                                p.decompose()
                                break
                            else:
                                # Paragrafta başka içerik de varsa sadece yazarı kaldır
                                p_text = pattern.sub('', p_text)
                                p_text = re.sub(r'\s+', ' ', p_text).strip()
                                if p_text:
                                    p.string = p_text
                                else:
                                    p.decompose()
                                break
                    
                    # a2) Hüseyin Zorkun için özel kontrol
                    for pattern in huseyin_zorkun_patterns:
                        if pattern.search(p_text):
                            if len(p_text.split()) <= 5:  # Kısa bir paragrafsa, muhtemelen sadece imza
                                p.decompose()
                                break
                            else:
                                # Paragrafta başka içerik de varsa sadece yazarı kaldır
                                p_text = pattern.sub('', p_text)
                                p_text = re.sub(r'\s+', ' ', p_text).strip()
                                if p_text:
                                    p.string = p_text
                                else:
                                    p.decompose()
                                break
                                
                    # a3) Burak Birol için özel kontrol
                    for pattern in burak_birol_patterns:
                        if pattern.search(p_text):
                            if len(p_text.split()) <= 5:  # Kısa bir paragrafsa, muhtemelen sadece imza
                                p.decompose()
                                break
                            else:
                                # Paragrafta başka içerik de varsa sadece yazarı kaldır
                                p_text = pattern.sub('', p_text)
                                p_text = re.sub(r'\s+', ' ', p_text).strip()
                                if p_text:
                                    p.string = p_text
                                else:
                                    p.decompose()
                                break
                                
                    # a4) Hüseyin Polattimur için özel kontrol
                    for pattern in huseyin_polattimur_patterns:
                        if pattern.search(p_text):
                            if len(p_text.split()) <= 5:  # Kısa bir paragrafsa, muhtemelen sadece imza
                                p.decompose()
                                break
                            else:
                                # Paragrafta başka içerik de varsa sadece yazarı kaldır
                                p_text = pattern.sub('', p_text)
                                p_text = re.sub(r'\s+', ' ', p_text).strip()
                                if p_text:
                                    p.string = p_text
                                else:
                                    p.decompose()
                                break
                    
                    # b) Kesin yazar bilgisi içeren paragraflar
                    for pattern in author_patterns:
                        if pattern.search(p_text):
                            p.decompose()
                            break
                    
                    # c) Diğer yazar bilgileri - yalnızca kısa paragraflar ve özel formatlarda
                    # Yazar bilgisi genellikle tek satır olur
                    if len(p_text.split('\n')) <= 2 and len(p_text.split()) <= 10:
                        for pattern in author_patterns:
                            if pattern.search(p_text):
                                p.decompose()
                                break
            
            # 6. Son paragrafları özel olarak kontrol et (genellikle yazar imzası içerir)
            paragraphs = cleaned_element.find_all('p')
            if len(paragraphs) > 2:
                for p in paragraphs[-3:]:  # Son 3 paragrafı kontrol et
                    if p.text and len(p.text.strip()) < 100:  # Kısa paragraflar
                        p_text = p.text.strip()
                        
                        # Abdullah Solmaz kontrolü
                        for pattern in abdullah_solmaz_patterns:
                            if pattern.search(p_text):
                                p.decompose()
                                break
                        
                        # Hüseyin Zorkun kontrolü
                        for pattern in huseyin_zorkun_patterns:
                            if pattern.search(p_text):
                                p.decompose()
                                break
                                
                        # Burak Birol kontrolü
                        for pattern in burak_birol_patterns:
                            if pattern.search(p_text):
                                p.decompose()
                                break
                                
                        # Hüseyin Polattimur kontrolü
                        for pattern in huseyin_polattimur_patterns:
                            if pattern.search(p_text):
                                p.decompose()
                                break
                        
                        # İmza satırı genellikle kısa olur ve özel karakterler içerir
                        if ('TEKHA' in p_text or '/' in p_text or '-' in p_text) and len(p_text.split()) <= 10:
                            for pattern in author_patterns:
                                if pattern.search(p_text):
                                    p.decompose()
                                    break
        
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
        verbose = options.get('verbose', False)  # Eğer tanımlanmamışsa False kullan
        max_pages = options['max_pages']
        
        # Abdullah Solmaz için sabit değer
        yazar_adi = 'ABDULLAH SOLMAZ'

        # Kategori eşleştirme sözlüğü - tüm fonksiyon içinde kullanılabilecek
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
        
        # Geçersiz kategori listesi
        gecersiz_kategoriler = ['instagram', 'facebook', 'twitter', 'sosyal medya', 'uye giris', 'nobetci eczane']
        
        self.stdout.write(self.style.SUCCESS(f'TEKHA sitesinden Abdullah Solmaz haberlerini çekiliyor (limit: {limit})'))
        
        # Kaynak kontrol edilir veya oluşturulur
        kaynak, created = HaberKaynagi.objects.get_or_create(
            url='https://www.tekha.com.tr',
            defaults={
                'ad': 'Tek Haber Ajansı (TEKHA)',
                'aktif': True,
                'aranan_kelimeler': 'Abdullah Solmaz, Gaziantep, TEKHA',
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
        
        # Haberleri topla
        haber_linkleri = []
        
        try:
            # 1. Doğrudan ana sayfa 
            self.stdout.write(self.style.SUCCESS(f"Ana sayfa kontrol ediliyor"))
            
            response = requests.get('https://www.tekha.com.tr/')
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Tüm makale veya haber bağlantılarını bul
                for link in soup.find_all('a', href=True):
                    url = link['href']
                    # Kategori, etiket ve sayfa bağlantılarını atla
                    if url.startswith('https://www.tekha.com.tr') and not re.search(r'/(category|tag|page|etiket)/', url):
                        if url not in haber_linkleri:
                            haber_linkleri.append(url)
            
            # 2. Tüm kategori sayfalarını tara
            kategoriler = ['gundem', 'asayis', 'siyaset', 'ekonomi', 'spor', 'genel', 'meteoroloji', 'politika', 'dunya', 'egitim', 'yasam', 'kultur-sanat']
            
            for kategori in kategoriler:  # Tüm kategorileri tara
                # Her kategori için son 5 sayfayı kontrol et
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
                                if url.startswith('https://www.tekha.com.tr') and not re.search(r'/(category|tag|page|etiket)/', url):
                                    if url not in haber_linkleri:
                                        haber_linkleri.append(url)
                        elif response.status_code == 404:
                            # Bu kategori için daha fazla sayfa yok
                            self.stdout.write(f"{kategori} kategorisi için sayfa {page_num} bulunamadı, sonraki kategoriye geçiliyor")
                            break
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f'Kategori sayfası kontrol edilirken hata: {str(e)}'))
            
            # 3. Son içerikler için sayfa numaralarını tara
            for page_num in range(1, max_pages + 1):
                if page_num == 1:
                    page_url = "https://www.tekha.com.tr/"
                else:
                    page_url = f"https://www.tekha.com.tr/page/{page_num}/"
                
                self.stdout.write(f"Ana sayfa kontrol ediliyor: {page_url}")
                
                try:
                    response = requests.get(page_url, timeout=10)
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.content, 'html.parser')
                        
                        # Tüm haber linklerini bul
                        for link in soup.find_all('a', href=True):
                            url = link['href']
                            # Kategori, etiket ve sayfa bağlantılarını atla
                            if url.startswith('https://www.tekha.com.tr') and not re.search(r'/(category|tag|page|etiket)/', url):
                                if url not in haber_linkleri:
                                    haber_linkleri.append(url)
                    elif response.status_code == 404:
                        # Daha fazla sayfa yok
                        self.stdout.write(f"Sayfa {page_num} bulunamadı, tarama tamamlanıyor")
                        break
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'Ana sayfa kontrol edilirken hata: {str(e)}'))
            
            # 4. Gaziantep ile ilgili etiketler - Abdullah Solmaz haberleri için önemli
            gaziantep_etiketleri = [
                'gaziantep', 'gaziantep-haber', 'asayis-gaziantep', 
                'trafik-kazasi-gaziantep', 'gaziantep-emniyet', 
                'gaziantep-polis', 'gaziantep-adliye'
            ]
            
            for etiket in gaziantep_etiketleri:
                etiket_url = f"https://www.tekha.com.tr/etiket/{etiket}/"
                self.stdout.write(f"Etiket sayfası kontrol ediliyor: {etiket_url}")
                
                try:
                    response = requests.get(etiket_url, timeout=10)
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.content, 'html.parser')
                        
                        # Tüm haber linklerini bul
                        for link in soup.find_all('a', href=True):
                            url = link['href']
                            # Kategori, etiket ve sayfa bağlantılarını atla
                            if url.startswith('https://www.tekha.com.tr') and not re.search(r'/(category|tag|page|etiket)/', url):
                                if url not in haber_linkleri:
                                    haber_linkleri.append(url)
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'Etiket sayfası kontrol edilirken hata: {str(e)}'))
            
            self.stdout.write(self.style.SUCCESS(f'Toplam {len(haber_linkleri)} haber bağlantısı bulundu, Abdullah Solmaz içeriği kontrol ediliyor...'))
            
            # Bulunan bağlantıları kontrol et ve Abdullah Solmaz içeriği olanları filtrele
            found_urls = []
            haber_skorlari = {}  # URL -> skor eşlemesi
            
            # Gereksiz sayfaları filtrele
            filtered_urls = []
            for url in haber_linkleri:
                # Gereksiz sayfaları atla (yazarlar, üye giriş vb.)
                if re.search(r'/(yazarlar|uye-giris|nobetci-eczaneler|hava-durumu|namaz-vakitleri|puan-durumlari)/?$', url):
                    continue
                # Ana sayfayı atla
                if url == 'https://www.tekha.com.tr' or url == 'https://www.tekha.com.tr/':
                    continue
                # Geçerli haberleri ekle
                filtered_urls.append(url)
            
            haber_linkleri = filtered_urls
            
            for i, url in enumerate(haber_linkleri):
                if len(found_urls) >= limit:
                    break
                    
                # Zaten veritabanında varsa atla (force_update etkinleştirilmediyse)
                if not force_update and Haber.objects.filter(kaynak_url=url).exists():
                    continue
                
                try:
                    # Haber detayını kontrol et
                    self.stdout.write(f"Haber kontrol ediliyor ({i+1}/{len(haber_linkleri)}): {url}")
                    response = requests.get(url, timeout=10)
                    if response.status_code == 200:
                        news_soup = BeautifulSoup(response.content, 'html.parser')
                        
                        # Sayfanın tüm metninde Abdullah Solmaz adını ara
                        page_text = news_soup.get_text()
                        
                        # Abdullah Solmaz için skorlama sistemi
                        skor = 0
                        
                        # 1. URL içeriğinde "gaziantep" geçiyorsa +2 puan (Abdullah Solmaz genellikle Gaziantep'te haber yapıyor)
                        if 'gaziantep' in url.lower():
                            skor += 2
                        
                        # 2. Sayfada "ABDULLAH SOLMAZ-GAZİANTEP/TEKHA" formatı +10 puan (kesin eşleşme)
                        if re.search(r'ABDULLAH\s+SOLMAZ[-\s]*GAZİANTEP/TEKHA', page_text, re.IGNORECASE):
                            skor += 10
                        
                        # 3. Sayfada hem Abdullah hem Solmaz kelimeleri geçiyorsa +5 puan
                        if re.search('Abdullah', page_text, re.IGNORECASE) and re.search('Solmaz', page_text, re.IGNORECASE):
                            skor += 5
                        
                        # 4. Başlıkta "Abdullah" veya "Solmaz" geçiyorsa +3 puan
                        baslik = news_soup.find('h1')
                        if baslik and ('Abdullah' in baslik.text or 'Solmaz' in baslik.text):
                            skor += 3
                        
                        # 5. TEKHA'nın tipik yazar formatı: BÜYÜK HARF YAZAR ADI-ŞEHİR/TEKHA
                        yazar_formati = re.compile(r'ABDULLAH\s+SOLMAZ[-\s]*GAZİANTEP/TEKHA', re.IGNORECASE)
                        if news_soup.find(text=yazar_formati):
                            skor += 15
                            self.stdout.write(self.style.SUCCESS(f"TEKHA formatında kesin eşleşme bulundu: {url}"))
                        
                        # 6. <strong> etiketinde yazar adı kontrolü - TEKHA sitesinde genellikle bu formatta
                        strong_tags = news_soup.find_all('strong')
                        for tag in strong_tags:
                            if tag.text and 'ABDULLAH SOLMAZ' in tag.text.upper() and 'GAZİANTEP' in tag.text.upper():
                                skor += 15
                                self.stdout.write(self.style.SUCCESS(f"<strong> etiketinde yazar bilgisi bulundu: {url}"))
                        
                        # 7. Sayfada Kaynak: TEKHA yazısı yanında Abdullah Solmaz geçiyorsa
                        kaynak_text = news_soup.find(text=lambda t: t and 'Kaynak:' in t and 'TEKHA' in t)
                        if kaynak_text:
                            kaynak_parent = kaynak_text.parent
                            next_elements = list(kaynak_parent.next_siblings) + list(kaynak_parent.parent.next_siblings)
                            for elem in next_elements[:5]:  # Sadece yakın kardeş elementlerde ara
                                if hasattr(elem, 'text') and 'ABDULLAH SOLMAZ' in elem.text.upper():
                                    skor += 10
                                    self.stdout.write(self.style.SUCCESS(f"Kaynak: TEKHA yanında yazar bilgisi bulundu: {url}"))
                        
                        # 8. Tipik Giriş: DD-MM-YYYY formatı yanında yazar bilgisi
                        giris_text = news_soup.find(text=re.compile(r'Giriş:\s*\d{2}-\d{2}-\d{4}'))
                        if giris_text:
                            giris_parent = giris_text.parent
                            next_elements = list(giris_parent.next_siblings) + list(giris_parent.parent.next_siblings)
                            for elem in next_elements[:5]:
                                if hasattr(elem, 'text') and 'ABDULLAH SOLMAZ' in elem.text.upper():
                                    skor += 10
                                    self.stdout.write(self.style.SUCCESS(f"Giriş tarihi yanında yazar bilgisi bulundu: {url}"))
                        
                        # 9. Paragraf içeriğinde Abdullah Solmaz ifadesi geçiyorsa
                        for paragraph in news_soup.find_all(['p', 'div', 'span']):
                            if paragraph.text and ('ABDULLAH' in paragraph.text.upper() and 'SOLMAZ' in paragraph.text.upper()):
                                skor += 3
                                self.stdout.write(self.style.SUCCESS(f"Paragraf içeriğinde yazar bilgisi bulundu: {url}"))
                                break
                        
                        # Skoru kaydet (minimum skor eşiğini geçerse)
                        if skor >= 5:  # En az 5 puan alan haberleri potansiyel olarak değerlendir
                            haber_skorlari[url] = skor
                            self.stdout.write(self.style.SUCCESS(f"Potansiyel Abdullah Solmaz haberi bulundu: {url}, Skor: {skor}"))
                        
                        # Yüksek skorlu haberleri doğrudan ekle (kesin eşleşmeler)
                        if skor >= 15 and url not in found_urls:
                            found_urls.append(url)
                            self.stdout.write(self.style.SUCCESS(f"Yüksek skorlu kesin eşleşme bulundu: {url}, Skor: {skor}"))
                        
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'Haber kontrol edilirken hata: {str(e)}'))
            
            # Skor tabanlı seçim - found_urls'e eklemek için
            if haber_skorlari:
                # Skorlarına göre haberleri sırala (en yüksek puanlı haberler önce)
                sirali_urls = sorted(haber_skorlari.keys(), key=lambda u: haber_skorlari[u], reverse=True)
                
                # En yüksek skorlu haberleri ekle (skor 10 ve üzeri olanlar)
                for url in sirali_urls:
                    if haber_skorlari[url] >= 10 and url not in found_urls and len(found_urls) < limit:
                        found_urls.append(url)
                        self.stdout.write(self.style.SUCCESS(f"Skorlama ile seçilen yüksek puanlı haber: {url}, Skor: {haber_skorlari[url]}"))
                
                # Orta skorlu haberleri ekle (skor 5-9 arası)
                for url in sirali_urls:
                    if 5 <= haber_skorlari[url] < 10 and url not in found_urls and len(found_urls) < limit:
                        found_urls.append(url)
                        self.stdout.write(self.style.SUCCESS(f"Skorlama ile seçilen orta puanlı haber: {url}, Skor: {haber_skorlari[url]}"))
            
            if not found_urls:
                self.stdout.write(self.style.WARNING(f'Abdullah Solmaz tarafından yazılmış haber bulunamadı.'))
                kaynak.son_kontrol = timezone.now()
                kaynak.save()
                return
            
            self.stdout.write(self.style.SUCCESS(f'Toplam {len(found_urls)} adet Abdullah Solmaz haberi bulundu.'))
            
            # Test modundaysa haberleri kaydetme
            if test_mode:
                self.stdout.write(self.style.WARNING('Test modu - Haberler kaydedilmedi.'))
                for url in found_urls:
                    self.stdout.write(f'  - {url}')
                return

            # Veritabanında olmayan haberleri kaydedelim
            for url in found_urls:
                # Zaten veritabanında varsa atla (force_update etkinleştirilmediyse)
                if not force_update and Haber.objects.filter(kaynak_url=url).exists():
                    continue
                found_urls.append(url)
                if len(found_urls) >= limit:
                    break
            
            if not found_urls:
                self.stdout.write(self.style.WARNING('İşlenecek yeni haber bulunamadı.'))
                kaynak.son_kontrol = timezone.now()
                kaynak.save()
                return

            self.stdout.write(self.style.SUCCESS(f'Toplam {len(found_urls)} adet yeni haber bulundu ve işlenecek.'))
            
            # Haberleri veritabanına kaydet
            for i, news_url in enumerate(found_urls, 1):
                try:
                    self.stdout.write(f'{i}/{len(found_urls)} - Haber çekiliyor: {news_url}')
                    
                    # URL'ye göre haberi güncelle veya yeni oluştur
                    existing_haber = None
                    if force_update:
                        existing_haber = Haber.objects.filter(kaynak_url=news_url).first()
                    
                    # Haber detayını çek
                    news_response = requests.get(news_url)
                    news_response.raise_for_status()
                    news_soup = BeautifulSoup(news_response.content, 'html.parser')
                    
                    # Başlık çek
                    title_element = news_soup.find('h1') or news_soup.find('h2')
                    if not title_element:
                        self.stdout.write(self.style.ERROR(f'Başlık bulunamadı: {news_url}'))
                        continue
                    
                    baslik = title_element.text.strip()
                    
                    # Yayın tarihini bul
                    yayin_tarihi = timezone.now()  # varsayılan değer - şu anki zaman
                    
                    try:
                        # TEKHA sitesinde yayın tarihi genellikle meta taglerinde olur
                        published_meta = news_soup.find('meta', property='article:published_time')
                        modified_meta = news_soup.find('meta', property='article:modified_time')
                        
                        if published_meta and published_meta.get('content'):
                            try:
                                yayin_tarihi = timezone.datetime.fromisoformat(published_meta.get('content').replace('Z', '+00:00'))
                                self.stdout.write(self.style.SUCCESS(f"Meta tag'den yayın tarihi bulundu: {yayin_tarihi}"))
                            except ValueError:
                                self.stdout.write(self.style.WARNING(f"Meta tag'den tarih çıkarılamadı: {published_meta.get('content')}"))
                        
                        # TEKHA sitesinde "Giriş: 13-04-2025 10:50" formatında tarih alanını ara
                        tarih_bulundu = False
                        if yayin_tarihi == timezone.now():
                            # 1. Önce tarih sınıfına sahip elementleri ara
                            date_elements = news_soup.find_all(class_=re.compile('entry-meta|entry-date|published|post-date'))
                            for date_element in date_elements:
                                if 'Giriş:' in date_element.text:
                                    self.stdout.write(self.style.SUCCESS(f"Tarih bilgisi elementte bulundu: {date_element.text.strip()}"))
                                    tarih_match = re.search(r'Giriş:\s*(\d{2})-(\d{2})-(\d{4})\s*(\d{2}):(\d{2})', date_element.text)
                                    if tarih_match:
                                        gun, ay, yil, saat, dakika = map(int, tarih_match.groups())
                                        try:
                                            yayin_tarihi = timezone.datetime(yil, ay, gun, saat, dakika, tzinfo=timezone.get_current_timezone())
                                            self.stdout.write(self.style.SUCCESS(f"Tarih bulundu (entry-meta): {yayin_tarihi}"))
                                            tarih_bulundu = True
                                            break
                                        except ValueError as e:
                                            self.stdout.write(self.style.WARNING(f"Geçersiz tarih değerleri: {e}"))
                            
                            # 2. Tüm metinde "Giriş: DD-MM-YYYY HH:MM" formatını ara (1. yöntem başarısız olursa)
                            if not tarih_bulundu:
                                full_text = news_soup.get_text()
                                tarih_match = re.search(r'Giriş:\s*(\d{2})-(\d{2})-(\d{4})\s*(\d{2}):(\d{2})', full_text)
                                
                                if tarih_match:
                                    gun, ay, yil, saat, dakika = map(int, tarih_match.groups())
                                    try:
                                        yayin_tarihi = timezone.datetime(yil, ay, gun, saat, dakika, tzinfo=timezone.get_current_timezone())
                                        self.stdout.write(self.style.SUCCESS(f"Tarih bulundu (tam metin): {yayin_tarihi}"))
                                    except ValueError as e:
                                        self.stdout.write(self.style.WARNING(f"Geçersiz tarih değerleri: {e}"))
                                else:
                                    # Alternatif tarih formatlarını kontrol et
                                    self.stdout.write(self.style.WARNING("'Giriş:' formatında tarih bulunamadı, alternatif formatları deniyorum..."))
                                    
                                    # Basit tarih formatı araması - Daha kapsamlı regex ile gün/ay/yıl formatlarını yakala
                                    # Çeşitli ayraçlar: / . - ve farklı format kombinasyonları
                                    date_pattern = re.compile(r'(\d{1,2})[\/\.\-](\d{1,2})[\/\.\-](\d{4})')
                                    
                                    # Yazı içerisinde tarih formatını da ara (örn: 5 Mayıs 2025)
                                    date_text_pattern = re.compile(r'(\d{1,2})\s+(Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)\s+(\d{4})', re.IGNORECASE)
                                    
                                    # Önce normal sayısal format kontrolü
                                    date_matches = list(date_pattern.finditer(full_text))
                                    
                                    if date_matches:
                                        # İlk eşleşmeyi al
                                        match = date_matches[0]
                                        gun, ay, yil = map(int, match.groups())
                                        try:
                                            yayin_tarihi = timezone.datetime(yil, ay, gun, tzinfo=timezone.get_current_timezone())
                                            self.stdout.write(self.style.SUCCESS(f"Alternatif tarih formatı bulundu: {yayin_tarihi}"))
                                        except ValueError:
                                            self.stdout.write(self.style.WARNING(f"Geçersiz alternatif tarih değerleri: {gun}/{ay}/{yil}"))
                                    else:
                                        # Yazı ile ay isimli format kontrolü
                                        text_matches = list(date_text_pattern.finditer(full_text))
                                        if text_matches:
                                            match = text_matches[0]
                                            gun = int(match.group(1))
                                            ay_ismi = match.group(2).lower()
                                            yil = int(match.group(3))
                                            
                                            # Ay isimlerini sayılara çevir
                                            ay_isimleri = {
                                                'ocak': 1, 'şubat': 2, 'mart': 3, 'nisan': 4, 'mayıs': 5, 'haziran': 6,
                                                'temmuz': 7, 'ağustos': 8, 'eylül': 9, 'ekim': 10, 'kasım': 11, 'aralık': 12
                                            }
                                            
                                            # Türkçe karakter duyarlılığı için normalize et
                                            ay_ismi = ay_ismi.replace('ş', 'ş').replace('ı', 'ı').replace('ö', 'ö').replace('ç', 'ç').replace('ğ', 'ğ').replace('ü', 'ü')
                                            
                                            if ay_ismi in ay_isimleri:
                                                ay = ay_isimleri[ay_ismi]
                                                try:
                                                    yayin_tarihi = timezone.datetime(yil, ay, gun, tzinfo=timezone.get_current_timezone())
                                                    self.stdout.write(self.style.SUCCESS(f"Yazı ile tarih formatı bulundu: {yayin_tarihi}"))
                                                except ValueError:
                                                    self.stdout.write(self.style.WARNING(f"Geçersiz yazı ile tarih değerleri: {gun}/{ay_ismi}/{yil}"))
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f'Tarih çekerken hata: {str(e)}'))
                        # Hata durumunda varsayılan tarihi kullan (şu anki zaman)
                    
                    # İçerik çek algoritması - TEKHA için özelleştirilmiş
                    content_html = ""
                    
                    # 1. Yazar içeren paragraf (post-excerpt sınıfında bulunuyor)
                    yazar_p = news_soup.find('p', string=re.compile(yazar_adi))
                    
                    # 2. İçerik paragraflari (entry-content sınıfında bulunuyor)
                    content_div = news_soup.find('div', class_='entry-content')
                    
                    # Abdullah Solmaz içeriklerde adını kaldıralım
                    remove_author = (yazar_adi and 'ABDULLAH SOLMAZ' == yazar_adi)
                    
                    if content_div:
                        self.stdout.write(self.style.SUCCESS(f"Haber içeriği bulundu (entry-content): {news_url}"))
                        # İstenmeyen içeriklerden arındırılmış temiz içerik elde etme
                        clean_content_div = self.clean_html_content(content_div, remove_author=remove_author)
                        content_html = str(clean_content_div)
                    else:
                        # Alternatif yöntem - tüm paragrafları kontrol et
                        paragraphs = news_soup.find_all('p')
                        
                        # Yazar paragrafını bul
                        yazar_index = -1
                        for i, p in enumerate(paragraphs):
                            if yazar_adi in p.text:
                                yazar_index = i
                                break
                        
                        # İçerik paragraflarını topla
                        if yazar_index >= 0:
                            # Yazar paragrafından sonraki tüm paragrafları içerik olarak al
                            content_paragraphs = []
                            for i in range(yazar_index + 1, len(paragraphs)):
                                # Yorum alanı paragraflarını atla
                                if paragraphs[i].parent.get('class') and 'comment' in str(paragraphs[i].parent.get('class')):
                                    continue
                                content_paragraphs.append(str(paragraphs[i]))
                            
                            if content_paragraphs:
                                temp_content = f"<div class='extracted-content'>{' '.join(content_paragraphs)}</div>"
                                # İçeriği temizle ve Abdullah Solmaz'ı kaldır
                                clean_temp = self.clean_html_content(temp_content, remove_author=remove_author)
                                content_html = str(clean_temp)
                                self.stdout.write(self.style.SUCCESS(f"Haber içeriği paragraflardan oluşturuldu: {news_url}"))
                        
                        # İçerik bulunamadıysa
                        if not content_html:
                            # Son çare: entry-content kelimesini içeren herhangi bir div
                            alt_content_divs = news_soup.find_all('div', class_=re.compile('content'))
                            for div in alt_content_divs:
                                if 'entry' in str(div.get('class', [])) and 'sideright' not in str(div.get('class', [])):
                                    clean_div = self.clean_html_content(div, remove_author=remove_author)
                                    content_html = str(clean_div)
                                    self.stdout.write(self.style.SUCCESS(f"Haber içeriği alternatif yöntemle bulundu: {news_url}"))
                                    break
                    
                    if not content_html:
                        self.stdout.write(self.style.ERROR(f'İçerik bulunamadı: {news_url}'))
                        continue
                    
                    # İçeriği BeautifulSoup nesnesi olarak işle
                    content_soup = BeautifulSoup(content_html, 'html.parser')
                    
                    # Özet çek (içeriğin ilk 300 karakteri)
                    text_content = content_soup.get_text(strip=True)
                    ozet = text_content[:300] + '...' if len(text_content) > 300 else text_content

                    # Temizlenmiş içeriği al
                    icerik = content_html
                    
                    # Resim URL'sini çek
                    resim_url = None
                    main_image = (news_soup.find('img', class_=re.compile('featured|main|post|thumbnail')) or 
                                news_soup.find('meta', property='og:image'))
                    
                    if main_image:
                        if main_image.name == 'img':
                            resim_url = main_image.get('src')
                        else:  # meta tag
                            resim_url = main_image.get('content')
                    
                    if not resim_url:
                        # Alternatif resim arama yöntemleri
                        images = content_soup.find_all('img')
                        if images:
                            # En büyük resmi bul (genellikle ana görsel olur)
                            largest_img = None
                            largest_size = 0
                            
                            for img in images:
                                # Boyut bilgisi varsa kullan
                                width = img.get('width')
                                height = img.get('height')
                                
                                if width and height:
                                    size = int(width) * int(height)
                                    if size > largest_size:
                                        largest_size = size
                                        largest_img = img
                                elif img.get('src'):
                                    if not largest_img:
                                        largest_img = img
                            
                            if largest_img:
                                resim_url = largest_img.get('src')
                    
                    if resim_url and not resim_url.startswith('http'):
                        resim_url = urljoin('https://www.tekha.com.tr', resim_url)
                    
                    # Kategori belirle
                    kategori = default_kategori
                    kategori_adi = None

                    # 1. Önce standart kategori arama yöntemini deneyelim
                    category_element = news_soup.find('a', class_=re.compile('category|tag|section')) or news_soup.find('span', class_=re.compile('category|tag|section'))
                    if category_element:
                        kategori_adi = category_element.text.strip()
                        self.stdout.write(self.style.SUCCESS(f"Standart kategori etiketi bulundu: {kategori_adi}"))
                        
                        # Instagram, Facebook gibi etiketleri kontrol et ve doğrudan atla
                        if kategori_adi.lower() in ['instagram', 'facebook', 'twitter', 'sosyal medya']:
                            kategori_adi = None
                            self.stdout.write(self.style.WARNING(f"Sosyal medya etiketi atlandı, alternatif kategori aranacak"))
                    else:
                        # 2. Sayfa yapısına özel kategori arama - resimde paylaştığınız görseldeki "Gaziantep | Gündem" formatı için
                        # Başlık altındaki Kaynak bilgisini içeren bölümün yanındaki kategori bilgisini arayalım
                        kaynak_bilgisi = news_soup.find(string=re.compile('Kaynak:.*TEKHA'))
                        if kaynak_bilgisi and hasattr(kaynak_bilgisi, 'parent'):
                            # Kaynak bilgisi elementi bulundu, şimdi aynı satırdaki kategori bilgilerini arayalım
                            parent_elem = kaynak_bilgisi.parent
                            while parent_elem and parent_elem.name != 'div' and parent_elem.name != 'section':
                                parent_elem = parent_elem.parent
                            
                            if parent_elem:
                                # Bu div'in içindeki veya sonrasındaki kategori bilgilerini içeren elementi bul
                                # Genellikle sağ tarafta olur ve "|" işareti içerir
                                kategori_text = None
                                
                                # Önce bu div içinde "|" içeren metni ara
                                for text in parent_elem.stripped_strings:
                                    if "|" in text and "Kaynak:" not in text:
                                        kategori_text = text.strip()
                                        break
                                
                                # Sonraki kardeş elementlerde de ara
                                if not kategori_text and parent_elem.next_sibling:
                                    sibling = parent_elem.next_sibling
                                    while sibling and not kategori_text:
                                        if hasattr(sibling, 'stripped_strings'):
                                            for text in sibling.stripped_strings:
                                                if "|" in text:
                                                    kategori_text = text.strip()
                                                    break
                                        sibling = sibling.next_sibling
                                
                                if kategori_text:
                                    self.stdout.write(self.style.SUCCESS(f"Özel format kategori bilgisi bulundu: {kategori_text}"))
                                    
                                    # "Gaziantep | Gündem" şeklindeki metni işle
                                    kategori_parcalari = [k.strip() for k in kategori_text.split('|')]
                                    if len(kategori_parcalari) > 0:
                                        # Son parçayı kategori olarak al, genelde "Gündem", "Spor" gibi ana kategoridir
                                        kategori_adi = kategori_parcalari[-1]
                                        self.stdout.write(self.style.SUCCESS(f"Çıkarılan kategori: {kategori_adi}"))
                        
                        # 3. Hiç bir kategoriye ulaşamadıysak URL'den tahminde bulunalım
                        if not kategori_adi:
                            # URL'yi kontrol et, kategori bilgisi URL'de olabilir
                            if 'category/' in news_url:
                                url_parts = news_url.split('category/')
                                if len(url_parts) > 1:
                                    url_category = url_parts[1].strip('/').split('/')[0]  # ilk kategori kısmını al
                                    if url_category:
                                        kategori_adi = url_category
                                        self.stdout.write(self.style.SUCCESS(f"URL'den kategori çıkarıldı: {kategori_adi}"))
                            elif 'gundem' in news_url.lower():
                                kategori_adi = 'Gündem'
                                self.stdout.write(self.style.SUCCESS(f"URL'den kategori tahmin edildi: {kategori_adi}"))
                            elif 'ekonomi' in news_url.lower():
                                kategori_adi = 'Ekonomi'
                                self.stdout.write(self.style.SUCCESS(f"URL'den kategori tahmin edildi: {kategori_adi}"))
                            elif 'spor' in news_url.lower():
                                kategori_adi = 'Spor'
                                self.stdout.write(self.style.SUCCESS(f"URL'den kategori tahmin edildi: {kategori_adi}"))
                            elif 'siyaset' in news_url.lower():
                                kategori_adi = 'Siyaset'
                                self.stdout.write(self.style.SUCCESS(f"URL'den kategori tahmin edildi: {kategori_adi}"))
                            elif 'asayis' in news_url.lower():
                                kategori_adi = 'Asayiş'
                                self.stdout.write(self.style.SUCCESS(f"URL'den kategori tahmin edildi: {kategori_adi}"))
                        
                        # Article class'larından kategori bilgisi çekme
                        article_classes = []
                        if hasattr(news_soup, 'article') and news_soup.article:
                            article_classes = news_soup.article.get('class', [])
                        
                        # Meta tag'lerden kategori bilgisi çekme
                        meta_category = news_soup.find('meta', property='article:section')
                        if meta_category and meta_category.get('content'):
                            meta_cat = meta_category.get('content').strip()
                            if not kategori_adi:  # Henüz kategori belirlenmemişse
                                kategori_adi = meta_cat
                                self.stdout.write(self.style.SUCCESS(f"Meta tagden kategori bulundu: {kategori_adi}"))
                        
                        # Eğer kategori hala Instagram/Facebook ise veya henüz belirlenmemişse başlığa ve URL'ye bak
                        if not kategori_adi or (kategori_adi and kategori_adi.lower() in gecersiz_kategoriler):
                            self.stdout.write(self.style.WARNING(f"Kategori belirlenmedi veya geçersiz kategori: {kategori_adi}"))
                            
                            # Önce URL'den kategori belirlemeyi dene
                            kategori_adi = None  # Kategori adını sıfırla
                            
                            # URL'de kategori bilgisi var mı?
                            if 'category/' in news_url:
                                url_parts = news_url.split('category/')
                                if len(url_parts) > 1:
                                    url_category = url_parts[1].strip('/').split('/')[0]  # ilk kategori kısmını al
                                    if url_category and url_category.lower() not in gecersiz_kategoriler:
                                        kategori_adi = url_category
                                        self.stdout.write(self.style.SUCCESS(f"URL'den kategori çıkarıldı: {kategori_adi}"))
                            
                            # URL'de farklı ipuçları var mı?
                            if not kategori_adi:
                                if 'gundem' in news_url.lower() or 'gündem' in news_url.lower():
                                    kategori_adi = 'Gündem'
                                elif 'ekonomi' in news_url.lower():
                                    kategori_adi = 'Ekonomi'
                                elif 'spor' in news_url.lower():
                                    kategori_adi = 'Spor'
                                elif 'siyaset' in news_url.lower():
                                    kategori_adi = 'Siyaset'
                                elif 'asayis' in news_url.lower() or 'asayiş' in news_url.lower():
                                    kategori_adi = 'Asayiş'
                                elif 'dunya' in news_url.lower() or 'dünya' in news_url.lower():
                                    kategori_adi = 'Dünya'
                            
                            if kategori_adi:
                                self.stdout.write(self.style.SUCCESS(f"URL içeriğinden kategori belirlendi: {kategori_adi}"))
                        
                            # Başlıktan kategori kestirmesi yap
                            if not kategori_adi:
                                baslik_lower = baslik.lower()
                                for key, value in kategori_eslesme.items():
                                    if key in baslik_lower:
                                        kategori_adi = value
                                        self.stdout.write(self.style.SUCCESS(f"Başlıktan kategori belirlendi: {kategori_adi}"))
                                        break
                            
                            # Hala bulunamadıysa içeriğe bak
                            if not kategori_adi and text_content:
                                for key, value in kategori_eslesme.items():
                                    if key in text_content[:300].lower():
                                        kategori_adi = value
                                        self.stdout.write(self.style.SUCCESS(f"İçerikten kategori belirlendi: {kategori_adi}"))
                                        break
                            
                            # Hiçbir kategori belirlenemezse Genel kullan
                            if not kategori_adi:
                                kategori_adi = "Genel"
                                self.stdout.write(self.style.WARNING(f"Kategori belirlenemedi, Genel kategorisi kullanılıyor"))

                    # Kategori adını veritabanı için uygun formata çevir ve oluştur
                    if kategori_adi:
                        # Kategori adı zaten kategori_eslesme'nin bir değeri mi?
                        if kategori_adi in kategori_eslesme.values():
                            # Doğrudan kullan
                            final_kategori = kategori_adi
                        else:
                            # Kategori adını küçük harfe çevir
                            kategori_adi_lower = kategori_adi.lower()
                            
                            # Birebir eşleşme kontrolü
                            final_kategori = None
                            for key, value in kategori_eslesme.items():
                                if key == kategori_adi_lower:
                                    final_kategori = value
                                    self.stdout.write(self.style.SUCCESS(f"Kategori eşleştirildi (birebir): {kategori_adi} -> {final_kategori}"))
                                    break
                            
                            # Birebir eşleşme yoksa içerir kontrolü
                            if not final_kategori:
                                for key, value in kategori_eslesme.items():
                                    if key in kategori_adi_lower:
                                        final_kategori = value
                                        self.stdout.write(self.style.SUCCESS(f"Kategori eşleştirildi (içerir): {kategori_adi} -> {final_kategori}"))
                                        break
                            
                            # Eşleşme yoksa Genel kategori kullan
                            if not final_kategori:
                                final_kategori = "Genel"
                                self.stdout.write(self.style.WARNING(f"Eşleşen kategori bulunamadı ({kategori_adi}), Genel kategorisine atanıyor"))
                        
                        # Veritabanında kategoriyi oluştur veya al
                        kategori, _ = Kategori.objects.get_or_create(ad=final_kategori)
                    else:
                        kategori, _ = Kategori.objects.get_or_create(ad="Genel")

                    # Instagram tarzı hashtag analizi - haber içeriğinde #tag formatında etiketler ara
                    hashtags = []
                    if content_html:
                        content_soup = BeautifulSoup(content_html, 'html.parser')
                        content_text = content_soup.get_text()
                        
                        # #tag formatındaki etiketleri bul
                        hashtag_pattern = re.compile(r'#(\w+)')
                        hashtag_matches = hashtag_pattern.findall(content_text)
                        
                        if hashtag_matches:
                            hashtags = hashtag_matches
                            self.stdout.write(self.style.SUCCESS(f"İçerikte bulunan hashtag'ler: {', '.join(hashtags)}"))
                            
                            # Hashtag'lere göre kategori güncelleme yapılabilir
                            # Şimdilik sadece log yapalım
                            for tag in hashtags:
                                if tag:  # Boş olmadığından emin ol
                                    tag_lower = tag.lower()
                                    for key, value in kategori_eslesme.items():
                                        if key == tag_lower:
                                            self.stdout.write(self.style.SUCCESS(f"Hashtag eşleştirildi: #{tag} -> {value}"))
                                            break

                    # Tarih ve giriş bilgisini çek
                    entry_info = None
                    # Başlık altındaki "Giriş: 05-05-2023 15:47" şeklindeki metni ara
                    entry_text = news_soup.find(string=re.compile('Giriş:\\s*\\d{2}-\\d{2}-\\d{4}'))
                    if entry_text:
                        self.stdout.write(self.style.SUCCESS(f"Giriş bilgisi bulundu: {entry_text.strip()}"))
                        entry_info = entry_text.strip()
                    
                    # Varolan haberi güncelle
                    if existing_haber:
                        self.stdout.write(self.style.WARNING(f'Varolan haber güncelleniyor: {existing_haber.baslik}'))
                        existing_haber.baslik = baslik
                        existing_haber.icerik = icerik
                        existing_haber.ozet = ozet
                        existing_haber.kategori = kategori
                        
                        # Çekilen yayın tarihini kullan (eğer varolan haber tarihinden daha yeniyse)
                        if yayin_tarihi > existing_haber.yayin_tarihi:
                            existing_haber.yayin_tarihi = yayin_tarihi
                        
                        existing_haber.guncelleme_tarihi = timezone.now()
                        
                        # Resim varsa ve önceki resimden farklıysa güncelle
                        if resim_url:
                            try:
                                img_response = requests.get(resim_url, stream=True)
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
                            yayin_tarihi=yayin_tarihi  # Çekilen yayın tarihini kullan
                        )
                        
                        # Resim varsa indir ve kaydet
                        if resim_url:
                            try:
                                img_response = requests.get(resim_url, stream=True)
                                if img_response.status_code == 200:
                                    # Dosya adı oluştur
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