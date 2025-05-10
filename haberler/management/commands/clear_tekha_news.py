import logging
from django.core.management.base import BaseCommand
from haberler.models import Haber, HaberKaynagi

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'TEKHA sitesinden çekilmiş haberleri siler'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Silme işlemini onaylayın'
        )
        parser.add_argument(
            '--yazar',
            type=str,
            default='',
            help='Belirli bir yazarın haberlerini sil (boş bırakılırsa tüm TEKHA haberleri)'
        )

    def handle(self, *args, **options):
        confirm = options['confirm']
        yazar_adi = options['yazar']
        
        # TEKHA kaynağını bul
        try:
            tekha_kaynak = HaberKaynagi.objects.get(url__contains='tekha.com.tr')
        except HaberKaynagi.DoesNotExist:
            self.stdout.write(self.style.ERROR('TEKHA kaynağı bulunamadı!'))
            return
        
        # Silinecek haberleri sorgula
        haberler = Haber.objects.filter(kaynak=tekha_kaynak)
        
        # Eğer belirli bir yazar belirtilmişse, filtreleme ekle
        if yazar_adi:
            haberler = haberler.filter(icerik__icontains=yazar_adi)
            self.stdout.write(f'"{yazar_adi}" adına ait TEKHA haberleri sorgulanıyor...')
        else:
            self.stdout.write('Tüm TEKHA haberleri sorgulanıyor...')
        
        # Toplam haber sayısını göster
        haber_sayisi = haberler.count()
        self.stdout.write(f'Toplam {haber_sayisi} haber bulundu.')
        
        # Onay kontrolü
        if not confirm:
            self.stdout.write(self.style.WARNING('Silme işlemi onaylanmadı. Onaylamak için --confirm parametresini ekleyin.'))
            self.stdout.write(f'Örnek: python manage.py clear_tekha_news --confirm')
            return
        
        # İşlemi gerçekleştir
        for haber in haberler:
            # Resim dosyasını da sil
            if haber.resim:
                haber.resim.delete(save=False)
            
            # Haberi sil
            haber_baslik = haber.baslik
            haber.delete()
            self.stdout.write(f'Silindi: {haber_baslik}')
        
        self.stdout.write(self.style.SUCCESS(f'İşlem tamamlandı. {haber_sayisi} haber silindi.')) 