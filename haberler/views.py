from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from .models import Haber, Kategori
from django.utils import timezone
from datetime import timedelta
import yfinance as yf
from datetime import datetime
import requests
from django.conf import settings

def get_financial_data():
    try:
        # Döviz sembolleri
        usd_try = yf.Ticker("USDTRY=X")
        eur_try = yf.Ticker("EURTRY=X")
        gbp_try = yf.Ticker("GBPTRY=X")
        
        # Altın sembolü
        gold = yf.Ticker("GC=F")  # COMEX Gold
        
        # BIST 100 sembolü
        bist = yf.Ticker("XU100.IS")
        
        # Son 1 günlük verileri al
        end_date = datetime.now()
        start_date = end_date - timedelta(days=1)
        
        # Döviz verilerini al
        usd_data = usd_try.history(start=start_date, end=end_date)
        eur_data = eur_try.history(start=start_date, end=end_date)
        gbp_data = gbp_try.history(start=start_date, end=end_date)
        
        # Altın verilerini al (USD cinsinden)
        gold_data = gold.history(start=start_date, end=end_date)
        
        # BIST 100 verilerini al
        bist_data = bist.history(start=start_date, end=end_date)
        
        # Son kapanış fiyatlarını al
        usd_try_rate = round(usd_data['Close'].iloc[-1], 4)
        eur_try_rate = round(eur_data['Close'].iloc[-1], 4)
        gbp_try_rate = round(gbp_data['Close'].iloc[-1], 4)
        gold_usd = round(gold_data['Close'].iloc[-1], 2)
        bist_value = round(bist_data['Close'].iloc[-1], 2)
        
        # Altını gram cinsine çevir (1 ons = 31.1034768 gram)
        gold_gram_usd = gold_usd / 31.1034768
        # Gram altını TL'ye çevir
        gold_try = round(gold_gram_usd * usd_try_rate, 2)
        
        # Son güncelleme zamanını al (sadece saat)
        last_updated = timezone.now().strftime('%H:%M')
        print(f"Son güncelleme zamanı: {last_updated}")  # Debug için
        
        data = {
            'usd': usd_try_rate,
            'eur': eur_try_rate,
            'gbp': gbp_try_rate,
            'gold': gold_try,
            'bist': bist_value,
            'last_updated': last_updated
        }
        print(f"Dönen veri: {data}")  # Debug için
        return data
    except Exception as e:
        print(f"Veri çekme hatası: {str(e)}")
        return {
            'usd': 0,
            'eur': 0,
            'gbp': 0,
            'gold': 0,
            'bist': 0,
            'last_updated': timezone.now().strftime('%H:%M')
        }

def ana_sayfa(request):
    # Son 10 haberi al
    son_dakika_haberler = Haber.objects.filter(
        yayinda=True
    ).order_by('-yayin_tarihi')[:10]

    # Tüm yayındaki haberleri al
    haberler = Haber.objects.filter(
        yayinda=True
    ).order_by('-yayin_tarihi')

    # Ekonomik verileri al
    financial_data = get_financial_data()

    context = {
        'son_dakika_haberler': son_dakika_haberler,
        'haberler': haberler,
        'financial_data': financial_data,
        'kategoriler': Kategori.objects.all()
    }

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
        haberler = Haber.objects.filter(
            yayinda=True,
            baslik__icontains=arama_terimi
        ).order_by('-yayin_tarihi')
    else:
        haberler = Haber.objects.none()
    
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
        'kategoriler': Kategori.objects.all(),
    })
