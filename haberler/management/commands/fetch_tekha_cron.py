import os
import sys
import logging
from datetime import datetime
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from haberler.models import HaberKaynagi
from django.core.management import call_command

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Belirlenen periyotta haber kaynaklarından haber çeker. Cron göreviyle çalıştırılmalıdır.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Tüm kaynakları kontrol et'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=5,
            help='Her kaynak için çekilecek maksimum haber sayısı'
        )
        parser.add_argument(
            '--log-file',
            type=str,
            help='Log dosyası yolu'
        )

    def handle(self, *args, **options):
        limit = options['limit']
        check_all = options['all']
        log_file = options.get('log_file')

        # Log dosyası belirtilmişse, dosyaya loglama yapalım
        if log_file:
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(logging.INFO)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

        start_time = datetime.now()
        logger.info(f"Haber çekme işlemi başladı: {start_time}")
        self.stdout.write(self.style.SUCCESS(f"Haber çekme işlemi başladı: {start_time}"))

        # Kontrol edilecek kaynakları belirle
        if check_all:
            kaynaklar = HaberKaynagi.objects.filter(aktif=True)
        else:
            # Son kontrol üzerinden en az 2 saat geçen kaynakları kontrol et
            two_hours_ago = timezone.now() - timezone.timedelta(hours=2)
            kaynaklar = HaberKaynagi.objects.filter(
                aktif=True,
                son_kontrol__lte=two_hours_ago
            )

        if not kaynaklar.exists():
            self.stdout.write(self.style.WARNING("Kontrol edilecek aktif kaynak bulunamadı."))
            logger.info("Kontrol edilecek aktif kaynak bulunamadı.")
            return

        self.stdout.write(f"{kaynaklar.count()} adet haber kaynağı kontrol edilecek.")
        logger.info(f"{kaynaklar.count()} adet haber kaynağı kontrol edilecek.")

        # TEKHA sitesinden Abdullah Solmaz haberlerini çek
        tekha_sources = kaynaklar.filter(url__contains='tekha.com.tr')
        if tekha_sources.exists():
            for tekha_source in tekha_sources:
                logger.info(f"TEKHA kaynağından haber çekiliyor: {tekha_source.url}")
                self.stdout.write(self.style.SUCCESS(f"TEKHA kaynağından haber çekiliyor: {tekha_source.url}"))
                
                try:
                    # Burada --force-update bayrağını ekleyerek varolan haberlerin de kontrol edilmesini sağlıyoruz
                    call_command('fetch_tekha_news', limit=limit, force_update=True)
                    logger.info(f"TEKHA haber çekme işlemi tamamlandı")
                    self.stdout.write(self.style.SUCCESS(f"TEKHA haber çekme işlemi tamamlandı"))
                except Exception as e:
                    logger.error(f"TEKHA haber çekme hatası: {str(e)}")
                    self.stdout.write(self.style.ERROR(f"TEKHA haber çekme hatası: {str(e)}"))
        
        # Burada diğer kaynak türleri için özel komutlar çağrılabilir
        # Örnek: call_command('fetch_other_source', limit=limit)

        end_time = datetime.now()
        duration = end_time - start_time
        self.stdout.write(self.style.SUCCESS(f"Haber çekme işlemi tamamlandı. Süre: {duration}"))
        logger.info(f"Haber çekme işlemi tamamlandı. Süre: {duration}") 