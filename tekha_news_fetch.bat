@echo off
cd /d "%~dp0"
python manage.py fetch_tekha_cron --all --limit=5 --log-file=logs/tekha_cron.log
echo Haber çekme işlemi tamamlandı: %date% %time% >> logs/cron_history.log 