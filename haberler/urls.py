from django.urls import path
from . import views
from django.contrib.sitemaps.views import sitemap
from .sitemaps import HaberSitemap, KategoriSitemap, StatikSayfalarSitemap

# Sitemaps dictionary
sitemaps = {
    'haberler': HaberSitemap,
    'kategoriler': KategoriSitemap,
    'statik': StatikSayfalarSitemap,
}

urlpatterns = [
    path('', views.ana_sayfa, name='ana_sayfa'),
    path('kategori/<slug:kategori_slug>/', views.kategori_haberleri, name='kategori_haberleri'),
    path('haber/<slug:haber_slug>/', views.haber_detay, name='haber_detay'),
    path('arama/', views.haber_ara, name='haber_ara'),
    
    # İlan sayfaları
    path('ilanlar/', views.ilan_listesi, name='ilan_listesi'),
    path('ilan/<slug:ilan_slug>/', views.ilan_detay, name='ilan_detay'),

    # Kurumsal Sayfalar
    path('hakkimizda/', views.hakkimizda, name='hakkimizda'),
    path('kunye/', views.kunye, name='kunye'),
    path('yayin-ilkeleri/', views.yayin_ilkeleri, name='yayin_ilkeleri'),
    path('gizlilik-politikasi/', views.gizlilik_politikasi, name='gizlilik_politikasi'),
    path('kvkk/', views.kvkk, name='kvkk'),
    path('cerez-politikasi/', views.cerez_politikasi, name='cerez_politikasi'),
    
    # Haber çekme işlemleri
    path('haberleri-cek/', views.fetch_tekha_news, name='fetch_tekha_news'),
    path('tum-haberleri-cek/', views.fetch_all_categories, name='fetch_all_categories'),

    # Sitemap URL'i
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
] 