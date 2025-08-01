# Generated by Django 5.2.3 on 2025-07-02 01:20

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Invitation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('email', models.EmailField(max_length=254)),
                ('invitee_name', models.CharField(blank=True, max_length=255)),
                ('invitation_type', models.CharField(choices=[('admin', 'Admin'), ('owner', 'Owner'), ('user', 'User')], default='user', max_length=10)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('accepted', 'Accepted'), ('declined', 'Declined'), ('expired', 'Expired')], default='pending', max_length=20)),
                ('personal_message', models.TextField(blank=True)),
                ('invitation_token', models.UUIDField(default=uuid.uuid4, unique=True)),
                ('expires_at', models.DateTimeField()),
                ('accepted_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('accepted_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='accepted_invitations', to=settings.AUTH_USER_MODEL)),
                ('invited_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sent_invitations', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'invitations',
            },
        ),
        migrations.CreateModel(
            name='OnboardingToken',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('email', models.EmailField(max_length=254)),
                ('user_type', models.CharField(choices=[('admin', 'Admin'), ('owner', 'Owner'), ('user', 'User')], default='user', max_length=10)),
                ('token', models.UUIDField(default=uuid.uuid4, unique=True)),
                ('expires_at', models.DateTimeField()),
                ('used_at', models.DateTimeField(blank=True, null=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('invitation', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='invitations.invitation')),
                ('used_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'onboarding_tokens',
            },
        ),
        migrations.AddIndex(
            model_name='invitation',
            index=models.Index(fields=['invitation_token'], name='invitations_invitat_9c6805_idx'),
        ),
        migrations.AddIndex(
            model_name='invitation',
            index=models.Index(fields=['email', 'status'], name='invitations_email_fc68a2_idx'),
        ),
        migrations.AddIndex(
            model_name='invitation',
            index=models.Index(fields=['invited_by', 'status'], name='invitations_invited_df73f2_idx'),
        ),
        migrations.AddIndex(
            model_name='invitation',
            index=models.Index(fields=['expires_at'], name='invitations_expires_7f52c2_idx'),
        ),
        migrations.AddIndex(
            model_name='onboardingtoken',
            index=models.Index(fields=['token'], name='onboarding__token_69c4f4_idx'),
        ),
        migrations.AddIndex(
            model_name='onboardingtoken',
            index=models.Index(fields=['email'], name='onboarding__email_2c8d89_idx'),
        ),
        migrations.AddIndex(
            model_name='onboardingtoken',
            index=models.Index(fields=['expires_at'], name='onboarding__expires_9029aa_idx'),
        ),
    ]
