from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.contrib.auth.models import User

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
    icerik = models.TextField()
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
