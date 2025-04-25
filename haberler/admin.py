from django.contrib import admin
from .models import Haber, Kategori

class KategoriAdmin(admin.ModelAdmin):
    list_display = ('ad', 'slug', 'icon', 'aciklama')
    prepopulated_fields = {'slug': ('ad',)}
    search_fields = ('ad',)

class HaberAdmin(admin.ModelAdmin):
    list_display = ('baslik', 'kategori', 'yayin_tarihi', 'yazar', 'yayinda')
    list_filter = ('kategori', 'yayin_tarihi', 'yayinda')
    search_fields = ('baslik', 'icerik', 'ozet')
    prepopulated_fields = {'slug': ('baslik',)}
    readonly_fields = ('olusturulma_tarihi', 'guncelleme_tarihi')
    
    fieldsets = (
        ('Temel Bilgiler', {
            'fields': ('baslik', 'slug', 'kategori', 'yazar', 'yayin_tarihi', 'yayinda')
        }),
        ('İçerik', {
            'fields': ('ozet', 'icerik', 'resim')
        }),
        ('Tarihler', {
            'fields': ('olusturulma_tarihi', 'guncelleme_tarihi'),
            'classes': ('collapse',)
        }),
    )

admin.site.register(Haber, HaberAdmin)
admin.site.register(Kategori, KategoriAdmin)
