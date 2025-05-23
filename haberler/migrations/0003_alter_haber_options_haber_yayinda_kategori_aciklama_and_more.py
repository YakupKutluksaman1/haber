# Generated by Django 5.1.5 on 2025-04-24 15:40

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("haberler", "0002_kategori_haber_slug_alter_haber_yayin_tarihi_and_more"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="haber",
            options={"ordering": ["-yayin_tarihi"], "verbose_name_plural": "Haberler"},
        ),
        migrations.AddField(
            model_name="haber",
            name="yayinda",
            field=models.BooleanField(default=True, verbose_name="Yayında"),
        ),
        migrations.AddField(
            model_name="kategori",
            name="aciklama",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="kategori",
            name="icon",
            field=models.CharField(
                blank=True,
                help_text="Bootstrap Icons sınıf adı (örn: newspaper, trophy)",
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name="haber",
            name="kategori",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="haberler",
                to="haberler.kategori",
            ),
        ),
        migrations.AlterField(
            model_name="haber",
            name="yayin_tarihi",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
