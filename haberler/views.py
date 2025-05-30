from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from .models import Haber, Kategori, Ilan, Yorum
from django.utils import timezone
from datetime import timedelta
import yfinance as yf
from datetime import datetime
import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.core.cache import cache
import xml.etree.ElementTree as ET
import json
from bs4 import BeautifulSoup
import re
from django.http import HttpResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.core.management import call_command

# BIST veri kaynakları - en güvenilir birkaç kaynak
bist_sources = [
    {
        'name': 'Borsa İstanbul Resmi',
        'url': 'https://www.borsaistanbul.com/tr/endeks-detay/1000/bist-100',
        'regex': r'Değer[^>]*>[^>]*>([0-9]{1,3}[.,][0-9]{3}[.,][0-9]{2})',
        'process': lambda text: text.replace('.', '').replace(',', '.').strip()
    },
    {
        'name': 'Bloomberg HT Son Fiyat',
        'url': 'https://www.bloomberght.com/borsa',
        'regex': r'BIST\s*100\s*Endeks[^0-9]*([0-9]{1,3}[.,][0-9]{3}[.,][0-9]{2}|[0-9]{2,5}[.,][0-9]{2})',
        'process': lambda text: text.replace('.', '').replace(',', '.').strip()
    }
]

def get_financial_data():
    try:
        from datetime import datetime
        from django.utils import timezone
        import xml.etree.ElementTree as ET
        import re
        
        # GÜNCEL FİNANSAL VERİLER - Bu değerler sadece son çare olarak kullanılır
        # Son güncelleme tarihi: 10 Mayıs 2025
        CURRENT_VALUES = {
            'usd': 38.70,  # USD/TRY
            'eur': 43.53,  # EUR/TRY
            'gbp': 51.42,  # GBP/TRY
            'gold': 4142.72,  # Gram altın TL
            'bist': 9390.51  # BIST 100 endeksi - Borsa İstanbul resmi siteden alındı
        }
        
        # Her zaman API'lerden taze veri çekilecek
        print("API'lerden taze veriler çekiliyor...")
            
        # Veri çekme işlemleri
        result_data = {}
        
        # 1. TCMB'den günlük döviz kurlarını çek (hızlı ve güvenilir)
        try:
            # TCMB XML servisi - Türkiye'nin resmi kur verileri
            tcmb_url = "https://www.tcmb.gov.tr/kurlar/today.xml"
            response = requests.get(tcmb_url, timeout=5)
            
            if response.status_code == 200:
                # XML verisini parse et
                root = ET.fromstring(response.content)
                
                # Döviz kurlarını bul - Efektif Satış değeri
                usd_try = float(root.find("./Currency[@Kod='USD']/BanknoteSelling").text.replace(',', '.'))
                eur_try = float(root.find("./Currency[@Kod='EUR']/BanknoteSelling").text.replace(',', '.'))
                gbp_try = float(root.find("./Currency[@Kod='GBP']/BanknoteSelling").text.replace(',', '.'))
                
                # Döviz kurlarını result_data'ya ekle
                result_data['usd'] = round(usd_try, 2)
                result_data['eur'] = round(eur_try, 2)
                result_data['gbp'] = round(gbp_try, 2)
                
                print(f"TCMB'den döviz kurları çekildi: USD={usd_try}, EUR={eur_try}, GBP={gbp_try}")
                
            else:
                # TCMB başarısız olursa sabit değerleri kullan
                result_data['usd'] = CURRENT_VALUES['usd']
                result_data['eur'] = CURRENT_VALUES['eur']
                result_data['gbp'] = CURRENT_VALUES['gbp']
                print(f"TCMB API hatası, sabit değerler kullanıldı: USD={result_data['usd']}, EUR={result_data['eur']}, GBP={result_data['gbp']}")
                
        except Exception as tcmb_error:
            print(f"TCMB veri çekme hatası: {str(tcmb_error)}")
            # TCMB başarısız olursa sabit değerleri kullan
            result_data['usd'] = CURRENT_VALUES['usd']
            result_data['eur'] = CURRENT_VALUES['eur']
            result_data['gbp'] = CURRENT_VALUES['gbp']
            print(f"TCMB API hatası, sabit değerler kullanıldı: USD={result_data['usd']}, EUR={result_data['eur']}, GBP={result_data['gbp']}")
        
        # 2. Altın ve BIST verilerini web scraping ile çek
        try:
            from bs4 import BeautifulSoup
            
            # ------------------------------- ALTIN VERİLERİ -------------------------------
            # Daha hızlı ve güvenilir olan kaynaklardan altın verisi çekmeyi deneyelim
            # Altın veri kaynakları - öncelik sırasına göre
            gold_sources = [
                {
                    'name': 'Bigpara',
                    'url': 'https://bigpara.hurriyet.com.tr/altin/gram-altin-fiyati/',
                    'selector': 'span.value',
                    'process': lambda text: text.replace('.', '').replace(',', '.')
                }
            ]
            
            # Altın verisi için sırayla tüm kaynakları dene
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            for source in gold_sources:
                if 'gold' in result_data:
                    break  # Eğer altın verisi bulunmuşsa diğer kaynaklara bakma
                    
                try:
                    print(f"{source['name']} altın verisi deneniyor...")
                    gold_response = requests.get(source['url'], headers=headers, timeout=8)
                    
                    if gold_response.status_code == 200:
                        soup = BeautifulSoup(gold_response.content, 'html.parser')
                        gold_element = soup.select_one(source['selector'])
                        
                        if gold_element and gold_element.text.strip():
                            gold_text = source['process'](gold_element.text.strip())
                            
                            if gold_text and re.match(r'^\d+(\.\d+)?$', gold_text):
                                gold_try = float(gold_text)
                                result_data['gold'] = round(gold_try, 2)
                                print(f"{source['name']}'den altın fiyatı başarıyla çekildi: {gold_try}")
                            else:
                                print(f"{source['name']} altın verisi sayısal değil: '{gold_text}'")
                        else:
                            print(f"{source['name']} altın elementi bulunamadı")
                    else:
                        print(f"{source['name']} HTTP hatası: {gold_response.status_code}")
                        
                except Exception as gold_error:
                    print(f"{source['name']} altın veri çekme hatası: {str(gold_error)}")
            
            # Altın verisi çekilemediyse sabit değerleri kullan
            if 'gold' not in result_data:
                result_data['gold'] = CURRENT_VALUES['gold']
                print(f"Altın verisi çekilemedi, sabit değer kullanıldı: {result_data['gold']}")
            
            # ------------------------------- BIST VERİLERİ -------------------------------
            # Borsa İstanbul verilerini çekelim
            try:
                bist_value = get_bist_from_web()
                if bist_value:
                    result_data['bist'] = bist_value
                    print(f"BIST 100 değeri başarıyla alındı: {bist_value}")
                else:
                    print("BIST verisi çekilemedi, sabit değer kullanılacak")
                    result_data['bist'] = CURRENT_VALUES['bist']
            except Exception as bist_error:
                print(f"BIST veri çekme genel hatası: {str(bist_error)}")
                result_data['bist'] = CURRENT_VALUES['bist']
            
        except ImportError:
            print("BeautifulSoup (bs4) kütüphanesi yüklü değil, sabit değerler kullanılacak.")
            # Sabit değerleri kullan
            result_data['gold'] = CURRENT_VALUES['gold']
            result_data['bist'] = CURRENT_VALUES['bist']
        except Exception as scraping_error:
            print(f"Web scraping hatası: {str(scraping_error)}")
            # Hata durumunda sabit değerleri kullan
            if 'gold' not in result_data:
                result_data['gold'] = CURRENT_VALUES['gold']
            if 'bist' not in result_data:
                result_data['bist'] = CURRENT_VALUES['bist']
        
        # Eksik değerleri manuel değerlerle doldur (son çare)
        for key in CURRENT_VALUES.keys():
            if key not in result_data:
                result_data[key] = CURRENT_VALUES[key]
                print(f"{key} için sabit değer kullanıldı: {result_data[key]}")
        
        # Son güncelleme saatini ekle
        result_data['last_updated'] = datetime.now().strftime('%H:%M')
        
        print("Güncel finansal veriler toplandı:", result_data)
        return result_data
        
    except Exception as e:
        print(f"Genel veri çekme hatası: {str(e)}")
        # Genel hata durumunda en güncel değerler
        return {
            'usd': 38.70,
            'eur': 43.53,
            'gbp': 51.42,
            'gold': 4142.72,
            'bist': 9390.51,  # Borsa İstanbul resmi siteden alınan güncel değer
            'last_updated': timezone.now().strftime('%H:%M')
        }

def ana_sayfa(request):
    # Son 10 haberi al
    son_dakika_haberler = Haber.objects.filter(
        yayinda=True
    ).order_by('-yayin_tarihi')[:10]

    # Manşet haberlerini al
    manset_haberler = Haber.objects.filter(
        yayinda=True,
        manset=True
    ).order_by('-yayin_tarihi')[:6]

    # Tüm yayındaki haberleri al
    haberler = Haber.objects.filter(
        yayinda=True
    ).order_by('-yayin_tarihi')
    
    # Aktif ilanları al (en fazla 12 tane ve öne çıkarılmışlara öncelik ver)
    ilanlar = Ilan.objects.filter(
        durum='aktif',
        bitis_tarihi__gt=timezone.now()
    ).order_by('-one_cikarilmis', '-olusturulma_tarihi')[:12]

    # Ekonomik verileri al
    financial_data = get_financial_data()

    # Sayfalama
    paginator = Paginator(haberler, 12)  # Her sayfada 12 haber
    sayfa = request.GET.get('sayfa', 1)
    
    try:
        haberler = paginator.page(sayfa)
    except (PageNotAnInteger, ValueError):
        haberler = paginator.page(1)
    except EmptyPage:
        haberler = paginator.page(paginator.num_pages)

    context = {
        'son_dakika_haberler': son_dakika_haberler,
        'manset_haberler': manset_haberler,
        'haberler': haberler,
        'ilanlar': ilanlar,
        'financial_data': financial_data,
        'kategoriler': Kategori.objects.all()
    }

    # AJAX isteği için JSON yanıtı döndür
    if request.GET.get('format') == 'json':
        from django.template.loader import render_to_string
        from django.http import JsonResponse
        
        # Haber listesini JSON için hazırla
        haber_listesi = []
        for haber in haberler:
            # Haber modelinin özelliklerini kontrol ederek ekle
            haber_dict = {
                'id': haber.id,
                'baslik': haber.baslik,
                'slug': haber.slug,
                'kategori': haber.kategori.ad if haber.kategori else None,
                'yayın_tarihi': haber.yayin_tarihi.strftime('%d %B %Y'),
                'goruntulenme_sayisi': haber.goruntulenme_sayisi,
            }
            
            # yorum_sayisi özelliği varsa ekle
            if hasattr(haber, 'yorum_sayisi'):
                haber_dict['yorum_sayisi'] = haber.yorum_sayisi
            # Eğer yorumlar özelliği varsa, onun sayısını hesapla
            elif hasattr(haber, 'yorumlar'):
                try:
                    haber_dict['yorum_sayisi'] = haber.yorumlar.filter(aktif=True).count()
                except:
                    haber_dict['yorum_sayisi'] = 0
            else:
                haber_dict['yorum_sayisi'] = 0
                
            haber_listesi.append(haber_dict)
        
        # Sadece haber kartlarını render et
        html_content = render_to_string('haberler/includes/haber_kartlari.html', {'haberler': haberler})
        
        return JsonResponse({
            'haberHTML': html_content,
            'haberler': haber_listesi,
            'has_next': haberler.has_next(),
            'next_page': haberler.next_page_number() if haberler.has_next() else None,
            'current_page': haberler.number,
        })
        
    return render(request, 'haberler/ana_sayfa.html', context)

def kategori_haberleri(request, kategori_slug):
    kategori = get_object_or_404(Kategori, slug=kategori_slug)
    
    # Sıralama parametresi
    siralama = request.GET.get('siralama', 'newest')
    
    # Tarih filtresi
    tarih_filtresi = request.GET.get('tarih', 'all')
    
    # Temel sorgu - yayında olan ve yayın tarihi geçmiş haberleri getir
    haberler = Haber.objects.select_related('kategori', 'yazar').filter(
        kategori=kategori,
        yayinda=True,
        yayin_tarihi__lte=timezone.now()
    )
    
    # Tarih filtresi uygula
    if tarih_filtresi == 'today':
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        haberler = haberler.filter(yayin_tarihi__gte=today_start)
    elif tarih_filtresi == 'week':
        week_ago = timezone.now() - timedelta(days=7)
        haberler = haberler.filter(yayin_tarihi__gte=week_ago)
    elif tarih_filtresi == 'month':
        month_ago = timezone.now() - timedelta(days=30)
        haberler = haberler.filter(yayin_tarihi__gte=month_ago)
    
    # Sıralama uygula
    if siralama == 'newest':
        haberler = haberler.order_by('-yayin_tarihi')
    elif siralama == 'popular':
        haberler = haberler.order_by('-goruntulenme_sayisi', '-yayin_tarihi')
    elif siralama == 'most_viewed':
        haberler = haberler.order_by('-goruntulenme_sayisi', '-yayin_tarihi')
    
    # Son güncelleme tarihini al
    try:
        son_guncelleme = haberler.first().yayin_tarihi if haberler.exists() else timezone.now()
    except AttributeError:
        son_guncelleme = timezone.now()
    
    # Sayfalama
    paginator = Paginator(haberler, 12)
    page = request.GET.get('sayfa', 1)
    
    try:
        haberler = paginator.page(page)
    except (PageNotAnInteger, ValueError):
        haberler = paginator.page(1)
    except EmptyPage:
        haberler = paginator.page(paginator.num_pages)
    
    context = {
        'haberler': haberler,
        'kategori': kategori,
        'son_guncelleme': son_guncelleme,
        'siralama': siralama,
        'tarih_filtresi': tarih_filtresi,
        'kategoriler': Kategori.objects.all(),
    }
    
    return render(request, 'haberler/kategori_haberleri.html', context)

def haber_detay(request, haber_slug):
    haber = get_object_or_404(Haber, slug=haber_slug, yayinda=True)
    
    # Görüntülenme sayısını artır
    haber.goruntulenme_sayisi += 1
    haber.save()
    
    # Benzer haberleri getir
    benzer_haberler = Haber.objects.filter(
        kategori=haber.kategori,
        yayinda=True
    ).exclude(id=haber.id).order_by('-yayin_tarihi')[:3]
    
    # En çok okunan haberleri getir
    en_cok_okunanlar = Haber.objects.filter(
        yayinda=True
    ).exclude(id=haber.id).order_by('-goruntulenme_sayisi')[:3]
    
    # Son yorumları getir
    son_yorumlar = haber.yorumlar.filter(aktif=True).order_by('-olusturulma_tarihi')[:5]
    
    kategoriler = Kategori.objects.all()
    
    return render(request, 'haberler/haber_detay.html', {
        'haber': haber,
        'benzer_haberler': benzer_haberler,
        'en_cok_okunanlar': en_cok_okunanlar,
        'son_yorumlar': son_yorumlar,
        'kategoriler': kategoriler,
    })

def haber_ara(request):
    arama_terimi = request.GET.get('q', '')
    if arama_terimi:
        # Her bir kelimeyi ayrı ayrı arayacak şekilde sorguları oluştur
        kelimeler = arama_terimi.split()
        q_objects = Q()
        
        # Her bir kelime için OR sorgusu oluştur
        for kelime in kelimeler:
            # Sadece başlıktaki eşleşmeleri arayacak şekilde düzenlendi
            q_objects |= Q(baslik__icontains=kelime)
        
        # Filtreyi uygula - sadece başlıklarda arama
        haberler = Haber.objects.filter(
            q_objects,
            yayinda=True
        ).distinct()
        
        # Önce başlık eşleşmelerini üste getirelim
        haberler_baslik_eslesme = []
        haberler_diger = []
        
        for haber in haberler:
            baslikta_var = False
            
            # Başlıkta herhangi bir kelime var mı kontrol et
            for kelime in kelimeler:
                if kelime.lower() in haber.baslik.lower():
                    baslikta_var = True
                    break
            
            if baslikta_var:
                haberler_baslik_eslesme.append(haber.id)
            else:
                haberler_diger.append(haber.id)
                
        # Özel sıralama için Case kullan
        from django.db.models import Case, When, Value, IntegerField
        preserved_baslik = Case(*[When(id=id, then=Value(i)) for i, id in enumerate(haberler_baslik_eslesme)], output_field=IntegerField())
        
        if haberler_baslik_eslesme:
            haberler_baslik = Haber.objects.filter(id__in=haberler_baslik_eslesme).order_by(preserved_baslik, '-yayin_tarihi')
            haberler_kalan = Haber.objects.filter(id__in=haberler_diger).order_by('-yayin_tarihi')
            # İki queryset'i birleştir
            from itertools import chain
            haberler_sirali = list(chain(haberler_baslik, haberler_kalan))
            
            # Sayfalama için tekrar queryset'e çevir
            from django.db.models import QuerySet
            haberler = QuerySet(model=Haber).none()
            haberler = haberler | Haber.objects.filter(id__in=[h.id for h in haberler_sirali])
        else:
            # Başlıkta eşleşen yoksa, normal sıralama kullan
            haberler = haberler.order_by('-yayin_tarihi')
            
        # Bulunan haberlerin kategorilerini al ve ilgili kategorileri bul
        secilen_kategori = None
        kategori_haberleri = []
        
        # Arama sonuçlarında haber varsa, ilk haberin kategorisi ile ilgili diğer haberleri getir
        if haberler.exists():
            # İlk bulunan haberin kategorisini al
            ilk_haber = haberler.first()
            if ilk_haber and ilk_haber.kategori:
                secilen_kategori = ilk_haber.kategori
                
                # Aynı kategorideki diğer haberleri getir (arama sonuçlarında olmayan)
                kategori_haberleri = Haber.objects.filter(
                    kategori=secilen_kategori,
                    yayinda=True
                ).exclude(
                    id__in=[h.id for h in haberler]
                ).order_by('-yayin_tarihi')[:10]  # En son 10 haber
        
        # Son eklenen haberler
        son_haberler = Haber.objects.filter(
            yayinda=True
        ).order_by('-yayin_tarihi')[:5]
    else:
        haberler = Haber.objects.none()
        secilen_kategori = None
        kategori_haberleri = []
        son_haberler = []
    
    # Arama terimleri için işlem
    arama_kelimeleri = [kelime.strip() for kelime in arama_terimi.split()] if arama_terimi else []
    
    # Sayfalama
    paginator = Paginator(haberler, 12)
    page = request.GET.get('sayfa')
    
    try:
        haberler = paginator.page(page)
    except PageNotAnInteger:
        haberler = paginator.page(1)
    except EmptyPage:
        haberler = paginator.page(paginator.num_pages)
    
    return render(request, 'haberler/arama.html', {
        'haberler': haberler,
        'arama_terimi': arama_terimi,
        'arama_kelimeleri': arama_kelimeleri,
        'kategoriler': Kategori.objects.all(),
        'secilen_kategori': secilen_kategori,
        'kategori_haberleri': kategori_haberleri,
        'son_haberler': son_haberler,
    })

def ilan_listesi(request):
    # Sıralama parametresi
    siralama = request.GET.get('siralama', 'yeni')
    
    # Tüm aktif ilanları getir
    ilanlar = Ilan.objects.filter(
        durum='aktif',
        bitis_tarihi__gt=timezone.now()
    )
    
    # Sıralama
    if siralama == 'yeni':
        ilanlar = ilanlar.order_by('-olusturulma_tarihi')
    elif siralama == 'populer':
        ilanlar = ilanlar.order_by('-goruntulenme_sayisi')
    elif siralama == 'one_cikan':
        ilanlar = ilanlar.order_by('-one_cikarilmis', '-olusturulma_tarihi')
    
    # Sayfalama
    paginator = Paginator(ilanlar, 12)  # Sayfa başına 12 ilan
    page = request.GET.get('sayfa', 1)
    
    try:
        ilanlar = paginator.page(page)
    except (PageNotAnInteger, ValueError):
        ilanlar = paginator.page(1)
    except EmptyPage:
        ilanlar = paginator.page(paginator.num_pages)
    
    context = {
        'ilanlar': ilanlar,
        'kategoriler': Kategori.objects.all(),
        'siralama': siralama
    }
    
    return render(request, 'haberler/ilan_listesi.html', context)

def ilan_detay(request, ilan_slug):
    ilan = get_object_or_404(Ilan, slug=ilan_slug, durum='aktif')
    
    # Görüntülenme sayısını artır
    ilan.goruntulenme_sayisi += 1
    ilan.save()
    
    # Diğer ilanlar
    diger_ilanlar = Ilan.objects.filter(
        durum='aktif',
        bitis_tarihi__gt=timezone.now()
    ).exclude(id=ilan.id).order_by('-one_cikarilmis', '-olusturulma_tarihi')[:4]
    
    context = {
        'ilan': ilan,
        'diger_ilanlar': diger_ilanlar,
        'kategoriler': Kategori.objects.all()
    }
    
    return render(request, 'haberler/ilan_detay.html', context)

@login_required
def ilan_ekle(request):
    if request.method == 'POST':
        # Form verilerini al
        firma_adi = request.POST.get('firma_adi')
        faaliyet_alani = request.POST.get('faaliyet_alani')
        aciklama = request.POST.get('aciklama')
        adres = request.POST.get('adres')
        telefon = request.POST.get('telefon')
        email = request.POST.get('email', '')
        website = request.POST.get('website', '')
        kategori_id = request.POST.get('kategori')
        
        # Sosyal medya
        facebook = request.POST.get('facebook', '')
        instagram = request.POST.get('instagram', '')
        twitter = request.POST.get('twitter', '')
        youtube = request.POST.get('youtube', '')
        linkedin = request.POST.get('linkedin', '')
        
        # Bitiş tarihi (varsayılan olarak 30 gün)
        bitis_tarihi = timezone.now() + timedelta(days=30)
        
        # Temel doğrulamalar
        if not (firma_adi and faaliyet_alani and aciklama and adres and telefon and kategori_id):
            messages.error(request, 'Lütfen zorunlu alanları doldurun.')
            return redirect('ilan_ekle')
        
        try:
            kategori = Kategori.objects.get(id=kategori_id)
            
            # Yeni ilan oluştur
            ilan = Ilan(
                firma_adi=firma_adi,
                faaliyet_alani=faaliyet_alani,
                aciklama=aciklama,
                adres=adres,
                telefon=telefon,
                email=email,
                website=website,
                facebook=facebook,
                instagram=instagram,
                twitter=twitter,
                youtube=youtube,
                linkedin=linkedin,
                kategori=kategori,
                ekleyen=request.user,
                bitis_tarihi=bitis_tarihi,
                durum='beklemede'  # Onay bekliyor olarak başlat
            )
            
            # Logo ve fotoğrafları işle
            if 'logo' in request.FILES:
                ilan.logo = request.FILES['logo']
            if 'fotograf1' in request.FILES:
                ilan.fotograf1 = request.FILES['fotograf1']
            if 'fotograf2' in request.FILES:
                ilan.fotograf2 = request.FILES['fotograf2']
            if 'fotograf3' in request.FILES:
                ilan.fotograf3 = request.FILES['fotograf3']
            
            ilan.save()
            messages.success(request, 'İlanınız başarıyla oluşturuldu ve onay için gönderildi.')
            return redirect('ilan_listesi')
            
        except Exception as e:
            messages.error(request, f'İlan eklenirken bir hata oluştu: {str(e)}')
            return redirect('ilan_ekle')
    
    # GET isteği için form sayfasını göster
    context = {
        'kategoriler': Kategori.objects.all()
    }
    
    return render(request, 'haberler/ilan_ekle.html', context)

# Kurumsal sayfalar için view'lar
def hakkimizda(request):
    kategoriler = Kategori.objects.all()
    return render(request, 'haberler/sayfalar/hakkimizda.html', {
        'kategoriler': kategoriler,
    })

def kunye(request):
    kategoriler = Kategori.objects.all()
    return render(request, 'haberler/sayfalar/kunye.html', {
        'kategoriler': kategoriler,
    })

def yayin_ilkeleri(request):
    kategoriler = Kategori.objects.all()
    return render(request, 'haberler/sayfalar/yayin-ilkeleri.html', {
        'kategoriler': kategoriler,
    })

def gizlilik_politikasi(request):
    kategoriler = Kategori.objects.all()
    return render(request, 'haberler/sayfalar/gizlilik-politikasi.html', {
        'kategoriler': kategoriler,
    })

def kvkk(request):
    kategoriler = Kategori.objects.all()
    return render(request, 'haberler/sayfalar/kvkk.html', {
        'kategoriler': kategoriler,
    })

def cerez_politikasi(request):
    kategoriler = Kategori.objects.all()
    return render(request, 'haberler/sayfalar/cerez-politikasi.html', {
        'kategoriler': kategoriler,
    })

# BIST verilerini getiren fonksiyonu güncelleyerek yeniliyorum
def get_bist_from_web():
    # Farklı User-Agent'lar ile deneyelim
    user_agents = [
        # Normal tarayıcı - yeni URL için daha etkili olabilir
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36',
        # Mobil tarayıcı
        'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
        # Windows / Chrome
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    ]
    
    # Borsa İstanbul sitesinden direkt veri çekmeyi deneyelim
    try:
        url = 'https://www.borsaistanbul.com/tr/endeks-detay/1000/bist-100'
        headers = {
            'User-Agent': user_agents[0],
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7'
        }
        
        print("Borsa İstanbul sitesinden BIST 100 verisi çekiliyor...")
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            # HTML içeriğinde BIST 100 değerini arayalım
            # Tam HTML yapısına göre daha spesifik arama
            html_content = response.text
            
            # BeautifulSoup ile düzgün parse edelim
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # İlk yöntem: Değeri içeren td'yi bulmayı deneyelim
            # Belirli bir class ile bolder-and-larger class'ına sahip td'leri arayalım
            value_cells = soup.select('td.bolder-and-larger')
            if value_cells and len(value_cells) > 0:
                # İlk bolder-and-larger hücresini alıp, içeriğini temizleyelim
                value_text = value_cells[0].text.strip()
                print(f"Borsa İstanbul BIST 100 değeri (class ile): {value_text}")
                
                # Değeri sayısal formata çevirelim
                bist_text = value_text.replace('.', '').replace(',', '.')
                if bist_text and re.match(r'^\d+(\.\d+)?$', bist_text):
                    bist_value = float(bist_text)
                    print(f"Borsa İstanbul'dan BIST 100 değeri başarıyla çekildi: {bist_value}")
                    return round(bist_value, 2)
            
            # İkinci yöntem: doğrudan HTML içinde daha spesifik regex kullanarak değeri alalım
            # HTML yapısını tam olarak arıyoruz: class="bolder-and-larger">9.390,51</td>
            bist_regex = r'class="bolder-and-larger">\s*([0-9]{1,3}[.,][0-9]{3}[.,][0-9]{2})\s*</td>'
            bist_match = re.search(bist_regex, html_content)
            
            if bist_match:
                bist_value_text = bist_match.group(1).strip()
                print(f"Borsa İstanbul BIST 100 değeri (regex ile): {bist_value_text}")
                
                # Değeri sayısal formata çevirelim
                bist_text = bist_value_text.replace('.', '').replace(',', '.')
                if bist_text and re.match(r'^\d+(\.\d+)?$', bist_text):
                    bist_value = float(bist_text)
                    print(f"Borsa İstanbul'dan BIST 100 değeri başarıyla çekildi: {bist_value}")
                    return round(bist_value, 2)
            
            # Üçüncü yöntem: Değer hücresini içeren tabloyu bulmayı deneyelim
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if cells and len(cells) > 0:
                        first_cell_text = cells[0].text.strip()
                        if 'değer' in first_cell_text.lower():
                            # Değer satırı bulundu, ikinci hücredeki değeri alalım
                            if len(cells) > 1:
                                value_text = cells[1].text.strip()
                                print(f"Borsa İstanbul BIST 100 değeri (tablo ile): {value_text}")
                                
                                # Değeri sayısal formata çevirelim
                                bist_text = value_text.replace('.', '').replace(',', '.')
                                if bist_text and re.match(r'^\d+(\.\d+)?$', bist_text):
                                    bist_value = float(bist_text)
                                    print(f"Borsa İstanbul'dan BIST 100 değeri başarıyla çekildi: {bist_value}")
                                    return round(bist_value, 2)
            
            # Dördüncü yöntem: Doğrudan Güncel Endeks Değerleri başlığı altındaki ilk sayıyı alalım
            # Tüm sayısal değerleri bul
            value_pattern = r'([0-9]{1,2}[.,][0-9]{3}[.,][0-9]{2})'
            value_matches = re.findall(value_pattern, html_content)
            
            if value_matches:
                # İlk eşleşen değeri kullanalım (muhtemelen Güncel Endeks Değerinin altındaki ilk değer)
                value_text = value_matches[0]
                print(f"Borsa İstanbul'da bulunan ilk BIST benzeri değer: {value_text}")
                
                # Değeri sayısal formata çevirelim
                bist_text = value_text.replace('.', '').replace(',', '.')
                if bist_text and re.match(r'^\d+(\.\d+)?$', bist_text):
                    bist_value = float(bist_text)
                    if 1000 <= bist_value <= 20000:  # BIST 100 değerleri genellikle bu aralıkta
                        print(f"Borsa İstanbul'dan BIST 100 değeri başarıyla çekildi: {bist_value}")
                        return round(bist_value, 2)
            
            print("Borsa İstanbul sitesinden BIST 100 değeri bulunamadı")
        else:
            print(f"Borsa İstanbul sitesi HTTP hatası: {response.status_code}")
    except Exception as error:
        print(f"Borsa İstanbul veri çekme hatası: {str(error)}")
    
    # Bloomberg HT'den veri çekmeyi deneyelim (yedek kaynak)
    try:
        for i, source in enumerate(bist_sources):
            if 'bloomberg' in source['name'].lower():
                user_agent = user_agents[i % len(user_agents)]
                
                headers = {
                    'User-Agent': user_agent,
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
                    'Referer': 'https://www.google.com/'
                }
                
                print(f"{source['name']} BIST verisi deneniyor...")
                response = requests.get(source['url'], headers=headers, timeout=15)
                
                if response.status_code == 200:
                    # Sayfanın metnini düşük harfe çevirelim
                    page_text = response.text.lower()
                    
                    # Normal regex araması
                    matches = re.search(source['regex'], page_text)
                    if matches:
                        # Regex paternindeki grupları kontrol et
                        groups = matches.groups()
                        value_group = groups[-1] if len(groups) > 1 else groups[0]
                        
                        bist_text = source['process'](value_group)
                        
                        # Sayısal değer olduğundan emin olalım
                        if bist_text and re.match(r'^\d+(\.\d+)?$', bist_text):
                            bist_value = float(bist_text)
                            
                            # BIST 100 değeri genellikle 1000-20000 arasındadır
                            if 1000 <= bist_value <= 20000:
                                print(f"{source['name']}'den BIST 100 değeri başarıyla çekildi: {bist_value}")
                                return round(bist_value, 2)
                            else:
                                print(f"{source['name']} bulunan değer BIST 100 aralığında değil: {bist_value}")
                        else:
                            print(f"{source['name']} bulunan değer sayısal değil: '{value_group}' -> '{bist_text}'")
    except Exception as error:
        print(f"Bloomberg HT veri çekme hatası: {str(error)}")
    
    # Hiçbir kaynaktan veri alamadık
    print("Hiçbir kaynaktan BIST verisi çekilemedi")
    return None

# Collectapi.com'dan BIST değerini alma yardımcı fonksiyonu - artık kullanılmıyor
def get_bist_from_collectapi():
    # collectapi'yi artık kullanmıyoruz çünkü ücretsiz değil
    print("Collectapi ücretsiz kullanılamıyor, bu kaynak atlandı")
    return None

# Yahoo Finance API'den BIST değerini alma yardımcı fonksiyonu - artık kullanılmıyor
def get_bist_from_yahoo_api():
    print("Yahoo Finance API rate limit sorunları yaşıyor, bu kaynak atlandı")
    return None

@staff_member_required
def fetch_tekha_news(request):
    """Admin kullanıcıları için TEKHA'dan Abdullah Solmaz haberlerini çeken basit bir view"""
    try:
        # Haber çekme komutunu çağır - Abdullah Solmaz haberleri için
        call_command('fetch_tekha_news', limit=10, force_update=False, verbosity=0)
        messages.success(request, "TEKHA sitesinden Abdullah Solmaz haberleri başarıyla çekildi!")
    except Exception as e:
        messages.error(request, f"Haber çekme sırasında hata oluştu: {str(e)}")
    
    # Admin anasayfasına yönlendir
    return redirect('admin:index')

@staff_member_required
def fetch_all_categories(request):
    """Admin kullanıcıları için TEKHA'dan tüm kategorilerdeki haberleri çeken view"""
    try:
        # Tüm kategorilerden haber çekme komutunu çağır - 5 sayfa ve 100 haber limiti ile
        call_command('fetch_all_categories', limit=100, max_pages=5, force_update=False, verbosity=0)
        messages.success(request, "TEKHA sitesinden tüm kategorilerdeki haberler başarıyla çekildi!")
    except Exception as e:
        messages.error(request, f"Tüm haberleri çekme sırasında hata oluştu: {str(e)}")
    
    # Admin anasayfasına yönlendir
    return redirect('admin:index')
