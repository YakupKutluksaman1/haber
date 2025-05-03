from django.contrib import admin
from django import forms
from .models import Haber, Kategori, Yorum, Ilan
from ckeditor_uploader.widgets import CKEditorUploadingWidget

class HaberForm(forms.ModelForm):
    icerik = forms.CharField(widget=CKEditorUploadingWidget())
    
    class Meta:
        model = Haber
        fields = '__all__'

class KategoriAdmin(admin.ModelAdmin):
    list_display = ('ad', 'slug', 'icon', 'aciklama')
    prepopulated_fields = {'slug': ('ad',)}
    search_fields = ('ad',)

class HaberAdmin(admin.ModelAdmin):
    form = HaberForm
    list_display = ('baslik', 'kategori', 'yayin_tarihi', 'yazar', 'yayinda', 'manset')
    list_filter = ('kategori', 'yayin_tarihi', 'yayinda', 'manset')
    search_fields = ('baslik', 'icerik', 'ozet')
    prepopulated_fields = {'slug': ('baslik',)}
    readonly_fields = ('olusturulma_tarihi', 'guncelleme_tarihi')
    list_editable = ('yayinda', 'manset')
    
    fieldsets = (
        ('Temel Bilgiler', {
            'fields': ('baslik', 'slug', 'kategori', 'yazar', 'yayin_tarihi', 'yayinda', 'manset')
        }),
        ('İçerik', {
            'fields': ('ozet', 'icerik', 'resim')
        }),
        ('Tarihler', {
            'fields': ('olusturulma_tarihi', 'guncelleme_tarihi'),
            'classes': ('collapse',)
        }),
    )

class YorumAdmin(admin.ModelAdmin):
    list_display = ('haber', 'yazar', 'olusturulma_tarihi', 'aktif')
    list_filter = ('aktif', 'olusturulma_tarihi')
    search_fields = ('icerik', 'yazar__username', 'haber__baslik')
    list_editable = ('aktif',)

class IlanAdmin(admin.ModelAdmin):
    list_display = ('firma_adi', 'faaliyet_alani', 'durum', 'bitis_tarihi', 'one_cikarilmis', 'goruntulenme_sayisi')
    list_filter = ('durum', 'one_cikarilmis')
    search_fields = ('firma_adi', 'faaliyet_alani', 'aciklama', 'adres')
    prepopulated_fields = {'slug': ('firma_adi',)}
    readonly_fields = ('olusturulma_tarihi', 'guncelleme_tarihi', 'goruntulenme_sayisi')
    list_editable = ('durum', 'one_cikarilmis')
    
    fieldsets = (
        ('Firma Bilgileri', {
            'fields': ('firma_adi', 'slug', 'faaliyet_alani', 'logo')
        }),
        ('İlan Detayları', {
            'fields': ('aciklama', 'durum', 'bitis_tarihi', 'one_cikarilmis')
        }),
        ('İletişim Bilgileri', {
            'fields': ('adres', 'telefon', 'email', 'website')
        }),
        ('Diğer Bilgiler', {
            'fields': ('ekleyen', 'olusturulma_tarihi', 'guncelleme_tarihi', 'goruntulenme_sayisi'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:  # Eğer yeni bir kayıt oluşturuluyorsa
            obj.ekleyen = request.user
        super().save_model(request, obj, form, change)

admin.site.register(Haber, HaberAdmin)
admin.site.register(Kategori, KategoriAdmin)
admin.site.register(Yorum, YorumAdmin)
admin.site.register(Ilan, IlanAdmin)
