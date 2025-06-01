from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from .models import Haber, Kategori


class HaberSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.9
    protocol = 'https'

    def items(self):
        return Haber.objects.filter(aktif=True).order_by('-yayin_tarihi')

    def lastmod(self, obj):
        return obj.yayin_tarihi

    def location(self, obj):
        return f'/haber/{obj.slug}/'


class KategoriSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7
    protocol = 'https'

    def items(self):
        return Kategori.objects.filter(aktif=True)

    def location(self, obj):
        return f'/kategori/{obj.slug}/'


class StatikSayfalarSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.5
    protocol = 'https'

    def items(self):
        return ['ana_sayfa', 'kunye', 'yayin_ilkeleri', 'cerez_politikasi']

    def location(self, item):
        if item == 'ana_sayfa':
            return '/'
        elif item == 'kunye':
            return '/kunye/'
        elif item == 'yayin_ilkeleri':
            return '/yayin-ilkeleri/'
        elif item == 'cerez_politikasi':
            return '/cerez-politikasi/'
        return reverse(item) 