import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.cache import cache

class User(AbstractUser):
    USER_TYPES = (
        ('admin', 'Admin'),
        ('owner', 'Owner'),
        ('user', 'User'),
    )
    
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    avatar_url = models.URLField(blank=True)
    user_type = models.CharField(max_length=10, choices=USER_TYPES, default='user')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    onboarding_completed = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)
    last_active_at = models.DateTimeField(null=True, blank=True)
    trust_network_count = models.PositiveIntegerField(default=0)
    beds24_subaccount_id = models.CharField(max_length=100, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']
    
    class Meta:
        db_table = 'users'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['user_type']),
            models.Index(fields=['status']),
            models.Index(fields=['beds24_subaccount_id']),
        ]
    
    def save(self, *args, **kwargs):
        # Clear user cache on save
        cache.delete(f'user_profile_{self.id}')
        super().save(*args, **kwargs)
    
    def get_trust_network_size(self):
        """Get cached trust network size for owners"""
        if self.user_type == 'owner':
            cache_key = f'trust_network_size_{self.id}'
            size = cache.get(cache_key)
            if size is None:
                from trust_levels.models import OwnerTrustedNetwork
                size = OwnerTrustedNetwork.objects.filter(
                    owner=self, status='active'
                ).count()
                cache.set(cache_key, size, timeout=300)  # 5 minutes
            return size
        return 0