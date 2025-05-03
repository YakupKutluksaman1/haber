from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.contrib.auth.models import User
from ckeditor_uploader.fields import RichTextUploadingField

class Kategori(models.Model):
    ad = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    icon = models.CharField(max_length=50, blank=True, help_text="Bootstrap Icons sınıf adı (örn: newspaper, trophy)")
    aciklama = models.CharField(max_length=200, blank=True)
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.ad)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return self.ad

class Haber(models.Model):
    baslik = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    icerik = RichTextUploadingField(verbose_name="İçerik")
    ozet = models.TextField(max_length=500, blank=True, help_text="Haberin kısa özeti (maksimum 500 karakter)")
    yayin_tarihi = models.DateTimeField(
        default=timezone.now,
        help_text="Haberin yayınlanacağı tarih ve saat"
    )
    olusturulma_tarihi = models.DateTimeField(auto_now_add=True)
    guncelleme_tarihi = models.DateTimeField(auto_now=True)
    yazar = models.ForeignKey(User, on_delete=models.CASCADE)
    kategori = models.ForeignKey(Kategori, on_delete=models.CASCADE, related_name='haberler')
    resim = models.ImageField(upload_to='haber_resimleri/', null=True, blank=True)
    yayinda = models.BooleanField(default=True, verbose_name="Yayında")
    goruntulenme_sayisi = models.PositiveIntegerField(default=0, verbose_name="Görüntülenme Sayısı")
    manset = models.BooleanField(default=False, verbose_name="Manşet Haber", help_text="Bu haber manşette gösterilsin mi?")

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.baslik)
            # Eğer aynı slug varsa sonuna sayı ekle
            original_slug = self.slug
            counter = 1
            while Haber.objects.filter(slug=self.slug).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1
        
        # Yayın tarihi gelecekte ise ve haber yayında ise, yayın tarihini şu ana ayarla
        if self.yayin_tarihi > timezone.now() and self.yayinda:
            self.yayin_tarihi = timezone.now()
            
        super().save(*args, **kwargs)

    def __str__(self):
        return self.baslik

    class Meta:
        verbose_name_plural = "Haberler"
        ordering = ['-yayin_tarihi']

class Yorum(models.Model):
    haber = models.ForeignKey(Haber, on_delete=models.CASCADE, related_name='yorumlar')
    yazar = models.ForeignKey(User, on_delete=models.CASCADE)
    icerik = models.TextField()
    olusturulma_tarihi = models.DateTimeField(auto_now_add=True)
    guncelleme_tarihi = models.DateTimeField(auto_now=True)
    aktif = models.BooleanField(default=True)

    class Meta:
        ordering = ['-olusturulma_tarihi']

    def __str__(self):
        return f"{self.yazar.username} - {self.haber.baslik[:50]}"

class Ilan(models.Model):
    DURUM_SECENEKLERI = (
        ('aktif', 'Aktif'),
        ('pasif', 'Pasif'),
        ('beklemede', 'Onay Bekliyor'),
    )
    
    firma_adi = models.CharField(max_length=200, verbose_name="Firma Adı")
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    faaliyet_alani = models.CharField(max_length=200, verbose_name="Faaliyet Alanı")
    aciklama = models.TextField(verbose_name="İlan Açıklaması")
    adres = models.TextField(verbose_name="Adres")
    telefon = models.CharField(max_length=20, verbose_name="Telefon")
    email = models.EmailField(verbose_name="E-posta", blank=True)
    website = models.URLField(verbose_name="Web Sitesi", blank=True)
    logo = models.ImageField(upload_to='ilan_logolari/', null=True, blank=True, verbose_name="Firma Logosu")
    ekleyen = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ilanlar', verbose_name="Ekleyen")
    olusturulma_tarihi = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma Tarihi")
    guncelleme_tarihi = models.DateTimeField(auto_now=True, verbose_name="Güncelleme Tarihi")
    bitis_tarihi = models.DateTimeField(verbose_name="İlan Bitiş Tarihi", help_text="İlanın yayında kalacağı son tarih")
    durum = models.CharField(max_length=10, choices=DURUM_SECENEKLERI, default='beklemede', verbose_name="İlan Durumu")
    one_cikarilmis = models.BooleanField(default=False, verbose_name="Öne Çıkarılmış", help_text="Bu ilan öne çıkarılsın mı?")
    goruntulenme_sayisi = models.PositiveIntegerField(default=0, verbose_name="Görüntülenme Sayısı")
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.firma_adi)
            # Eğer aynı slug varsa sonuna sayı ekle
            original_slug = self.slug
            counter = 1
            while Ilan.objects.filter(slug=self.slug).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1
        super().save(*args, **kwargs)

    def __str__(self):
        return self.firma_adi
    
    class Meta:
        verbose_name_plural = "İlanlar"
        ordering = ['-olusturulma_tarihi']
