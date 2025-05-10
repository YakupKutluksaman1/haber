@echo off
cd /d "%~dp0"
echo ---- TEKHA Haber Çekme İşlemi Başlıyor - %date% %time% ----
python manage.py fetch_tekha_cron --all --limit 100
echo ---- İşlem Tamamlandı - %date% %time% ---- 