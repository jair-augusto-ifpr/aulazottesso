from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="material",
            name="title",
            field=models.CharField(blank=True, max_length=200, verbose_name="título"),
        ),
        migrations.AddField(
            model_name="material",
            name="text_content",
            field=models.TextField(blank=True, verbose_name="texto para busca"),
        ),
    ]
