"""
URL configuration for haber_sitesi project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from django.views.generic import TemplateView
from haberler.views import fetch_tekha_news

# Özel admin URL'lerini admin.site.urls'den önce tanımla
urlpatterns = [
    # Google Search Console doğrulama dosyası
    path('googlea29b1506f669d0fc.html', TemplateView.as_view(template_name='googlea29b1506f669d0fc.html', content_type='text/html')),
    
    # Admin sayfasındaki haber çekme işlemi için URL
    path('haberleri-cek/', fetch_tekha_news, name='fetch_tekha_news_admin'),
    # Standart admin URLs
    path('admin/', admin.site.urls),
    # Uygulamanın ana URL'leri
    path('', include('haberler.urls')),
    path('ckeditor/', include('ckeditor_uploader.urls')),
    path('favicon.ico', RedirectView.as_view(url='/static/img/favicon.ico')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
