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

def get_financial_data():
    try:
        # Döviz sembolleri
        usd_try = yf.Ticker("USDTRY=X")
        eur_try = yf.Ticker("EURTRY=X")
        gbp_try = yf.Ticker("GBPTRY=X")
        
        # Altın sembolü (USD cinsinden)
        gold_usd = yf.Ticker("GC=F")
        
        # BIST 100 sembolü
        bist = yf.Ticker("XU100.IS")
        
        # Son 3 günlük verileri al
        end_date = datetime.now()
        start_date = end_date - timedelta(days=3)
        
        # Döviz verilerini al
        usd_data = usd_try.history(start=start_date, end=end_date, interval="1d")
        eur_data = eur_try.history(start=start_date, end=end_date, interval="1d")
        gbp_data = gbp_try.history(start=start_date, end=end_date, interval="1d")
        
        # Altın verilerini al (USD cinsinden)
        gold_data = gold_usd.history(start=start_date, end=end_date, interval="1d")
        
        # BIST 100 verilerini al
        bist_data = bist.history(start=start_date, end=end_date, interval="1d")
        
        # Veri kontrolü
        if usd_data.empty or eur_data.empty or gbp_data.empty or gold_data.empty or bist_data.empty:
            raise Exception("Veri boş geldi")
        
        # Son kapanış fiyatlarını al
        usd_try_rate = round(usd_data['Close'].iloc[-1], 4)
        eur_try_rate = round(eur_data['Close'].iloc[-1], 4)
        gbp_try_rate = round(gbp_data['Close'].iloc[-1], 4)
        gold_usd_rate = round(gold_data['Close'].iloc[-1], 2)
        bist_value = round(bist_data['Close'].iloc[-1], 2)
        
        # Altını gram cinsine çevir (1 ons = 31.1034768 gram)
        gold_gram_usd = gold_usd_rate / 31.1034768
        # Gram altını TL'ye çevir
        gold_try = round(gold_gram_usd * usd_try_rate, 2)
        
        # Son güncelleme zamanını al
        last_updated = timezone.now().strftime('%H:%M')
        
        # Veri doğrulama
        if not all(isinstance(x, (int, float)) for x in [usd_try_rate, eur_try_rate, gbp_try_rate, gold_try, bist_value]):
            raise Exception("Geçersiz veri tipi")
        
        data = {
            'usd': usd_try_rate,
            'eur': eur_try_rate,
            'gbp': gbp_try_rate,
            'gold': gold_try,
            'bist': bist_value,
            'last_updated': last_updated
        }
        
        # Debug için verileri yazdır
        print("Çekilen veriler:", data)
        return data
        
    except Exception as e:
        print(f"Veri çekme hatası: {str(e)}")
        # Hata durumunda varsayılan değerler
        return {
            'usd': 32.00,
            'eur': 35.00,
            'gbp': 40.00,
            'gold': 2000,
            'bist': 10000,
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
