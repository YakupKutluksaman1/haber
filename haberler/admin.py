from django.contrib import admin
from django import forms
from .models import Haber, Kategori, Yorum, Ilan, HaberKaynagi
from ckeditor_uploader.widgets import CKEditorUploadingWidget
from django.utils.html import format_html
from django.utils import timezone
from django.core.management import call_command
from django.contrib import messages
from django.urls import path
from django.http import HttpResponseRedirect
from django.shortcuts import render, redirect
from django.urls import reverse

# Admin sitesini özelleştir
admin.site.site_header = 'Haber Sitesi Yönetimi'
admin.site.site_title = 'Haber Yönetim Paneli'
admin.site.index_title = 'Haber Sitesi Yönetimi'

# Uygulama ismini değiştir
admin.site.app_index_template = 'admin/app_index.html'

class HaberForm(forms.ModelForm):
    icerik = forms.CharField(widget=CKEditorUploadingWidget())
    
    class Meta:
        model = Haber
        fields = '__all__'

class YorumInline(admin.TabularInline):
    model = Yorum
    extra = 0

# Özel TemplateMixin
class AdminTemplateMixin:
    change_list_template = 'admin/haberler/haberkaynagi/change_list.html'

@admin.register(Haber)
class HaberAdmin(admin.ModelAdmin):
    form = HaberForm
    list_display = ('baslik', 'kategori', 'yazar_tam_ad', 'yayin_tarihi', 'yayinda', 'manset', 'goruntulenme_sayisi', 'otomatik_eklendi')
    list_filter = ('yayinda', 'manset', 'kategori', 'yazar', 'otomatik_eklendi')
    search_fields = ('baslik', 'icerik')
    prepopulated_fields = {'slug': ('baslik',)}
    date_hierarchy = 'yayin_tarihi'
    ordering = ('-yayin_tarihi',)
    raw_id_fields = ('yazar',)
    readonly_fields = ('goruntulenme_sayisi',)
    inlines = [YorumInline]
    actions = ['yayinla', 'yayindan_kaldir', 'fetch_all_news']
    
    def yazar_tam_ad(self, obj):
        return f"{obj.yazar.first_name} {obj.yazar.last_name}" if obj.yazar.first_name or obj.yazar.last_name else obj.yazar.username
    yazar_tam_ad.short_description = 'Yazar'
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('fetch-news/', self.admin_site.admin_view(self.fetch_news_view), name='fetch-news'),
        ]
        return custom_urls + urls
    
    def fetch_news_view(self, request):
        try:
            # Haber çekme komutunu çağır
            call_command('fetch_tekha_news', limit=50, force_update=False, verbosity=0)
            self.message_user(request, "Haberler başarıyla çekildi.", messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"Haber çekme sırasında hata oluştu: {str(e)}", messages.ERROR)
        return HttpResponseRedirect(reverse('admin:index'))
    
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['fetch_news_button'] = True
        return super().changelist_view(request, extra_context=extra_context)

    def yayinla(self, request, queryset):
        updated = queryset.update(yayinda=True)
        self.message_user(request, f'{updated} haber yayınlandı.')
    yayinla.short_description = "Seçili haberleri yayınla"

    def yayindan_kaldir(self, request, queryset):
        updated = queryset.update(yayinda=False)
        self.message_user(request, f'{updated} haber yayından kaldırıldı.')
    yayindan_kaldir.short_description = "Seçili haberleri yayından kaldır"
    
    def fetch_all_news(self, request, queryset):
        try:
            # Haber çekme komutunu çağır
            call_command('fetch_tekha_news', limit=50, force_update=False, verbosity=0)
            self.message_user(request, "Haberler başarıyla çekildi.", messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"Haber çekme sırasında hata oluştu: {str(e)}", messages.ERROR)
    
    fetch_all_news.short_description = "TEKHA'dan haberleri çek"

@admin.register(Kategori)
class KategoriAdmin(admin.ModelAdmin):
    list_display = ('ad', 'haber_sayisi', 'icon')
    search_fields = ('ad',)
    prepopulated_fields = {'slug': ('ad',)}
    
    def haber_sayisi(self, obj):
        return obj.haberler.count()
    haber_sayisi.short_description = 'Haber Sayısı'

@admin.register(Yorum)
class YorumAdmin(admin.ModelAdmin):
    list_display = ('yazar_tam_ad', 'haber', 'olusturulma_tarihi', 'aktif')
    list_filter = ('aktif', 'olusturulma_tarihi')
    search_fields = ('yazar__username', 'icerik', 'haber__baslik')
    actions = ['yorumu_onayla', 'yorumu_kaldir']
    
    def yazar_tam_ad(self, obj):
        return f"{obj.yazar.first_name} {obj.yazar.last_name}" if obj.yazar.first_name or obj.yazar.last_name else obj.yazar.username
    yazar_tam_ad.short_description = 'Yazar'
    
    def yorumu_onayla(self, request, queryset):
        updated = queryset.update(aktif=True)
        self.message_user(request, f'{updated} yorum onaylandı.')
    yorumu_onayla.short_description = "Seçili yorumları onayla"
    
    def yorumu_kaldir(self, request, queryset):
        updated = queryset.update(aktif=False)
        self.message_user(request, f'{updated} yorum kaldırıldı.')
    yorumu_kaldir.short_description = "Seçili yorumları kaldır"

@admin.register(Ilan)
class IlanAdmin(admin.ModelAdmin):
    list_display = ('firma_adi', 'faaliyet_alani', 'telefon', 'durum', 'bitis_tarihi_durumu', 'goruntulenme_sayisi')
    list_filter = ('durum', 'one_cikarilmis', 'olusturulma_tarihi')
    search_fields = ('firma_adi', 'faaliyet_alani', 'aciklama')
    prepopulated_fields = {'slug': ('firma_adi',)}
    date_hierarchy = 'olusturulma_tarihi'
    readonly_fields = ('goruntulenme_sayisi',)
    actions = ['ilani_onayla', 'ilani_pasife_al']
    
    def bitis_tarihi_durumu(self, obj):
        if obj.bitis_tarihi < timezone.now():
            return format_html('<span style="color: red;">Süresi Doldu</span>')
        elif obj.bitis_tarihi < timezone.now() + timezone.timedelta(days=7):
            return format_html('<span style="color: orange;">Son 1 Hafta</span>')
        else:
            return format_html('<span style="color: green;">Aktif</span>')
    bitis_tarihi_durumu.short_description = 'Bitiş Durumu'
    
    def ilani_onayla(self, request, queryset):
        updated = queryset.update(durum='aktif')
        self.message_user(request, f'{updated} ilan onaylandı.')
    ilani_onayla.short_description = "Seçili ilanları onayla"
    
    def ilani_pasife_al(self, request, queryset):
        updated = queryset.update(durum='pasif')
        self.message_user(request, f'{updated} ilan pasife alındı.')
    ilani_pasife_al.short_description = "Seçili ilanları pasife al"

@admin.register(HaberKaynagi)
class HaberKaynagiAdmin(admin.ModelAdmin, AdminTemplateMixin):
    list_display = ('ad', 'url', 'aktif', 'son_kontrol')
    list_filter = ('aktif',)
    search_fields = ('ad', 'url')
    actions = ['get_news_from_source']
    change_list_template = 'admin/haberler/haberkaynagi/change_list.html'
    
    def get_news_from_source(self, request, queryset):
        total_news = 0
        for kaynak in queryset:
            if 'tekha.com.tr' in kaynak.url:
                try:
                    # Komut çalıştırma
                    call_command('fetch_tekha_news', limit=50, force_update=False, verbosity=0)
                    total_news += 1
                    self.message_user(request, f"TEKHA sitesinden haberler çekildi.", messages.SUCCESS)
                except Exception as e:
                    self.message_user(request, f"Hata: {str(e)}", messages.ERROR)
            else:
                self.message_user(request, f"{kaynak.ad} için haber çekme özelliği henüz eklenmedi.", messages.WARNING)
        
        if total_news > 0:
            self.message_user(request, f"Toplam {total_news} kaynaktan haberler çekildi.", messages.SUCCESS)
    
    get_news_from_source.short_description = "Seçili kaynaklardan haberleri çek"
