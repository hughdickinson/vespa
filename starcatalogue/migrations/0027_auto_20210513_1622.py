# Generated by Django 3.2.2 on 2021-05-13 16:22

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('starcatalogue', '0026_star_stats_version'),
    ]

    operations = [
        migrations.AddField(
            model_name='dataexport',
            name='max_classifications',
            field=models.IntegerField(null=True),
        ),
        migrations.AddField(
            model_name='dataexport',
            name='min_classifications',
            field=models.IntegerField(null=True),
        ),
    ]
