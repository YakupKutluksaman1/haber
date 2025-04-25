from django.urls import path
from . import views

urlpatterns = [
    path('', views.ana_sayfa, name='ana_sayfa'),
    path('kategori/<slug:kategori_slug>/', views.kategori_haberleri, name='kategori_haberleri'),
    path('haber/<slug:haber_slug>/', views.haber_detay, name='haber_detay'),
    path('ara/', views.haber_ara, name='haber_ara'),
] 