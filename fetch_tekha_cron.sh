#!/bin/bash

# Projenin bulunduğu dizine git
cd /path/to/haber/project

# Python sanal ortamını etkinleştir (eğer varsa)
# source /path/to/venv/bin/activate

# Log dosyası için tarih ve saat oluştur
DATE=$(date +"%Y-%m-%d_%H-%M-%S")
LOG_FILE="logs/tekha_fetch_$DATE.log"

# Log klasörünü oluştur (yoksa)
mkdir -p logs

echo "---- TEKHA Haber Çekme İşlemi Başlıyor - $(date) ----" | tee -a "$LOG_FILE"

# Komutu çalıştır ve çıktıyı hem ekrana hem de log dosyasına yönlendir
python manage.py fetch_tekha_cron --all --limit 50 --log-file="$LOG_FILE" 2>&1 | tee -a "$LOG_FILE"

echo "---- İşlem Tamamlandı - $(date) ----" | tee -a "$LOG_FILE" 