# Generated by Django 5.0.3 on 2024-04-18 05:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('domestic', '0009_alter_stockinfo_is_hs'),
    ]

    operations = [
        migrations.AlterField(
            model_name='fundinfo',
            name='invest_type',
            field=models.CharField(max_length=50, null=True),
        ),
        migrations.AlterField(
            model_name='fundinfo',
            name='status',
            field=models.CharField(max_length=50, null=True),
        ),
        migrations.AlterField(
            model_name='fundinfo',
            name='trustee',
            field=models.CharField(max_length=100, null=True),
        ),
        migrations.AlterField(
            model_name='fundinfo',
            name='type',
            field=models.CharField(max_length=50, null=True),
        ),
    ]
