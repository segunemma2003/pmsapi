# Generated by Django 5.2.3 on 2025-07-03 17:23

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('properties', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PropertyImage',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('image_url', models.URLField()),
                ('is_primary', models.BooleanField(default=False)),
                ('order', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'property_images',
                'ordering': ['order', 'created_at'],
            },
        ),
        migrations.RemoveField(
            model_name='propertyicalsync',
            name='property',
        ),
        migrations.RemoveIndex(
            model_name='property',
            name='properties_status_e6008a_idx',
        ),
        migrations.RemoveIndex(
            model_name='property',
            name='properties_city_6c1708_idx',
        ),
        migrations.RemoveIndex(
            model_name='property',
            name='properties_beds24__e2c880_idx',
        ),
        migrations.RemoveField(
            model_name='property',
            name='approval_notes',
        ),
        migrations.RemoveField(
            model_name='property',
            name='approved_at',
        ),
        migrations.RemoveField(
            model_name='property',
            name='approved_by',
        ),
        migrations.RemoveField(
            model_name='property',
            name='images',
        ),
        migrations.RemoveField(
            model_name='property',
            name='rejected_at',
        ),
        migrations.RemoveField(
            model_name='property',
            name='rejected_by',
        ),
        migrations.RemoveField(
            model_name='property',
            name='rejection_reason',
        ),
        migrations.RemoveField(
            model_name='property',
            name='submitted_for_approval_at',
        ),
        migrations.AddField(
            model_name='property',
            name='is_visible',
            field=models.BooleanField(db_index=True, default=True),
        ),
        migrations.AlterField(
            model_name='property',
            name='bedrooms',
            field=models.PositiveIntegerField(db_index=True),
        ),
        migrations.AlterField(
            model_name='property',
            name='beds24_property_id',
            field=models.CharField(blank=True, max_length=100, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name='property',
            name='city',
            field=models.CharField(blank=True, db_index=True, max_length=100),
        ),
        migrations.AlterField(
            model_name='property',
            name='country',
            field=models.CharField(blank=True, db_index=True, max_length=100),
        ),
        migrations.AlterField(
            model_name='property',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, db_index=True),
        ),
        migrations.AlterField(
            model_name='property',
            name='ical_export_url',
            field=models.URLField(blank=True),
        ),
        migrations.AlterField(
            model_name='property',
            name='ical_import_url',
            field=models.URLField(blank=True),
        ),
        migrations.AlterField(
            model_name='property',
            name='is_featured',
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AlterField(
            model_name='property',
            name='max_guests',
            field=models.PositiveIntegerField(db_index=True),
        ),
        migrations.AlterField(
            model_name='property',
            name='price_per_night',
            field=models.DecimalField(db_index=True, decimal_places=2, max_digits=10),
        ),
        migrations.AlterField(
            model_name='property',
            name='status',
            field=models.CharField(choices=[('draft', 'Draft'), ('active', 'Active'), ('inactive', 'Inactive'), ('suspended', 'Suspended')], db_index=True, default='active', max_length=30),
        ),
        migrations.AlterField(
            model_name='property',
            name='title',
            field=models.CharField(db_index=True, max_length=255),
        ),
        migrations.AddIndex(
            model_name='property',
            index=models.Index(fields=['status', 'is_visible'], name='properties_status_edbcfe_idx'),
        ),
        migrations.AddIndex(
            model_name='property',
            index=models.Index(fields=['city', 'status', 'is_visible'], name='properties_city_573570_idx'),
        ),
        migrations.AddIndex(
            model_name='property',
            index=models.Index(fields=['price_per_night', 'status', 'is_visible'], name='properties_price_p_642d4a_idx'),
        ),
        migrations.AddField(
            model_name='propertyimage',
            name='property',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='images_set', to='properties.property'),
        ),
        migrations.DeleteModel(
            name='PropertyICalSync',
        ),
        migrations.AddIndex(
            model_name='propertyimage',
            index=models.Index(fields=['property', 'is_primary'], name='property_im_propert_0ad054_idx'),
        ),
        migrations.AddIndex(
            model_name='propertyimage',
            index=models.Index(fields=['order'], name='property_im_order_48eaf4_idx'),
        ),
    ]
