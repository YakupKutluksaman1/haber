from django.core.management import call_command
import logging

logger = logging.getLogger(__name__)

def fetch_tekha_news_job():
    """
    Abdullah Solmaz'ın TEKHA sitesinden haberlerini çeken cron görevi.
    Bu fonksiyon, django-crontab aracılığıyla düzenli çalıştırılır.
    """
    try:
        # En son 5 haberi çek
        call_command('fetch_tekha_cron', all=True, limit=5, log_file='logs/tekha_cron.log')
        logger.info("TEKHA haberleri başarıyla çekildi.")
        return "TEKHA haberleri başarıyla çekildi."
    except Exception as e:
        logger.error(f"TEKHA haberleri çekilirken hata oluştu: {str(e)}")
        return f"TEKHA haberleri çekilirken hata oluştu: {str(e)}" 